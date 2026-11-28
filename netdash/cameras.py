"""Kamery: konfigurácia, snímky a živý obraz (MJPEG) z RTSP/HTTP/Home Assistant."""
import base64
import ipaddress
import json
import os
import secrets
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import netutil

PRESETS = {
    "hikvision": {"label": "Hikvision / HiLook", "rtsp": "rtsp://{u}:{p}@{ip}:554/Streaming/Channels/{ch}02",
                  "snapshot": "http://{ip}/ISAPI/Streaming/channels/{ch}01/picture", "user": "admin", "channels": True,
                  "note": "Meno je zvyčajne admin a heslo je heslo zariadenia (nie overovací kód z Hik-Connect). "
                          "Pri rekordéri (NVR/DVR) zadaj IP rekordéra a číslo kanála kamery."},
    "dahua": {"label": "Dahua / Imou / Amcrest", "rtsp": "rtsp://{u}:{p}@{ip}:554/cam/realmonitor?channel={ch}&subtype=1",
              "snapshot": "http://{ip}/cgi-bin/snapshot.cgi?channel={ch}", "user": "admin", "channels": True},
    "reolink": {"label": "Reolink", "rtsp": "rtsp://{u}:{p}@{ip}:554/h264Preview_{ch2}_sub",
                "snapshot": "http://{ip}/cgi-bin/api.cgi?cmd=Snap&channel={ch0}&rs=netdash&user={u}&password={p}", "user": "admin",
                "channels": True},
    "tapo": {"label": "TP-Link Tapo / VIGI", "rtsp": "rtsp://{u}:{p}@{ip}:554/stream2", "snapshot": "",
             "user": "", "note": "Meno a heslo si vytvor v appke Tapo: Kamera → Nastavenia → Pokročilé → Účet kamery."},
    "ezviz": {"label": "Ezviz", "rtsp": "rtsp://admin:{p}@{ip}:554/h264/ch1/sub/av_stream", "snapshot": "",
              "user": "admin", "note": "Heslo je overovací kód zo štítku kamery (6 veľkých písmen)."},
    "axis": {"label": "Axis", "rtsp": "rtsp://{u}:{p}@{ip}/axis-media/media.amp?resolution=640x360",
             "snapshot": "http://{ip}/axis-cgi/jpg/image.cgi", "user": "root"},
    "foscam": {"label": "Foscam", "rtsp": "rtsp://{u}:{p}@{ip}:554/videoSub",
               "snapshot": "http://{ip}:88/cgi-bin/CGIProxy.fcgi?cmd=snapPicture2&usr={u}&pwd={p}", "user": "admin"},
    "generic": {"label": "Iná kamera (vlastná adresa)", "rtsp": "", "snapshot": "", "user": "admin",
                "note": "Zadaj RTSP adresu alebo adresu obrázka/MJPEG z návodu ku kamere."},
}
VENDOR_HINTS = [("hikvision", "hikvision"), ("hilook", "hikvision"), ("dahua", "dahua"), ("imou", "dahua"), ("amcrest", "dahua"),
                ("reolink", "reolink"), ("tapo", "tapo"), ("tp-link", "tapo"), ("vigi", "tapo"), ("ezviz", "ezviz"),
                ("axis", "axis"), ("foscam", "foscam")]

MAX_FFMPEG = 8
_ffmpeg_count = 0
_ffmpeg_lock = threading.Lock()


class CameraError(Exception):
    pass


def ffmpeg_path():
    p = shutil.which("ffmpeg")
    if p:
        return p
    for c in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg",
              os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe"), r"C:\ffmpeg\bin\ffmpeg.exe"):
        if os.path.isfile(c):
            return c
    return None


def _host_allowed(url):
    """Kamery len v lokálnej sieti (ochrana pred zneužitím servera na prístup inam)."""
    host = urllib.parse.urlsplit(url).hostname or ""
    if host.endswith(".local") or host == "localhost":
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not (ip.is_private or ip.is_loopback or ip.is_link_local):
            return False
    return bool(infos)


def _fill(tpl, ip, user, pw, ch=1):
    q = lambda s: urllib.parse.quote(s or "", safe="")  # noqa: E731
    if not tpl:
        return ""
    return (tpl.replace("{ip}", ip).replace("{u}", q(user)).replace("{p}", q(pw)).replace("{ch2}", "%02d" % ch)
            .replace("{ch0}", str(ch - 1)).replace("{ch}", str(ch)))


