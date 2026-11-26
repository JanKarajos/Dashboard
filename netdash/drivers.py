"""Ovládače zariadení. Každý ovládač vie zariadenie rozpoznať, popísať jeho
ovládacie prvky (generický formát pre UI) a vykonať zmenu."""
import base64
import colorsys
import json
import re
import socket
import time
import urllib.parse

from . import netutil
from .netutil import get_json, http, hex_to_rgb, rgb_to_hex, xml_tag
from .wsclient import WebSocket, WSError


class ActionError(Exception):
    """Chyba so správou pre používateľa."""


# ------------------------------------------------------------ pomocníci pre UI

def T(id, label, value, group=None):
    return {"id": id, "type": "toggle", "label": label, "value": bool(value), "group": group}


def S(id, label, value, mn, mx, unit="", group=None, step=1):
    return {"id": id, "type": "slider", "label": label, "value": value, "min": mn, "max": mx,
            "unit": unit, "step": step, "group": group}


def C(id, label, value, group=None):
    return {"id": id, "type": "color", "label": label, "value": value, "group": group}


def B(id, label, group=None, icon=None):
    return {"id": id, "type": "button", "label": label, "group": group, "icon": icon}


def SEL(id, label, value, options, group=None):
    return {"id": id, "type": "select", "label": label, "value": value, "options": options, "group": group}


def SENS(id, label, value, unit="", group=None):
    return {"id": id, "type": "sensor", "label": label, "value": value, "unit": unit, "group": group}


def INFO(text, group=None, id="info"):
    return {"id": id, "type": "notice", "label": text, "group": group}


def INPUT(id, label, placeholder="", secret=False, group=None, button="Uložiť"):
    return {"id": id, "type": "input", "label": label, "placeholder": placeholder,
            "secret": secret, "group": group, "button": button}


def PAD(id, rows, group=None):
    return {"id": id, "type": "pad", "rows": rows, "group": group}


def as_int(v):
    return int(round(float(v)))


def as_bool(v):
    if isinstance(v, str):
        return v.lower() in ("1", "true", "on", "yes")
    return bool(v)


def must_json(url, timeout=3.0, headers=None):
    j = get_json(url, timeout=timeout, headers=headers)
    if j is None:
        raise ActionError("Zariadenie neodpovedá (%s)" % url.split("/")[2])
    return j


def call(method, url, body=None, headers=None, timeout=4.0):
    try:
        status, txt = http(method, url, body=body, headers=headers, timeout=timeout)
    except (OSError, ValueError) as e:
        raise ActionError("Zariadenie neodpovedá: %s" % e)
    if status == 401:
        raise ActionError("Zariadenie vyžaduje prihlásenie (401)")
    if status >= 400:
        raise ActionError("Zariadenie vrátilo chybu %s: %s" % (status, txt[:200]))
    return txt


class Driver:
    key = ""
    label = ""
    category = "smart"
    ports = ()          # aspoň jeden z týchto portov musí byť otvorený (prázdne = vždy skúsiť)
    hint_only = False   # detegovať len podľa hintov (SSDP/mDNS)

    def applicable(self, ports, hints):
        return not self.ports or any(p in ports for p in self.ports)

    def detect(self, ip, ports, hints):
        return None

    def controls(self, dev, store):
        return []

    def set(self, dev, store, cid, value):
        raise ActionError("Nepodporovaná akcia")


def _base(dev, port=None):
    port = port or dev.get("driver_info", {}).get("port") or 80
    scheme = "https" if port in (443, 8443) else "http"
    return "%s://%s:%d" % (scheme, dev["ip"], port)


def _http_ports(ports, prefer=(80, 8080, 8081, 443)):
    return [p for p in prefer if p in ports]


# ================================================================== Shelly

