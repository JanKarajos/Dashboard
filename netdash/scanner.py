"""Sken siete: nájde zariadenia, ich porty, mená a typ, a rozpozná ovládateľné zariadenia."""
import ipaddress
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from . import discovery, drivers, netutil

PORTS = {
    21: "FTP", 22: "SSH", 23: "Telnet", 53: "DNS", 80: "HTTP", 139: "NetBIOS", 443: "HTTPS",
    445: "SMB", 548: "AFP", 554: "RTSP", 631: "IPP", 1400: "Sonos", 1925: "Philips TV", 1926: "Philips TV", 1883: "MQTT", 1900: "UPnP",
    3000: "webOS", 3001: "webOS", 3389: "RDP", 5000: "HTTP-5000", 5001: "HTTPS-5001", 5900: "VNC",
    6053: "ESPHome", 6668: "Tuya", 7000: "AirPlay", 8001: "Samsung TV", 8002: "Samsung TV",
    8008: "Cast", 8009: "Cast", 8060: "Roku", 8080: "HTTP-8080", 8081: "HTTP-8081",
    8123: "Home Assistant", 8443: "HTTPS-8443", 8888: "HTTP-8888", 9000: "HTTP-9000",
    9100: "Tlač (RAW)", 32400: "Plex", 49152: "UPnP", 55443: "Yeelight", 62078: "Apple iOS",
}
ALIVE_PORTS = (445, 80, 443, 62078, 22, 8080, 7000, 139)

WEB_PORTS = [(8123, "http", "Home Assistant"), (80, "http", "Web"), (443, "https", "Web"),
             (8080, "http", "Web :8080"), (5000, "http", "Web :5000"), (5001, "https", "Web :5001"),
             (8443, "https", "Web :8443"), (32400, "http", "Plex"), (9000, "http", "Web :9000"),
             (8888, "http", "Web :8888"), (8081, "http", "Web :8081")]


def classify(d):
    p = set(d["open_ports"])
    svc = " ".join(d.get("mdns_services", [])).lower()
    blob = " ".join(str(d.get(k) or "") for k in ("vendor", "model", "name", "hostname", "ssdp_type")).lower()
    drv = [x["key"] for x in d.get("drivers", [])]
    if d.get("is_gateway") or "internetgatewaydevice" in blob or any(w in blob for w in ("router", "fritz!box", "mikrotik")):
        return "router"
    if d.get("is_self"):
        return "computer"
    if set(drv) & {"shelly", "tasmota", "wled", "hue", "yeelight"} or any(
            s in svc for s in ("_hap._tcp", "_shelly", "_esphomelib", "_wled", "_hue", "_miio", "_matter")) or 6668 in p:
        return "smart"
    if "homeassistant" in drv or 8123 in p:
        return "server"
    if set(drv) & {"roku", "samsung", "lgwebos", "philips", "upnp"} or 8008 in p or 8009 in p or any(
            s in svc for s in ("_googlecast", "_airplay", "_raop", "_spotify", "_sonos", "_androidtv", "_amzn")) \
            or "mediarenderer" in blob or any(w in blob for w in ("tv", "sonos", "chromecast", "roku")):
        return "media"
    if 9100 in p or 631 in p or "_ipp" in svc or "_printer" in svc or any(w in blob for w in ("printer", "tlačiare")):
        return "printer"
    if 554 in p or any(w in blob for w in ("camera", "ipcam", "hikvision", "dahua", "reolink")):
        return "camera"
    if any(w in blob for w in ("synology", "qnap", "nas", "diskstation")) or 5001 in p:
        return "server"
    if 62078 in p or "_apple-mobdev" in svc or any(w in blob for w in ("iphone", "ipad", "android", "galaxy", "pixel", "redmi", "xiaomi-")):
        return "phone"
    if p & {3389, 445, 139, 548, 5900, 22} or "_smb" in svc or "_afpovertcp" in svc or "_workstation" in svc:
        return "computer"
    if d.get("random_mac") and not p:
        return "phone"
    return "unknown"