class Cameras:
    def __init__(self, store, demo=False):
        self.store = store
        self.demo = demo

    # ------------------------------------------------------------- konfigurácia
    def all(self):
        return list((self.store.data.get("cameras") or {}).values()) if not self.demo else self._demo_list()

    def get(self, cid):
        for c in self.all():
            if c["id"] == cid:
                return c
        return None

    def public(self, cam):
        c = {k: v for k, v in cam.items() if k not in ("rtsp", "snapshot", "mjpeg", "_pw")}
        c["has_password"] = bool(self.store.get("secrets", "cam:" + cam["id"]))
        c["source"] = "Home Assistant" if cam.get("type") == "ha" else (
            "RTSP" + (" + obrázok" if cam.get("snapshot") else "") if cam.get("rtsp") else "MJPEG" if cam.get("mjpeg") else "obrázok" if cam.get("snapshot") else "—")
        c["custom"] = {k: self._mask(cam.get(k, "")) for k in ("rtsp", "snapshot", "mjpeg")} if cam.get("preset") == "generic" else None
        return c

    @staticmethod
    def _mask(url):
        if not url:
            return ""
        p = urllib.parse.urlsplit(url)
        if p.password:
            netloc = "%s:***@%s" % (p.username, p.hostname + (":%d" % p.port if p.port else ""))
            return urllib.parse.urlunsplit((p.scheme, netloc, p.path, p.query, p.fragment))
        return url

    def save(self, data):
        cams = self.store.data.setdefault("cameras", {})
        cid = data.get("id") or secrets.token_hex(4)
        old = cams.get(cid, {})
        name = str(data.get("name") or "").strip()[:40] or "Kamera"
        if data.get("type") == "ha":
            cam = {"id": cid, "type": "ha", "name": name, "ha_ip": data["ha_ip"], "entity": data["entity"]}
        else:
            preset = data.get("preset") if data.get("preset") in PRESETS else "generic"
            ip = str(data.get("ip") or old.get("ip") or "").strip()
            user = str(data.get("user") if data.get("user") is not None else old.get("user", "")).strip()
            pw = data.get("password")
            if pw is None or pw == "":
                pw = self.store.get("secrets", "cam:" + cid) or ""
            try:
                ch = max(1, min(64, int(data.get("channel") or old.get("channel") or 1)))
            except (TypeError, ValueError):
                ch = 1
            cam = {"id": cid, "type": "net", "name": name, "preset": preset, "ip": ip, "user": user, "channel": ch}
            if preset == "generic":
                for k in ("rtsp", "snapshot", "mjpeg"):
                    v = str(data.get(k) or "").strip()
                    if "***" in v:
                        v = old.get(k, "")
                    cam[k] = v
            else:
                if not ip:
                    raise CameraError("Zadaj IP adresu kamery")
                p = PRESETS[preset]
                cam["rtsp"] = _fill(p["rtsp"], ip, user, pw, ch)
                cam["snapshot"] = _fill(p["snapshot"], ip, user, pw, ch)
                cam["mjpeg"] = ""
            for k in ("rtsp", "snapshot", "mjpeg"):
                if cam.get(k) and not _host_allowed(cam[k]):
                    raise CameraError("Adresa kamery musí byť v lokálnej sieti")
            if not any(cam.get(k) for k in ("rtsp", "snapshot", "mjpeg")):
                raise CameraError("Chýba adresa videa alebo obrázka")
            cam["_pw"] = pw or ""
        return cam

    def commit(self, cam):
        cam = dict(cam)
        pw = cam.pop("_pw", None)
        with self.store.lock:
            self.store.data.setdefault("cameras", {})[cam["id"]] = cam
            sec = self.store.data.setdefault("secrets", {})
            if pw:
                sec["cam:" + cam["id"]] = pw
            else:
                sec.pop("cam:" + cam["id"], None)
            self.store.save()

    def delete(self, cid):
        with self.store.lock:
            (self.store.data.get("cameras") or {}).pop(cid, None)
            (self.store.data.get("secrets") or {}).pop("cam:" + cid, None)
            self.store.save()

    # ------------------------------------------------------------- návrhy
    def suggestions(self, devices):
        have = {c.get("ip") for c in self.all()} | {c.get("entity") for c in self.all()}
        out = []
        for d in devices:
            if not d.get("online") or d["ip"] in have:
                continue
            if d.get("category") == "camera" or 554 in (d.get("open_ports") or []):
                if d.get("category") in ("media", "router", "server", "computer"):
                    continue
                blob = " ".join(str(d.get(k) or "") for k in ("vendor", "model", "name", "hostname")).lower()
                preset = next((p for w, p in VENDOR_HINTS if w in blob), "generic")
                out.append({"type": "net", "name": d.get("display_name") or d["name"], "ip": d["ip"], "preset": preset,
                            "vendor": " ".join(x for x in (d.get("vendor"), d.get("model")) if x)})
            for drv in d.get("drivers") or []:
                if drv["key"] != "homeassistant":
                    continue
                token = self.store.get("secrets", "ha:" + d["ip"])
                if not token:
                    continue
                states = netutil.get_json("http://%s:8123/api/states" % d["ip"], timeout=5,
                                          headers={"Authorization": "Bearer " + token}) or []
                for s in states if isinstance(states, list) else []:
                    if s.get("entity_id", "").startswith("camera.") and s["entity_id"] not in have and s.get("state") != "unavailable":
                        out.append({"type": "ha", "name": (s.get("attributes") or {}).get("friendly_name") or s["entity_id"],
                                    "ha_ip": d["ip"], "entity": s["entity_id"], "vendor": "Home Assistant"})
        return out

    # ------------------------------------------------------------- obraz
    def _open(self, url, cam, timeout=8):
        handlers = [urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=netutil._SSL)]
        pw = cam.get("_pw", self.store.get("secrets", "cam:" + cam["id"])) if cam.get("type") != "ha" else None
        headers = {}
        if cam.get("type") == "ha":
            headers["Authorization"] = "Bearer " + (self.store.get("secrets", "ha:" + cam["ha_ip"]) or "")
        elif cam.get("user") or pw:
            mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
            mgr.add_password(None, url, cam.get("user", ""), pw or "")
            handlers += [urllib.request.HTTPDigestAuthHandler(mgr), urllib.request.HTTPBasicAuthHandler(mgr)]
        req = urllib.request.Request(url, headers=headers)
        try:
            return urllib.request.build_opener(*handlers).open(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise CameraError("Kamera odmietla meno alebo heslo")
            raise CameraError("Kamera vrátila chybu %s" % e.code)
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise CameraError("Kamera neodpovedá (%s)" % getattr(e, "reason", e))

    def _ha_url(self, cam, stream=False):
        return "http://%s:8123/api/%s/%s" % (cam["ha_ip"], "camera_proxy_stream" if stream else "camera_proxy", cam["entity"])

    def _ffmpeg_input(self, cam):
        if self.demo:
            return ["-re", "-f", "lavfi", "-i", "testsrc2=size=960x540:rate=8"]
        return ["-rtsp_transport", "tcp", "-timeout", "8000000", "-i", cam["rtsp"]]

    def snapshot(self, cam):
        if cam.get("type") == "ha":
            with self._open(self._ha_url(cam), cam) as r:
                return r.read(8_000_000)
        if cam.get("snapshot") and not self.demo:
            with self._open(cam["snapshot"], cam) as r:
                data = r.read(8_000_000)
            if not data.startswith(b"\xff\xd8"):
                raise CameraError("Kamera nevrátila obrázok JPEG – skontroluj meno a heslo")
            return data
        if cam.get("mjpeg") and not self.demo:
            with self._open(cam["mjpeg"], cam) as r:
                return _first_jpeg(r)
        ff = ffmpeg_path()
        if (cam.get("rtsp") or self.demo) and ff:
            try:
                p = subprocess.run([ff, "-loglevel", "error", *self._ffmpeg_input(cam), "-frames:v", "1", "-f", "image2",
                                    "-vcodec", "mjpeg", "-q:v", "4", "pipe:1"], capture_output=True, timeout=15)
            except subprocess.TimeoutExpired:
                raise CameraError("Kamera neposlala obraz do 15 s")
            if p.returncode != 0 or not p.stdout:
                err = p.stderr.decode("utf-8", "replace").strip().splitlines()
                msg = err[-1] if err else "neznáma chyba"
                if "401" in msg or "Unauthorized" in msg:
                    msg = "nesprávne meno alebo heslo"
                raise CameraError("RTSP zlyhalo: %s" % msg[:160])
            return p.stdout
        if cam.get("rtsp") and not ff:
            raise CameraError("Na RTSP video treba nainštalovať ffmpeg (pozri návod)")
        raise CameraError("Kamera nemá nastavenú adresu")

    def stream(self, cam, write, fps=8, slow=False):
        """Zapisuje multipart MJPEG cez write(bytes), kým klient neodpojí (write vyhodí OSError)."""
        global _ffmpeg_count
        if cam.get("type") == "ha" and not slow:
            with self._open(self._ha_url(cam, True), cam, timeout=10) as r:
                ctype = r.headers.get("Content-Type", "")
                b = ctype.split("boundary=")[-1].strip('"') if "boundary=" in ctype else None
                if b:
                    _relay(r, write, b)
                    return
        if cam.get("mjpeg") and not slow and not self.demo:
            with self._open(cam["mjpeg"], cam, timeout=10) as r:
                ctype = r.headers.get("Content-Type", "")
                if "boundary=" in ctype:
                    _relay(r, write, ctype.split("boundary=")[-1].strip('"'))
                    return
        ff = ffmpeg_path()
        use_ff = not slow and ff and (cam.get("rtsp") or self.demo) and cam.get("type") != "ha"
        if use_ff:
            with _ffmpeg_lock:
                if _ffmpeg_count >= MAX_FFMPEG:
                    use_ff = False
                else:
                    _ffmpeg_count += 1
        if use_ff:
            proc = subprocess.Popen([ff, "-loglevel", "error", *self._ffmpeg_input(cam), "-an",
                                     "-vf", "scale='min(1280,iw)':-2", "-r", str(fps), "-q:v", "6",
                                     "-f", "mpjpeg", "-boundary_tag", "frame", "pipe:1"],
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
            try:
                first = True
                while True:
                    chunk = proc.stdout.read(65536)
                    if not chunk:
                        if first and not cam.get("snapshot"):
                            raise CameraError("RTSP stream sa nepodarilo otvoriť")
                        if first:
                            break  # skúsime snímky
                        return
                    first = False
                    write(chunk)
            finally:
                proc.kill()
                try:
                    proc.wait(3)
                except subprocess.TimeoutExpired:
                    pass
                with _ffmpeg_lock:
                    _ffmpeg_count -= 1
        # záložný režim: opakované snímky
        interval = 2.0 if slow else 1.0
        while True:
            t = time.time()
            img = self.snapshot(cam)
            write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(img) + img + b"\r\n")
            time.sleep(max(0.05, interval - (time.time() - t)))

    # ------------------------------------------------------------- demo
    def _demo_list(self):
        return [{"id": "demo1", "type": "net", "name": "Vchod", "preset": "hikvision", "ip": "192.168.1.60", "user": "admin", "rtsp": "demo"},
                {"id": "demo2", "type": "net", "name": "Záhrada", "preset": "tapo", "ip": "192.168.1.61", "user": "dom", "rtsp": "demo"}]


def _first_jpeg(r):
    buf = b""
    while len(buf) < 8_000_000:
        chunk = r.read(65536)
        if not chunk:
            break
        buf += chunk
        s = buf.find(b"\xff\xd8")
        e = buf.find(b"\xff\xd9", s + 2) if s >= 0 else -1
        if s >= 0 and e > 0:
            return buf[s:e + 2]
    raise CameraError("Zo streamu sa nepodarilo prečítať obrázok")


def _relay(r, write, boundary):
    """Prepošle MJPEG s pôvodnou hranicou premenovanou na 'frame'."""
    old = ("--" + boundary).encode()
    carry = b""
    while True:
        chunk = r.read(65536)
        if not chunk:
            return
        data = (carry + chunk).replace(old, b"--frame")
        carry = data[-len(old):]
        write(data[:-len(old)])


def data_uri(jpeg):
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