class Shelly(Driver):
    key = "shelly"
    label = "Shelly"
    ports = (80,)

    def detect(self, ip, ports, hints):
        j = get_json("http://%s/shelly" % ip)
        if not isinstance(j, dict) or "mac" not in j or not ({"type", "gen", "app", "model"} & set(j)):
            return None
        gen = int(j.get("gen") or 1)
        info = {"gen": gen, "vendor": "Shelly", "model": j.get("model") or j.get("type") or j.get("app"),
                "name": j.get("name"), "mac": j.get("mac"),
                "auth": bool(j.get("auth") or j.get("auth_en"))}
        if gen == 1 and not info["auth"]:
            st = get_json("http://%s/settings" % ip) or {}
            info["name"] = st.get("name") or info["name"]
            info["model"] = (st.get("device") or {}).get("type") or info["model"]
        if info.get("app"):
            info["model"] = "Shelly " + j["app"]
        return info

    def controls(self, dev, store):
        info = dev.get("driver_info", {})
        if info.get("auth"):
            return [INFO("Zariadenie má zapnuté prihlásenie – vypni ho v jeho webovom rozhraní, "
                         "alebo ho ovládaj cez Home Assistant.")]
        return self._gen1(dev) if info.get("gen", 1) == 1 else self._gen2(dev)

    def _gen1(self, dev):
        st = must_json(_base(dev) + "/status")
        out = []
        rollers = st.get("rollers") or []
        relays = [] if rollers else (st.get("relays") or [])
        meters = st.get("meters") or st.get("emeters") or []
        for i, r in enumerate(relays):
            g = "Výstup %d" % (i + 1) if len(relays) > 1 else None
            out.append(T("relay:%d:on" % i, "Napájanie", r.get("ison"), g))
            if i < len(meters) and "power" in meters[i]:
                out.append(SENS("relay:%d:p" % i, "Príkon", round(meters[i]["power"], 1), "W", g))
        for i, l in enumerate(st.get("lights") or []):
            g = "Svetlo %d" % (i + 1) if len(st["lights"]) > 1 else "Svetlo"
            out.append(T("light:%d:on" % i, "Zapnuté", l.get("ison"), g))
            if "brightness" in l:
                out.append(S("light:%d:bri" % i, "Jas", l["brightness"], 1, 100, "%", g))
            elif "gain" in l:
                out.append(S("light:%d:gain" % i, "Jas", l["gain"], 1, 100, "%", g))
            if l.get("mode") == "color" and "red" in l:
                out.append(C("light:%d:rgb" % i, "Farba", rgb_to_hex(l["red"], l["green"], l["blue"]), g))
        for i, r in enumerate(rollers):
            g = "Žalúzia %d" % (i + 1) if len(rollers) > 1 else "Žalúzia"
            out += [B("roller:%d:open" % i, "Otvoriť", g, "up"), B("roller:%d:stop" % i, "Stop", g, "stop"),
                    B("roller:%d:close" % i, "Zatvoriť", g, "down")]
            if r.get("positioning"):
                out.append(S("roller:%d:pos" % i, "Poloha", r.get("current_pos", 0), 0, 100, "%", g))
        if not relays and not rollers and meters and "power" in meters[0]:
            for i, m in enumerate(meters):
                out.append(SENS("meter:%d" % i, "Príkon %d" % (i + 1), round(m.get("power", 0), 1), "W"))
        tmp = st.get("tmp") or {}
        if tmp.get("tC") is not None:
            out.append(SENS("tmp", "Teplota", round(tmp["tC"], 1), "°C"))
        if (st.get("hum") or {}).get("value") is not None:
            out.append(SENS("hum", "Vlhkosť", st["hum"]["value"], "%"))
        return out or [INFO("Zariadenie nemá ovládateľné výstupy.")]

    def _gen2(self, dev):
        st = must_json(_base(dev) + "/rpc/Shelly.GetStatus")
        cfg = get_json(_base(dev) + "/rpc/Shelly.GetConfig") or {}
        out = []
        comps = sorted(st.keys(), key=lambda k: (k.split(":")[0], int(k.split(":")[1]) if k.count(":") == 1 and k.split(":")[1].isdigit() else 0))
        multi = {}
        for k in comps:
            multi[k.split(":")[0]] = multi.get(k.split(":")[0], 0) + 1
        for k in comps:
            if ":" not in k:
                continue
            kind, n = k.split(":", 1)
            s = st[k] or {}
            name = (cfg.get(k) or {}).get("name")
            kind_label = {"switch": "Výstup", "light": "Svetlo", "rgb": "RGB", "rgbw": "RGBW",
                          "cover": "Žalúzia", "cct": "Svetlo"}.get(kind)
            g = name or (("%s %d" % (kind_label, int(n) + 1)) if kind_label and multi[kind] > 1 else kind_label)
            if kind == "switch":
                out.append(T("%s:on" % k, "Napájanie", s.get("output"), g if g != "Výstup" else None))
                if "apower" in s:
                    out.append(SENS("%s:p" % k, "Príkon", round(s["apower"], 1), "W", g if g != "Výstup" else None))
            elif kind in ("light", "rgb", "rgbw", "cct"):
                out.append(T("%s:on" % k, "Zapnuté", s.get("output"), g))
                if "brightness" in s:
                    out.append(S("%s:bri" % k, "Jas", s["brightness"], 1, 100, "%", g))
                if kind in ("rgb", "rgbw") and s.get("rgb"):
                    out.append(C("%s:rgb" % k, "Farba", rgb_to_hex(*s["rgb"][:3]), g))
            elif kind == "cover":
                out += [B("%s:open" % k, "Otvoriť", g, "up"), B("%s:stop" % k, "Stop", g, "stop"),
                        B("%s:close" % k, "Zatvoriť", g, "down")]
                if s.get("current_pos") is not None:
                    out.append(S("%s:pos" % k, "Poloha", s["current_pos"], 0, 100, "%", g))
            elif kind == "temperature" and s.get("tC") is not None:
                out.append(SENS(k, "Teplota", round(s["tC"], 1), "°C"))
            elif kind == "humidity" and s.get("rh") is not None:
                out.append(SENS(k, "Vlhkosť", round(s["rh"]), "%"))
            elif kind in ("pm1", "em1") and s.get("apower") is not None:
                out.append(SENS(k, "Príkon", round(s["apower"], 1), "W"))
        return out or [INFO("Zariadenie nemá ovládateľné výstupy.")]

    def set(self, dev, store, cid, value):
        base = _base(dev)
        kind, n, attr = cid.split(":")
        if dev.get("driver_info", {}).get("gen", 1) == 1:
            if kind == "relay":
                call("GET", "%s/relay/%s?turn=%s" % (base, n, "on" if as_bool(value) else "off"))
            elif kind == "light":
                st = must_json(base + "/status")
                mode = ((st.get("lights") or [{}])[int(n)]).get("mode")
                ep = "color" if mode == "color" else ("white" if mode == "white" else "light")
                if attr == "on":
                    q = "turn=%s" % ("on" if as_bool(value) else "off")
                elif attr in ("bri", "gain"):
                    q = "turn=on&%s=%d" % ("brightness" if attr == "bri" else "gain", as_int(value))
                else:
                    r, g, b = hex_to_rgb(value)
                    q = "turn=on&red=%d&green=%d&blue=%d" % (r, g, b)
                call("GET", "%s/%s/%s?%s" % (base, ep, n, q))
            elif kind == "roller":
                if attr == "pos":
                    call("GET", "%s/roller/%s?go=to_pos&roller_pos=%d" % (base, n, as_int(value)))
                else:
                    call("GET", "%s/roller/%s?go=%s" % (base, n, attr))
            return
        comp = {"switch": "Switch", "light": "Light", "rgb": "RGB", "rgbw": "RGBW", "cct": "CCT",
                "cover": "Cover"}[kind]
        if kind == "cover":
            if attr == "pos":
                call("GET", "%s/rpc/Cover.GoToPosition?id=%s&pos=%d" % (base, n, as_int(value)))
            else:
                call("GET", "%s/rpc/Cover.%s?id=%s" % (base, attr.capitalize(), n))
            return
        if attr == "on":
            q = "on=%s" % ("true" if as_bool(value) else "false")
        elif attr == "bri":
            q = "on=true&brightness=%d" % as_int(value)
        else:
            q = "on=true&rgb=" + urllib.parse.quote(json.dumps(list(hex_to_rgb(value))))
        call("GET", "%s/rpc/%s.Set?id=%s&%s" % (base, comp, n, q))