class Scanner:
    def __init__(self, store):
        self.store = store
        self.lock = threading.Lock()
        self.thread = None
        self.progress = {"running": False, "phase": "", "done": 0, "total": 0, "error": None}
        self.devices = {d["id"]: d for d in store.data.get("devices", [])}
        self.meta = store.data.get("meta", {})

    # ------------------------------------------------------------- API
    def start(self, subnet=None):
        with self.lock:
            if self.progress["running"]:
                return False
            self.progress = {"running": True, "phase": "Pripravujem…", "done": 0, "total": 0, "error": None}
        self.thread = threading.Thread(target=self._run_safe, args=(subnet,), daemon=True)
        self.thread.start()
        return True

    def device_list(self):
        aliases = self.store.data.get("aliases", {})
        out = []
        for d in self.devices.values():
            d = dict(d)
            alias = aliases.get(d["id"]) or (d.get("mac") and aliases.get(d["mac"])) or aliases.get(d["ip"])
            d["alias"] = alias
            d["display_name"] = alias or d["name"]
            out.append(d)
        return sorted(out, key=lambda d: tuple(int(x) for x in d["ip"].split(".")))

    def get(self, did):
        return self.devices.get(did)

    # ------------------------------------------------------------- sken
    def _phase(self, phase, total=0):
        self.progress.update(phase=phase, done=0, total=total)

    def _tick(self):
        with self.lock:
            self.progress["done"] += 1

    def _run_safe(self, subnet):
        try:
            self._run(subnet)
        except Exception as e:  # noqa
            import traceback
            traceback.print_exc()
            self.progress["error"] = str(e)
        finally:
            self.progress["running"] = False
            self.progress["phase"] = "Hotovo"

    def _run(self, subnet):
        my_ip = netutil.local_ip()
        net = ipaddress.IPv4Network(subnet, strict=False) if subnet else netutil.detect_network(my_ip)
        if net.num_addresses > 4096:
            raise ValueError("Sieť %s je príliš veľká (max /20)" % net)
        gw = netutil.default_gateway()
        hosts = [str(h) for h in net.hosts()]
        started = time.time()
        fd_limit = netutil.raise_fd_limit()
        budget = max(32, fd_limit - 96)  # rezerva pre server a objavovanie
        ping_workers = max(8, min(128, budget // 4))  # ping = proces + rúry
        port_workers = max(16, min(200, budget // 2))

        # objavovanie cez multicast beží paralelne s pingovaním
        disc = {}

        def run_disc(name, fn):
            try:
                disc[name] = fn(my_ip)
            except Exception:  # noqa
                disc[name] = {}
        dthreads = [threading.Thread(target=run_disc, args=("ssdp", discovery.ssdp_discover), daemon=True),
                    threading.Thread(target=run_disc, args=("mdns", discovery.mdns_discover), daemon=True)]
        for t in dthreads:
            t.start()

        self._phase("Hľadám zariadenia v sieti %s" % net, len(hosts))
        alive = set()

        def probe(ip):
            ok = ip == my_ip or netutil.ping(ip)
            if not ok:
                for port in ALIVE_PORTS:
                    if netutil.tcp_probe(ip, port, 0.3):
                        ok = True
                        break
            self._tick()
            return ip, ok

        with ThreadPoolExecutor(ping_workers) as ex:
            for ip, ok in ex.map(probe, hosts):
                if ok:
                    alive.add(ip)
        for t in dthreads:
            t.join(6)
        ssdp, mdns = disc.get("ssdp", {}), disc.get("mdns", {})
        arp = netutil.arp_table()
        in_net = lambda ip: ipaddress.IPv4Address(ip) in net  # noqa: E731
        for ip in list(arp) + list(ssdp) + list(mdns):
            if in_net(ip) and ip not in (str(net.network_address), str(net.broadcast_address)):
                alive.add(ip)

        alive = sorted(alive, key=lambda ip: tuple(int(x) for x in ip.split(".")))
        jobs = [(ip, port) for ip in alive for port in PORTS]
        self._phase("Skenujem porty (%d zariadení)" % len(alive), len(jobs))
        open_ports = {ip: [] for ip in alive}

        def scan_port(job):
            ip, port = job
            r = netutil.tcp_probe(ip, port, 0.6)
            self._tick()
            return ip, port, r == "open"

        with ThreadPoolExecutor(port_workers) as ex:
            for ip, port, ok in ex.map(scan_port, jobs):
                if ok:
                    open_ports[ip].append(port)
        arp.update(netutil.arp_table())

        self._phase("Rozpoznávam zariadenia", len(alive))

        def identify(ip):
            ports = sorted(open_ports[ip])
            hints = {"ssdp": ssdp.get(ip) or {}, "mdns": mdns.get(ip) or {}}
            d = self._build(ip, ports, hints, arp.get(ip), ip == my_ip, ip == gw)
            self._tick()
            return d

        with ThreadPoolExecutor(max(4, min(32, budget // 8))) as ex:
            found = list(ex.map(identify, alive))

        # zlúčenie s predchádzajúcimi výsledkami (offline zariadenia ostávajú)
        now = time.time()
        new = {}
        for d in found:
            d["online"] = True
            d["last_seen"] = now
            old = self.devices.get(d["id"])
            d["first_seen"] = (old or {}).get("first_seen", now)
            d["new"] = old is None and bool(self.devices)
            new[d["id"]] = d
        for did, d in self.devices.items():
            if did not in new and ipaddress.IPv4Address(d["ip"]) in net:
                d = dict(d, online=False, new=False)
                if not any(x["ip"] == d["ip"] for x in new.values()):
                    new[did] = d
        self.devices = new
        self.meta = {"network": str(net), "gateway": gw, "self_ip": my_ip, "scanned_at": now,
                     "duration": round(now - started, 1)}
        with self.store.lock:
            self.store.data["devices"] = list(new.values())
            self.store.data["meta"] = self.meta
            self.store.save()

    def _build(self, ip, ports, hints, mac, is_self, is_gw):
        ssdp, mdns = hints["ssdp"], hints["mdns"]
        found = drivers.detect_all(ip, ports, hints)
        info = {}
        for _, i in found:
            for k, v in i.items():
                if v and k not in info:
                    info[k] = v
        if not mac and info.get("mac"):
            raw = str(info["mac"]).replace(":", "").replace("-", "").lower()
            if len(raw) == 12:
                mac = ":".join(raw[i:i + 2] for i in range(0, 12, 2))

        mdns_names = dict(mdns.get("names") or [])
        txt = mdns.get("txt") or {}
        mdns_friendly = txt.get("fn") or txt.get("n") or next(
            (n for s, n in mdns_names.items() if s.startswith(("_googlecast", "_airplay", "_companion-link",
                                                               "_hap", "_sonos", "_spotify", "_device-info"))), None) \
            or next(iter(mdns_names.values()), None)
        if mdns_friendly and "@" in mdns_friendly and mdns_names.get("_raop._tcp.local") == mdns_friendly:
            mdns_friendly = mdns_friendly.split("@", 1)[1]
        nb = discovery.netbios_name(ip) if (139 in ports or 445 in ports) else None
        rdns = netutil.reverse_dns(ip)
        if rdns and rdns.split(".")[0].replace("-", ".") == ip:
            rdns = None
        hostname = mdns.get("hostname") or (rdns.split(".")[0] if rdns else None) or nb

        vendor = info.get("vendor") or ssdp.get("manufacturer") or txt.get("mf") or txt.get("manufacturer")
        model = info.get("model") or ssdp.get("modelName") or txt.get("md") or txt.get("model") or txt.get("ty")
        name = (info.get("name") or mdns_friendly or ssdp.get("friendlyName") or nb or hostname)
        if is_self:
            name = name or "Tento počítač"
        if not name:
            name = " ".join(x for x in (vendor, model) if x) or ("Router" if is_gw else "Zariadenie .%s" % ip.split(".")[-1])

        d = {
            "id": mac or ip, "ip": ip, "mac": mac, "name": name, "hostname": hostname, "vendor": vendor,
            "model": model, "open_ports": ports,
            "ports": [{"port": p, "service": PORTS.get(p, str(p))} for p in ports],
            "mdns_services": sorted(s.replace(".local", "") for s in (mdns.get("services") or [])),
            "ssdp_type": ssdp.get("deviceType"), "ssdp_server": ssdp.get("server"),
            "is_self": is_self, "is_gateway": is_gw, "random_mac": netutil.is_random_mac(mac) if mac else False,
            "drivers": [{"key": k, "label": drivers.BY_KEY[k].label, "info": i} for k, i in found],
        }
        d["category"] = classify(d)
        for dk in (x["key"] for x in d["drivers"]):
            cat = drivers.BY_KEY[dk].category
            if cat in ("media", "server") and d["category"] in ("unknown", "computer"):
                d["category"] = cat
        d["controllable"] = bool(d["drivers"])
        d["links"] = [{"label": lbl, "url": "%s://%s%s/" % (sch, ip, "" if (p, sch) in ((80, "http"), (443, "https")) else ":%d" % p)}
                      for p, sch, lbl in WEB_PORTS if p in ports]
        if 32400 in ports:
            for l in d["links"]:
                if l["label"] == "Plex":
                    l["url"] += "web/"
        return d
