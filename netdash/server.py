"""HTTP server: statické súbory dashboardu + JSON API."""
import hmac
import ipaddress
import json
import os
import re
import secrets
import threading
import time
import traceback
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import drivers, netutil

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
MIME = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
        ".json": "application/manifest+json"}
POOL = ThreadPoolExecutor(16)


class App:
    def __init__(self, store, scanner, pin=None, demo=None):
        self.store = store
        self.scanner = scanner
        self.pin = pin
        self.demo = demo
        self.sessions = set(store.get("settings", "sessions", []) or [])
        self.fails = {}
        self.dev_locks = {}
        self.lock = threading.Lock()

    def device_lock(self, did):
        with self.lock:
            return self.dev_locks.setdefault(did, threading.Lock())

    def controls(self, dev):
        """Ovládacie prvky všetkých ovládačov zariadenia; id = '<ovládač>/<prvok>'."""
        out = []
        for d in dev.get("drivers", []):
            drv = self.demo if self.demo else drivers.BY_KEY[d["key"]]
            view = dict(dev, driver_info=d.get("info") or {})
            section = d.get("label") if len(dev["drivers"]) > 1 else None
            try:
                ctrls = drv.controls(view, self.store)
            except drivers.ActionError as e:
                ctrls = [drivers.INFO("⚠ " + str(e), id="err")]
            except Exception as e:  # noqa
                traceback.print_exc()
                ctrls = [drivers.INFO("⚠ Chyba: %s" % e, id="err")]
            for c in ctrls:
                c = dict(c, id="%s/%s" % (d["key"], c["id"]))
                if section:
                    c["section"] = section
                out.append(c)
        return out

    def set_control(self, dev, cid, value):
        key, _, sub = cid.partition("/")
        d = next((x for x in dev.get("drivers", []) if x["key"] == key), None)
        if not d:
            raise drivers.ActionError("Neznámy ovládač")
        drv = self.demo if self.demo else drivers.BY_KEY[key]
        drv.set(dict(dev, driver_info=d.get("info") or {}), self.store, sub, value)


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = "NetDash/1.0"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            pass

        # ---------------------------------------------------------- pomocníci
        def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json_body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > 1_000_000:
                raise ValueError("Príliš veľká požiadavka")
            raw = self.rfile.read(n) if n else b""
            return json.loads(raw.decode("utf-8")) if raw else {}

        def _host_ok(self):
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
            if host in ("localhost", ""):
                return True
            try:
                ipaddress.ip_address(host)
                return True
            except ValueError:
                return host.endswith(".local")  # mDNS meno počítača

        def _client_local(self):
            ip = self.client_address[0]
            return ip in ("127.0.0.1", "::1", "::ffff:127.0.0.1")

        def _authed(self):
            if not app.pin or self._client_local():
                return True
            c = SimpleCookie(self.headers.get("Cookie") or "")
            tok = c.get("netdash")
            return bool(tok and tok.value in app.sessions)

        # ---------------------------------------------------------- GET
        def do_GET(self):
            if not self._host_ok():
                return self._send(403, {"error": "Neplatný Host"})
            path = urllib.parse.urlparse(self.path).path
            if path == "/api/state":
                if not self._authed():
                    return self._send(401, {"error": "auth", "pin_required": True})
                return self._send(200, {"devices": app.scanner.device_list(), "scan": app.scanner.progress,
                                        "meta": app.scanner.meta, "demo": bool(app.demo)})
            m = re.match(r"^/api/devices/([^/]+)/controls$", path)
            if m:
                if not self._authed():
                    return self._send(401, {"error": "auth"})
                return self._controls(urllib.parse.unquote(m.group(1)))
            if path == "/":
                path = "/index.html"
            fp = os.path.normpath(os.path.join(STATIC, path.lstrip("/")))
            if not fp.startswith(STATIC + os.sep) or not os.path.isfile(fp):
                return self._send(404, {"error": "Nenájdené"})
            with open(fp, "rb") as f:
                data = f.read()
            self._send(200, data, MIME.get(os.path.splitext(fp)[1], "application/octet-stream"))

        def _controls(self, did, timeout=12):
            dev = app.scanner.get(did)
            if not dev:
                return self._send(404, {"error": "Zariadenie nenájdené"})
            fut = POOL.submit(app.controls, dev)
            try:
                return self._send(200, {"controls": fut.result(timeout)})
            except FutTimeout:
                return self._send(504, {"error": "Zariadenie neodpovedá včas"})

        # ---------------------------------------------------------- POST
        def do_POST(self):
            if not self._host_ok():
                return self._send(403, {"error": "Neplatný Host"})
            # vlastná hlavička = prehliadač ju nepošle cross-origin bez CORS (ochrana pred CSRF)
            if self.headers.get("X-NetDash") != "1":
                return self._send(403, {"error": "Chýba hlavička"})
            path = urllib.parse.urlparse(self.path).path
            try:
                body = self._json_body()
            except ValueError as e:
                return self._send(400, {"error": str(e)})

            if path == "/api/login":
                ip = self.client_address[0]
                fails = [t for t in app.fails.get(ip, []) if t > time.time() - 300]
                if len(fails) >= 5:
                    return self._send(429, {"error": "Príliš veľa pokusov, skús o 5 minút."})
                if app.pin and hmac.compare_digest(str(body.get("pin", "")), app.pin):
                    tok = secrets.token_urlsafe(24)
                    app.sessions.add(tok)
                    app.store.put("settings", "sessions", sorted(app.sessions)[-50:])
                    return self._send(200, {"ok": True}, extra={
                        "Set-Cookie": "netdash=%s; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000" % tok})
                app.fails[ip] = fails + [time.time()]
                return self._send(403, {"error": "Nesprávny PIN"})

            if not self._authed():
                return self._send(401, {"error": "auth"})

            if path == "/api/scan":
                subnet = body.get("subnet") or None
                if subnet:
                    try:
                        net = ipaddress.IPv4Network(subnet, strict=False)
                    except ValueError:
                        return self._send(400, {"error": "Neplatná sieť (napr. 192.168.1.0/24)"})
                    if not net.is_private:
                        return self._send(400, {"error": "Skenovať sa dá len súkromná sieť"})
                started = app.scanner.start(subnet)
                return self._send(200, {"started": started, "scan": app.scanner.progress})

            m = re.match(r"^/api/devices/([^/]+)/(controls|alias|wol)$", path)
            if not m:
                return self._send(404, {"error": "Nenájdené"})
            did, action = urllib.parse.unquote(m.group(1)), m.group(2)
            dev = app.scanner.get(did)
            if not dev:
                return self._send(404, {"error": "Zariadenie nenájdené"})

            if action == "alias":
                name = str(body.get("name") or "").strip()[:60]
                app.store.put("aliases", did, name or None)
                return self._send(200, {"ok": True})
            if action == "wol":
                if not dev.get("mac"):
                    return self._send(400, {"error": "Zariadenie nemá známu MAC adresu"})
                meta = app.scanner.meta
                addrs = ["255.255.255.255"]
                if meta.get("network"):
                    addrs.append(str(ipaddress.IPv4Network(meta["network"]).broadcast_address))
                addrs.append(dev["ip"])
                if not app.demo:
                    netutil.wake_on_lan(dev["mac"], addrs)
                return self._send(200, {"ok": True})

            cid, value = body.get("id"), body.get("value")
            if not isinstance(cid, str):
                return self._send(400, {"error": "Chýba id"})
            lock = app.device_lock(did)

            def work():
                with lock:
                    app.set_control(dev, cid, value)
                    time.sleep(0.25 if not app.demo else 0)
                    return app.controls(dev)
            try:
                return self._send(200, {"controls": POOL.submit(work).result(15)})
            except drivers.ActionError as e:
                return self._send(502, {"error": str(e)})
            except FutTimeout:
                return self._send(504, {"error": "Zariadenie neodpovedá včas"})
            except Exception as e:  # noqa
                traceback.print_exc()
                return self._send(500, {"error": "Chyba: %s" % e})

    return Handler


def serve(app, host, port):
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    httpd.daemon_threads = True
    return httpd