# ================================================================== Tasmota

SENSOR_UNITS = {"Power": "W", "ApparentPower": "VA", "Voltage": "V", "Current": "A", "Today": "kWh",
                "Yesterday": "kWh", "Total": "kWh", "Temperature": "°C", "Humidity": "%", "Pressure": "hPa",
                "Illuminance": "lx", "CarbonDioxide": "ppm"}
SENSOR_LABELS = {"Power": "Príkon", "Voltage": "Napätie", "Current": "Prúd", "Today": "Dnes",
                 "Total": "Spolu", "Temperature": "Teplota", "Humidity": "Vlhkosť", "Pressure": "Tlak",
                 "Illuminance": "Osvetlenie", "CarbonDioxide": "CO₂", "Yesterday": "Včera"}


class Tasmota(Driver):
    key = "tasmota"
    label = "Tasmota"
    ports = (80,)

    def detect(self, ip, ports, hints):
        j = get_json("http://%s/cm?cmnd=Status%%200" % ip)
        if not isinstance(j, dict):
            return None
        if "WARNING" in j and "password" in str(j["WARNING"]).lower():
            return {"vendor": "Tasmota", "model": "Tasmota", "auth": True}
        if "Status" not in j:
            return None
        s = j["Status"]
        fn = s.get("FriendlyName")
        name = s.get("DeviceName") or (fn[0] if isinstance(fn, list) and fn else fn)
        fw = j.get("StatusFWR", {})
        return {"vendor": "Tasmota", "model": ("Tasmota %s" % fw.get("Version", "")).strip(),
                "hardware": fw.get("Hardware"), "name": name,
                "mac": (j.get("StatusNET") or {}).get("Mac")}

    def _cmd(self, dev, cmnd):
        txt = call("GET", "%s/cm?cmnd=%s" % (_base(dev), urllib.parse.quote(cmnd)))
        try:
            return json.loads(txt)
        except ValueError:
            return {}

    def controls(self, dev, store):
        if dev.get("driver_info", {}).get("auth"):
            return [INFO("Tasmota má nastavené heslo webového rozhrania – ovládanie cez dashboard "
                         "nie je možné, použi Home Assistant alebo heslo vypni.")]
        j = self._cmd(dev, "Status 0")
        sts = j.get("StatusSTS") or {}
        fn = (j.get("Status") or {}).get("FriendlyName") or []
        out = []
        pkeys = sorted(k for k in sts if re.match(r"^POWER\d*$", k))
        for k in pkeys:
            idx = int(k[5:] or 1)
            label = fn[idx - 1] if len(pkeys) > 1 and idx - 1 < len(fn) and fn[idx - 1] else (
                "Výstup %d" % idx if len(pkeys) > 1 else "Napájanie")
            out.append(T("power:" + k, label, sts[k] == "ON"))
        if "Dimmer" in sts:
            out.append(S("dimmer", "Jas", sts["Dimmer"], 0, 100, "%"))
        if "CT" in sts:
            out.append(S("ct", "Teplota farby", sts["CT"], 153, 500, " mired"))
        if "HSBColor" in sts and str(sts.get("Color", "")).strip():
            try:
                h, s_, b = [float(x) for x in sts["HSBColor"].split(",")]
                r, g, bl = colorsys.hsv_to_rgb(h / 360, s_ / 100, 1)
                out.append(C("color", "Farba", rgb_to_hex(r * 255, g * 255, bl * 255)))
            except ValueError:
                pass
        sns = j.get("StatusSNS") or {}
        count = 0
        for sec, vals in sns.items():
            if not isinstance(vals, dict):
                continue
            for k, v in vals.items():
                if isinstance(v, (int, float)) and k in SENSOR_UNITS and count < 8:
                    lbl = SENSOR_LABELS.get(k, k)
                    if sec != "ENERGY":
                        lbl = "%s (%s)" % (lbl, sec)
                    out.append(SENS("sns:%s:%s" % (sec, k), lbl, v, SENSOR_UNITS[k]))
                    count += 1
        return out or [INFO("Žiadne ovládateľné výstupy.")]

    def set(self, dev, store, cid, value):
        if cid.startswith("power:"):
            self._cmd(dev, "%s %s" % (cid[6:], "ON" if as_bool(value) else "OFF"))
        elif cid == "dimmer":
            self._cmd(dev, "Dimmer %d" % as_int(value))
        elif cid == "ct":
            self._cmd(dev, "CT %d" % as_int(value))
        elif cid == "color":
            self._cmd(dev, "Color %s" % value.lstrip("#").upper())
        else:
            raise ActionError("Neznámy prvok")


# ================================================================== WLED

class WLED(Driver):
    key = "wled"
    label = "WLED"
    ports = (80,)

    def detect(self, ip, ports, hints):
        j = get_json("http://%s/json/info" % ip)
        if not isinstance(j, dict) or not (j.get("brand") == "WLED" or ("leds" in j and "ver" in j)):
            return None
        return {"vendor": "WLED", "model": "WLED %s" % j.get("ver", ""), "name": j.get("name"),
                "mac": j.get("mac")}

    def controls(self, dev, store):
        j = must_json(_base(dev) + "/json")
        st = j.get("state") or {}
        seg = (st.get("seg") or [{}])[0]
        out = [T("on", "Zapnuté", st.get("on")), S("bri", "Jas", st.get("bri", 128), 1, 255)]
        col = (seg.get("col") or [[255, 255, 255]])[0]
        if isinstance(col, list) and len(col) >= 3:
            out.append(C("col", "Farba", rgb_to_hex(*col[:3])))
        effects = j.get("effects") or []
        if effects:
            out.append(SEL("fx", "Efekt", seg.get("fx", 0), [[i, n] for i, n in enumerate(effects)]))
        presets = get_json(_base(dev) + "/presets.json") or {}
        opts = [[int(k), v.get("n") or ("Predvoľba %s" % k)] for k, v in presets.items()
                if k.isdigit() and int(k) > 0 and isinstance(v, dict) and v]
        if opts:
            out.append(SEL("ps", "Predvoľba", st.get("ps", -1), [[-1, "—"]] + sorted(opts)))
        return out

    def set(self, dev, store, cid, value):
        if cid == "on":
            body = {"on": as_bool(value)}
        elif cid == "bri":
            body = {"on": True, "bri": as_int(value)}
        elif cid == "col":
            body = {"on": True, "seg": [{"id": 0, "col": [list(hex_to_rgb(value))]}]}
        elif cid == "fx":
            body = {"on": True, "seg": [{"id": 0, "fx": as_int(value)}]}
        elif cid == "ps":
            body = {"ps": as_int(value)}
        else:
            raise ActionError("Neznámy prvok")
        call("POST", _base(dev) + "/json/state", body=body)


# ================================================================== Philips Hue

class Hue(Driver):
    key = "hue"
    label = "Philips Hue"
    ports = (80, 443)

    def detect(self, ip, ports, hints):
        j = get_json("http://%s/api/config" % ip)
        if not isinstance(j, dict) or "bridgeid" not in j:
            return None
        return {"vendor": "Philips Hue", "model": "Hue Bridge %s" % (j.get("modelid") or ""),
                "name": j.get("name"), "bridgeid": j["bridgeid"], "mac": j.get("mac")}

    def _skey(self, dev):
        return "hue:" + dev.get("driver_info", {}).get("bridgeid", dev["ip"])

    def controls(self, dev, store):
        user = store.get("secrets", self._skey(dev))
        pair = [INFO("Dashboard ešte nie je spárovaný s Hue mostom. Stlač okrúhle tlačidlo na moste "
                     "a do 30 sekúnd klikni na Spárovať."), B("pair", "Spárovať", icon="link")]
        if not user:
            return pair
        lights = must_json("%s/api/%s/lights" % (_base(dev, 80), user))
        if isinstance(lights, list):  # chyba – neautorizovaný používateľ
            store.put("secrets", self._skey(dev), None)
            return pair
        out = [T("group:0:on", "Všetky svetlá",
                 any((l.get("state") or {}).get("on") for l in lights.values()), "Celý dom")]
        groups = get_json("%s/api/%s/groups" % (_base(dev, 80), user)) or {}
        if isinstance(groups, dict):
            for gid, g in sorted(groups.items(), key=lambda x: x[1].get("name", "")):
                if g.get("type") in ("Room", "Zone"):
                    out.append(T("group:%s:on" % gid, g.get("name", gid),
                                 (g.get("state") or {}).get("any_on"), "Miestnosti"))
        for lid, l in sorted(lights.items(), key=lambda x: x[1].get("name", "")):
            st = l.get("state") or {}
            g = l.get("name", "Svetlo " + lid)
            if not st.get("reachable", True):
                out.append(INFO("Svetlo je nedostupné (vypnuté vypínačom?)", g, id="light:%s:na" % lid))
                continue
            out.append(T("light:%s:on" % lid, "Zapnuté", st.get("on"), g))
            if "bri" in st:
                out.append(S("light:%s:bri" % lid, "Jas", st["bri"], 1, 254, "", g))
            if "hue" in st and "sat" in st:
                r, gg, b = colorsys.hsv_to_rgb(st["hue"] / 65535, st["sat"] / 254, 1)
                out.append(C("light:%s:rgb" % lid, "Farba", rgb_to_hex(r * 255, gg * 255, b * 255), g))
            if "ct" in st and "hue" not in st:
                out.append(S("light:%s:ct" % lid, "Teplota farby", st["ct"], 153, 454, " mired", g))
        return out

    def set(self, dev, store, cid, value):
        base = _base(dev, 80)
        if cid == "pair":
            txt = call("POST", base + "/api", body={"devicetype": "netdash#dashboard"})
            try:
                res = json.loads(txt)[0]
            except (ValueError, IndexError, KeyError):
                raise ActionError("Neočakávaná odpoveď mosta")
            if "success" in res:
                store.put("secrets", self._skey(dev), res["success"]["username"])
                return
            raise ActionError("Najprv stlač tlačidlo na Hue moste a potom do 30 s klikni na Spárovať.")
        user = store.get("secrets", self._skey(dev))
        if not user:
            raise ActionError("Most nie je spárovaný")
        kind, n, attr = cid.split(":")
        if attr == "on":
            body = {"on": as_bool(value)}
        elif attr == "bri":
            body = {"on": True, "bri": as_int(value)}
        elif attr == "ct":
            body = {"on": True, "ct": as_int(value)}
        else:
            r, g, b = hex_to_rgb(value)
            h, s, _v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            body = {"on": True, "hue": int(h * 65535), "sat": int(s * 254)}
        path = "groups/%s/action" % n if kind == "group" else "lights/%s/state" % n
        call("PUT", "%s/api/%s/%s" % (base, user, path), body=body)


# ================================================================== Yeelight

class Yeelight(Driver):
    key = "yeelight"
    label = "Yeelight"
    ports = (55443,)

    def applicable(self, ports, hints):
        return 55443 in ports or bool((hints.get("ssdp") or {}).get("yeelight"))

    def _cmd(self, ip, method, params, timeout=2.5):
        try:
            s = socket.create_connection((ip, 55443), timeout=timeout)
        except OSError as e:
            raise ActionError("Yeelight neodpovedá (je zapnutý „LAN Control“?): %s" % e)
        try:
            s.sendall((json.dumps({"id": 1, "method": method, "params": params}) + "\r\n").encode())
            buf = b""
            end = time.time() + timeout
            while time.time() < end:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
                for line in buf.split(b"\r\n"):
                    try:
                        msg = json.loads(line)
                    except ValueError:
                        continue
                    if msg.get("id") == 1:
                        if "error" in msg:
                            raise ActionError("Yeelight: %s" % msg["error"].get("message"))
                        return msg.get("result")
        except socket.timeout:
            pass
        finally:
            s.close()
        raise ActionError("Yeelight neodpovedal")

    def detect(self, ip, ports, hints):
        y = (hints.get("ssdp") or {}).get("yeelight") or {}
        if 55443 not in ports and not y:
            return None
        try:
            res = self._cmd(ip, "get_prop", ["power", "name"])
        except ActionError:
            if not y:
                return None
            res = None
        return {"vendor": "Yeelight", "model": "Yeelight %s" % (y.get("model") or ""),
                "name": (res[1] if res and len(res) > 1 and res[1] else None) or y.get("name")}

    def controls(self, dev, store):
        p = self._cmd(dev["ip"], "get_prop", ["power", "bright", "rgb", "ct", "color_mode"])
        out = [T("power", "Zapnuté", p[0] == "on")]
        if p[1]:
            out.append(S("bright", "Jas", int(p[1]), 1, 100, "%"))
        if p[2]:
            v = int(p[2])
            out.append(C("rgb", "Farba", rgb_to_hex(v >> 16, (v >> 8) & 255, v & 255)))
        if p[3]:
            out.append(S("ct", "Teplota farby", int(p[3]), 1700, 6500, " K", step=100))
        return out

    def set(self, dev, store, cid, value):
        ip = dev["ip"]
        if cid == "power":
            self._cmd(ip, "set_power", ["on" if as_bool(value) else "off", "smooth", 300])
            return
        self._cmd(ip, "set_power", ["on", "smooth", 300])
        if cid == "bright":
            self._cmd(ip, "set_bright", [max(1, as_int(value)), "smooth", 300])
        elif cid == "rgb":
            r, g, b = hex_to_rgb(value)
            self._cmd(ip, "set_rgb", [(r << 16) + (g << 8) + b or 1, "smooth", 300])
        elif cid == "ct":
            self._cmd(ip, "set_ct_abx", [as_int(value), "smooth", 300])


# ================================================================== Roku

ROKU_PAD = [
    [["Power", "⏻"], ["Home", "⌂"], ["Back", "↩"]],
    [None, ["Up", "▲"], None],
    [["Left", "◀"], ["Select", "OK"], ["Right", "▶"]],
    [None, ["Down", "▼"], None],
    [["Rev", "⏪"], ["Play", "⏯"], ["Fwd", "⏩"]],
    [["VolumeDown", "🔉"], ["VolumeMute", "🔇"], ["VolumeUp", "🔊"]],
]


class Roku(Driver):
    key = "roku"
    label = "Roku"
    category = "media"
    ports = (8060,)

    def detect(self, ip, ports, hints):
        x = netutil.get_text("http://%s:8060/query/device-info" % ip)
        if not x or "<device-info" not in x:
            return None
        return {"vendor": xml_tag(x, "vendor-name") or "Roku", "model": xml_tag(x, "model-name"),
                "name": xml_tag(x, "user-device-name") or xml_tag(x, "friendly-device-name"),
                "port": 8060}

    def controls(self, dev, store):
        out = [PAD("key", ROKU_PAD, "Ovládač")]
        x = netutil.get_text("http://%s:8060/query/apps" % dev["ip"]) or ""
        apps = re.findall(r'<app id="(\w+)"[^>]*>(.*?)</app>', x)
        if apps:
            out.append(SEL("app", "Spustiť aplikáciu", "", [["", "—"]] + [[a, n] for a, n in apps]))
        return out

    def set(self, dev, store, cid, value):
        if cid == "key":
            call("POST", "http://%s:8060/keypress/%s" % (dev["ip"], urllib.parse.quote(str(value))), body=b"")
        elif cid == "app" and value:
            call("POST", "http://%s:8060/launch/%s" % (dev["ip"], urllib.parse.quote(str(value))), body=b"")


# ================================================================== Samsung Tizen TV

SAMSUNG_PAD = [
    [["KEY_POWER", "⏻"], ["KEY_HOME", "⌂"], ["KEY_RETURN", "↩"]],
    [["KEY_SOURCE", "Zdroj"], ["KEY_UP", "▲"], ["KEY_MENU", "Menu"]],
    [["KEY_LEFT", "◀"], ["KEY_ENTER", "OK"], ["KEY_RIGHT", "▶"]],
    [["KEY_CHDOWN", "CH−"], ["KEY_DOWN", "▼"], ["KEY_CHUP", "CH+"]],
    [["KEY_REWIND", "⏪"], ["KEY_PLAY", "▶"], ["KEY_PAUSE", "⏸"]],
    [["KEY_VOLDOWN", "🔉"], ["KEY_MUTE", "🔇"], ["KEY_VOLUP", "🔊"]],
]


class SamsungTV(Driver):
    key = "samsung"
    label = "Samsung TV"
    category = "media"
    ports = (8001, 8002)

    def detect(self, ip, ports, hints):
        j = get_json("http://%s:8001/api/v2/" % ip)
        if not isinstance(j, dict) or "device" not in j:
            return None
        d = j["device"]
        return {"vendor": "Samsung", "model": d.get("modelName") or j.get("type"),
                "name": d.get("name") or j.get("name"), "mac": d.get("wifiMac"),
                "token_auth": d.get("TokenAuthSupport") in ("true", True)}

    def controls(self, dev, store):
        out = [PAD("key", SAMSUNG_PAD, "Ovládač")]
        if not store.get("secrets", "samsung:" + dev["ip"]):
            out.insert(0, INFO("Pri prvom stlačení tlačidla potvrď na TV prístup pre „Dashboard“."))
        return out

    def set(self, dev, store, cid, value):
        name = base64.b64encode(b"Dashboard").decode()
        skey = "samsung:" + dev["ip"]
        token = store.get("secrets", skey)
        path = "/api/v2/channels/samsung.remote.control?name=" + name
        if token:
            path += "&token=" + token
        try:
            secure = 8002 in dev.get("open_ports", []) or bool(dev.get("driver_info", {}).get("token_auth"))
            ws = WebSocket(dev["ip"], 8002 if secure else 8001, path, secure=secure, timeout=20)
            with ws:
                while True:
                    msg = ws.recv()
                    if isinstance(msg, dict) and msg.get("event") == "ms.channel.connect":
                        tok = (msg.get("data") or {}).get("token")
                        if tok and tok != token:
                            store.put("secrets", skey, tok)
                        break
                    if isinstance(msg, dict) and msg.get("event") == "ms.channel.unauthorized":
                        raise ActionError("TV odmietla prístup – povoľ ho v Nastavenia → Pripojené zariadenia.")
                ws.send({"method": "ms.remote.control", "params": {
                    "Cmd": "Click", "DataOfCmd": str(value), "Option": "false", "TypeOfRemote": "SendRemoteKey"}})
                time.sleep(0.15)
        except (OSError, WSError) as e:
            raise ActionError("Spojenie s TV zlyhalo: %s" % e)


# ================================================================== LG webOS TV

LG_PERMISSIONS = [
    "LAUNCH", "LAUNCH_WEBAPP", "APP_TO_APP", "CONTROL_AUDIO", "CONTROL_DISPLAY",
    "CONTROL_INPUT_MEDIA_PLAYBACK", "CONTROL_INPUT_TV", "CONTROL_POWER", "READ_APP_STATUS",
    "READ_CURRENT_CHANNEL", "READ_INPUT_DEVICE_LIST", "READ_INSTALLED_APPS", "READ_TV_CHANNEL_LIST",
    "READ_RUNNING_APPS", "READ_POWER_STATE", "CONTROL_TV_SCREEN", "CONTROL_MOUSE_AND_KEYBOARD",
    "READ_NOTIFICATIONS", "WRITE_NOTIFICATION_TOAST", "CONTROL_INPUT_JOYSTICK",
]


class LGWebOS(Driver):
    key = "lgwebos"
    label = "LG webOS TV"
    category = "media"
    ports = (3000, 3001)

    def detect(self, ip, ports, hints):
        ssdp = hints.get("ssdp") or {}
        blob = " ".join(str(ssdp.get(k) or "") for k in ("server", "manufacturer", "modelName", "friendlyName"))
        if "webos" not in blob.lower() and "lg electronics" not in blob.lower():
            return None
        return {"vendor": "LG", "model": ssdp.get("modelName") or "webOS TV", "name": ssdp.get("friendlyName")}

    def _session(self, dev, store, pairing_ok=False):
        skey = "lg:" + dev["ip"]
        key = store.get("secrets", skey)
        ws = None
        for port, secure in ((3001, True), (3000, False)):
            try:
                ws = WebSocket(dev["ip"], port, "/", secure=secure, timeout=4 if key else 60)
                break
            except (OSError, WSError):
                ws = None
        if not ws:
            raise ActionError("TV neodpovedá (je zapnutý?)")
        payload = {"forcePairing": False, "pairingType": "PROMPT",
                   "manifest": {"manifestVersion": 1, "appVersion": "1.0", "permissions": LG_PERMISSIONS}}
        if key:
            payload["client-key"] = key
        elif not pairing_ok:
            ws.close()
            return None
        ws.send({"type": "register", "id": "reg0", "payload": payload})
        try:
            while True:
                msg = ws.recv()
                if not isinstance(msg, dict):
                    continue
                if msg.get("type") == "registered":
                    ck = (msg.get("payload") or {}).get("client-key")
                    if ck and ck != key:
                        store.put("secrets", skey, ck)
                    return ws
                if msg.get("type") == "error":
                    ws.close()
                    store.put("secrets", skey, None)
                    raise ActionError("TV odmietla párovanie: %s" % msg.get("error"))
        except (OSError, WSError) as e:
            ws.close()
            raise ActionError("Párovanie s TV zlyhalo: %s" % e)

    def _req(self, ws, uri, payload=None, n=[0]):
        n[0] += 1
        rid = "r%d" % n[0]
        ws.send({"type": "request", "id": rid, "uri": uri, "payload": payload or {}})
        while True:
            msg = ws.recv()
            if isinstance(msg, dict) and msg.get("id") == rid:
                return msg.get("payload") or {}

    def controls(self, dev, store):
        if not store.get("secrets", "lg:" + dev["ip"]):
            return [INFO("Klikni Spárovať a na TV potvrď žiadosť ovládačom."), B("pair", "Spárovať", icon="link")]
        ws = self._session(dev, store)
        if ws is None:
            return [B("pair", "Spárovať", icon="link")]
        try:
            vol = self._req(ws, "ssap://audio/getVolume")
            apps = self._req(ws, "ssap://com.webos.applicationManager/listLaunchPoints").get("launchPoints", [])
            inputs = self._req(ws, "ssap://tv/getExternalInputList").get("devices", [])
        except (OSError, WSError) as e:
            raise ActionError("Komunikácia s TV zlyhala: %s" % e)
        finally:
            ws.close()
        volume = vol.get("volume", (vol.get("volumeStatus") or {}).get("volume", 0))
        muted = vol.get("muted", (vol.get("volumeStatus") or {}).get("muteStatus", False))
        out = [S("volume", "Hlasitosť", volume, 0, 100), T("mute", "Stlmiť", muted),
               B("off", "Vypnúť TV", icon="power"), B("chdown", "Kanál −"), B("chup", "Kanál +"),
               B("play", "Play", icon="play"), B("pause", "Pauza", icon="pause")]
        if apps:
            out.append(SEL("app", "Aplikácia", "", [["", "—"]] + sorted([[a["id"], a.get("title", a["id"])] for a in apps], key=lambda x: x[1])))
        if inputs:
            out.append(SEL("input", "Vstup", "", [["", "—"]] + [[i["id"], i.get("label", i["id"])] for i in inputs]))
        return out

    def set(self, dev, store, cid, value):
        ws = self._session(dev, store, pairing_ok=(cid == "pair"))
        if ws is None:
            raise ActionError("TV nie je spárovaná")
        try:
            if cid == "pair":
                return
            uri, payload = {
                "volume": ("ssap://audio/setVolume", {"volume": as_int(value)}),
                "mute": ("ssap://audio/setMute", {"mute": as_bool(value)}),
                "off": ("ssap://system/turnOff", {}),
                "chup": ("ssap://tv/channelUp", {}),
                "chdown": ("ssap://tv/channelDown", {}),
                "play": ("ssap://media.controls/play", {}),
                "pause": ("ssap://media.controls/pause", {}),
                "app": ("ssap://system.launcher/launch", {"id": value}),
                "input": ("ssap://tv/switchInput", {"inputId": value}),
            }[cid]
            if cid in ("app", "input") and not value:
                return
            self._req(ws, uri, payload)
        except (OSError, WSError) as e:
            raise ActionError("Komunikácia s TV zlyhala: %s" % e)
        finally:
            ws.close()


# ================================================================== UPnP / DLNA (Sonos, TV, receivery)

class UPnPRenderer(Driver):
    key = "upnp"
    label = "UPnP/DLNA prehrávač"
    category = "media"
    ports = ()

    def applicable(self, ports, hints):
        s = hints.get("ssdp") or {}
        return "RenderingControl" in (s.get("description_xml") or "")

    def detect(self, ip, ports, hints):
        s = hints.get("ssdp") or {}
        xml = s.get("description_xml") or ""
        loc = s.get("description_url")
        svcs = {}
        for block in re.findall(r"<service>(.*?)</service>", xml, re.S):
            st = xml_tag(block, "serviceType") or ""
            cu = xml_tag(block, "controlURL")
            if not cu:
                continue
            url = urllib.parse.urljoin(loc, cu)
            for name in ("RenderingControl", "AVTransport"):
                if ":%s:" % name in st and name not in svcs:
                    svcs[name] = {"url": url, "type": st}
        if "RenderingControl" not in svcs:
            return None
        manu = s.get("manufacturer") or ""
        name = s.get("friendlyName")
        if "sonos" in manu.lower():
            room = xml_tag(xml, "roomName")
            name = room or name
        return {"vendor": manu, "model": s.get("modelName"), "name": name, "services": svcs}

    def _soap(self, dev, svc, action, args=""):
        s = dev["driver_info"]["services"].get(svc)
        if not s:
            raise ActionError("Zariadenie nepodporuje %s" % svc)
        body = ('<?xml version="1.0" encoding="utf-8"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
                's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:%s xmlns:u="%s">'
                "<InstanceID>0</InstanceID>%s</u:%s></s:Body></s:Envelope>") % (action, s["type"], args, action, )
        try:
            status, txt = http("POST", s["url"], body=body, timeout=4, headers={
                "Content-Type": 'text/xml; charset="utf-8"', "SOAPACTION": '"%s#%s"' % (s["type"], action)})
        except OSError as e:
            raise ActionError("Zariadenie neodpovedá: %s" % e)
        if status >= 400:
            code = xml_tag(txt, "errorCode")
            raise ActionError("Akcia %s zlyhala (UPnP chyba %s)" % (action, code or status))
        return txt

    def controls(self, dev, store):
        out = []
        vol = xml_tag(self._soap(dev, "RenderingControl", "GetVolume", "<Channel>Master</Channel>"), "CurrentVolume")
        if vol is not None:
            out.append(S("volume", "Hlasitosť", int(vol), 0, 100))
        try:
            mute = xml_tag(self._soap(dev, "RenderingControl", "GetMute", "<Channel>Master</Channel>"), "CurrentMute")
            out.append(T("mute", "Stlmiť", mute == "1"))
        except ActionError:
            pass
        if "AVTransport" in dev["driver_info"]["services"]:
            try:
                state = xml_tag(self._soap(dev, "AVTransport", "GetTransportInfo"), "CurrentTransportState")
                labels = {"PLAYING": "Hrá", "PAUSED_PLAYBACK": "Pozastavené", "STOPPED": "Zastavené",
                          "NO_MEDIA_PRESENT": "Nič nehrá", "TRANSITIONING": "Načítava"}
                out.insert(0, SENS("state", "Stav", labels.get(state, state)))
            except ActionError:
                pass
            out += [B("Previous", "Predch.", icon="prev"), B("Play", "Play", icon="play"),
                    B("Pause", "Pauza", icon="pause"), B("Next", "Ďalšia", icon="next")]
        return out

    def set(self, dev, store, cid, value):
        if cid == "volume":
            self._soap(dev, "RenderingControl", "SetVolume",
                       "<Channel>Master</Channel><DesiredVolume>%d</DesiredVolume>" % as_int(value))
        elif cid == "mute":
            self._soap(dev, "RenderingControl", "SetMute",
                       "<Channel>Master</Channel><DesiredMute>%d</DesiredMute>" % (1 if as_bool(value) else 0))
        elif cid == "Play":
            self._soap(dev, "AVTransport", "Play", "<Speed>1</Speed>")
        elif cid in ("Pause", "Next", "Previous", "Stop"):
            self._soap(dev, "AVTransport", cid)


# ================================================================== Home Assistant

HA_DOMAINS = {
    "light": "Svetlá", "switch": "Vypínače", "fan": "Ventilátory", "cover": "Žalúzie a brány",
    "climate": "Kúrenie / klíma", "media_player": "Médiá", "lock": "Zámky", "vacuum": "Vysávače",
    "scene": "Scény", "script": "Skripty", "input_boolean": "Prepínače", "humidifier": "Zvlhčovače",
    "siren": "Sirény", "button": "Tlačidlá",
}


class HomeAssistant(Driver):
    key = "homeassistant"
    label = "Home Assistant"
    category = "server"
    ports = (8123,)

    def detect(self, ip, ports, hints):
        m = get_json("http://%s:8123/manifest.json" % ip)
        if isinstance(m, dict) and "home assistant" in (m.get("name") or "").lower():
            return {"vendor": "Home Assistant", "model": "Home Assistant", "name": "Home Assistant", "port": 8123}
        return None

    def _hdr(self, token):
        return {"Authorization": "Bearer " + token}

    def controls(self, dev, store):
        skey = "ha:" + dev["ip"]
        token = store.get("secrets", skey)
        ask = [INFO("Vytvor v Home Assistant token: Profil → Zabezpečenie → Dlhodobé prístupové tokeny "
                    "→ Vytvoriť token, a vlož ho sem. Cez HA ovládaš aj Tuya, Xiaomi, Zigbee a ďalšie."),
               INPUT("token", "Prístupový token", "eyJhbGciOi…", secret=True)]
        if not token:
            return ask
        try:
            status, txt = http("GET", _base(dev, 8123) + "/api/states", headers=self._hdr(token), timeout=6)
        except OSError as e:
            raise ActionError("Home Assistant neodpovedá: %s" % e)
        if status == 401:
            store.put("secrets", skey, None)
            return [INFO("Token bol odmietnutý.")] + ask
        states = json.loads(txt)
        out = []
        hidden = set(store.get("settings", "ha_hidden", []) or [])
        for e in sorted(states, key=lambda s: (list(HA_DOMAINS).index(s["entity_id"].split(".")[0])
                                               if s["entity_id"].split(".")[0] in HA_DOMAINS else 99,
                                               (s.get("attributes") or {}).get("friendly_name", s["entity_id"]).lower())):
            eid = e["entity_id"]
            dom = eid.split(".")[0]
            if dom not in HA_DOMAINS or eid in hidden or e.get("state") == "unavailable":
                continue
            a = e.get("attributes") or {}
            name = a.get("friendly_name") or eid
            g = HA_DOMAINS[dom]
            st = e.get("state")
            pre = "ha|%s|" % eid
            if dom in ("light", "switch", "fan", "input_boolean", "humidifier", "siren"):
                out.append(T(pre + "on", name, st == "on", g))
                if dom == "light" and st == "on" and a.get("brightness") is not None:
                    out.append(S(pre + "bri", "↳ jas", a["brightness"], 1, 255, "", g))
                if dom == "light" and st == "on" and a.get("rgb_color"):
                    out.append(C(pre + "rgb", "↳ farba", rgb_to_hex(*a["rgb_color"]), g))
            elif dom == "cover":
                out += [SENS(pre + "st", name, {"open": "otvorené", "closed": "zatvorené", "opening": "otvára sa",
                                                "closing": "zatvára sa"}.get(st, st), "", g),
                        B(pre + "open", "Otvoriť", g, "up"), B(pre + "stop", "Stop", g, "stop"),
                        B(pre + "close", "Zatvoriť", g, "down")]
            elif dom == "lock":
                out.append(T(pre + "lock", "%s (zamknuté)" % name, st == "locked", g))
            elif dom == "media_player":
                out.append(T(pre + "on", name, st not in ("off", "standby", "unavailable"), g))
                if a.get("volume_level") is not None:
                    out.append(S(pre + "vol", "↳ hlasitosť", round(a["volume_level"] * 100), 0, 100, "%", g))
                if st not in ("off", "standby"):
                    out.append(B(pre + "playpause", "↳ Play/Pauza", g, "play"))
            elif dom == "climate":
                cur = a.get("current_temperature")
                if cur is not None:
                    out.append(SENS(pre + "cur", "%s – aktuálne" % name, cur, "°C", g))
                if a.get("temperature") is not None:
                    out.append(S(pre + "temp", "%s – cieľ" % name, a["temperature"], a.get("min_temp", 7),
                                 a.get("max_temp", 35), "°C", g, step=a.get("target_temp_step", 0.5)))
            elif dom in ("scene", "script", "button"):
                out.append(B(pre + "run", name, g, "play"))
            elif dom == "vacuum":
                out += [SENS(pre + "st", name, st, "", g), B(pre + "start", "Štart", g, "play"),
                        B(pre + "dock", "Domov", g, "home")]
        return out or [INFO("V Home Assistant sa nenašli ovládateľné entity.")]

    def set(self, dev, store, cid, value):
        skey = "ha:" + dev["ip"]
        if cid == "token":
            token = str(value or "").strip()
            status, _ = http("GET", _base(dev, 8123) + "/api/", headers=self._hdr(token), timeout=5)
            if status != 200:
                raise ActionError("Token nefunguje (HTTP %s)" % status)
            store.put("secrets", skey, token)
            return
        token = store.get("secrets", skey)
        if not token:
            raise ActionError("Chýba token")
        _, eid, attr = cid.split("|")
        dom = eid.split(".")[0]
        data = {"entity_id": eid}
        on = as_bool(value)
        svc = None
        if attr == "on":
            svc = "turn_on" if on else "turn_off"
        elif attr == "bri":
            svc, data["brightness"] = "turn_on", as_int(value)
        elif attr == "rgb":
            svc, data["rgb_color"] = "turn_on", list(hex_to_rgb(value))
        elif attr in ("open", "close", "stop"):
            svc = attr + "_cover"
        elif attr == "lock":
            svc = "lock" if on else "unlock"
        elif attr == "vol":
            svc, data["volume_level"] = "volume_set", as_int(value) / 100
        elif attr == "playpause":
            svc = "media_play_pause"
        elif attr == "temp":
            svc, data["temperature"] = "set_temperature", float(value)
        elif attr == "run":
            svc = "press" if dom == "button" else "turn_on"
        elif attr == "start":
            svc = "start"
        elif attr == "dock":
            svc = "return_to_base"
        if not svc:
            raise ActionError("Neznáma akcia")
        call("POST", "%s/api/services/%s/%s" % (_base(dev, 8123), dom, svc), body=data,
             headers=self._hdr(token), timeout=8)


# ================================================================== registrácia

DRIVERS = [Shelly(), Tasmota(), WLED(), Hue(), Yeelight(), Roku(), SamsungTV(), LGWebOS(),
           HomeAssistant(), UPnPRenderer()]
BY_KEY = {d.key: d for d in DRIVERS}


def detect_all(ip, ports, hints):
    """Vráti zoznam (driver_key, info) pre všetky ovládače, ktoré zariadenie rozpoznali."""
    found = []
    http_drivers = ("shelly", "tasmota", "wled", "hue")
    for d in DRIVERS:
        if found and d.key in http_drivers and found[0][0] in http_drivers:
            continue  # jedno HTTP zariadenie = jeden typ
        if not d.applicable(ports, hints):
            continue
        try:
            info = d.detect(ip, ports, hints)
        except Exception:  # noqa – detekcia nesmie zhodiť sken
            info = None
        if info:
            found.append((d.key, info))
    return found
