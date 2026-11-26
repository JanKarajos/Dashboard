"""Ukážkový režim (--demo): vymyslené zariadenia na vyskúšanie dashboardu bez siete."""
import copy
import time

from . import drivers as D
from .scanner import PORTS, classify

_RAW = [
    ("192.168.1.1", "a4:91:b1:10:00:01", "Router", "TP-Link", "Archer AX55", [53, 80, 443, 1900], [], {"is_gateway": True}),
    ("192.168.1.10", "3c:22:fb:00:00:10", "Janov MacBook", "Apple", "MacBookPro18,3", [22, 445, 548, 5900, 7000], ["_airplay._tcp", "_smb._tcp"], {"is_self": True}),
    ("192.168.1.12", "f8:ff:c2:00:00:12", "PC-OBYVACKA", "Microsoft", "Windows", [135, 139, 445, 3389], [], {}),
    ("192.168.1.20", "c8:c9:a3:00:00:20", "Zásuvka – kávovar", "Shelly", "Shelly Plus Plug S", [80], ["_shelly._tcp", "_http._tcp"], {}, "shelly"),
    ("192.168.1.21", "e8:db:84:00:00:21", "Žalúzie spálňa", "Shelly", "Shelly 2PM (cover)", [80], ["_shelly._tcp"], {}, "shellycover"),
    ("192.168.1.22", "84:f3:eb:00:00:22", "Sonoff – bojler", "Tasmota", "Tasmota 14.2.0", [80], ["_http._tcp"], {}, "tasmota"),
    ("192.168.1.23", "c4:5b:be:00:00:23", "LED pás obývačka", "WLED", "WLED 0.15.0", [80], ["_wled._tcp"], {}, "wled"),
    ("192.168.1.24", "ec:b5:fa:00:00:24", "Hue Bridge", "Philips Hue", "BSB002", [80, 443], ["_hue._tcp"], {}, "hue"),
    ("192.168.1.25", "04:cf:8c:00:00:25", "Lampa pri posteli", "Yeelight", "Yeelight color4", [55443], [], {}, "yeelight"),
    ("192.168.1.30", "64:e4:a5:00:00:30", "LG OLED obývačka", "LG", "OLED55C3", [3000, 3001, 1900], ["_airplay._tcp"], {}, "lgwebos"),
    ("192.168.1.33", "70:af:24:00:00:33", "Philips TV obývačka", "Philips", "55PUS8507/12", [1925, 1926], [], {}, "philips"),
    ("192.168.1.31", "48:a6:b8:00:00:31", "Sonos Kuchyňa", "Sonos, Inc.", "Sonos One", [1400], ["_sonos._tcp", "_spotify-connect._tcp"], {}, "upnp"),
    ("192.168.1.32", "f4:f5:d8:00:00:32", "Chromecast spálňa", "Google", "Chromecast", [8008, 8009], ["_googlecast._tcp"], {}),
    ("192.168.1.40", "b8:27:eb:00:00:40", "Home Assistant", "Home Assistant", "Home Assistant", [22, 8123], ["_home-assistant._tcp"], {}, "homeassistant"),
    ("192.168.1.41", "00:11:32:00:00:41", "DiskStation", "Synology", "DS220+", [80, 443, 445, 5000, 5001], ["_smb._tcp"], {}),
    ("192.168.1.50", "3c:2a:f4:00:00:50", "HP LaserJet", "HP", "LaserJet M110we", [80, 631, 9100], ["_ipp._tcp"], {}),
    ("192.168.1.60", "9c:8e:cd:00:00:60", "Kamera vchod", "Hikvision", "DS-2CD1043", [80, 554], [], {}),
    ("192.168.1.101", "5a:1c:00:00:01:01", "Janov iPhone", "Apple", "iPhone", [62078], ["_apple-mobdev2._tcp"], {}),
    ("192.168.1.102", "a2:44:00:00:01:02", "Galaxy-S24", None, None, [], [], {}),
    ("192.168.1.150", "d8:3a:dd:00:01:50", "Zariadenie .150", None, None, [], [], {"online": False}),
]

_STATE = {
    "shelly": [D.T("switch:0:on", "Napájanie", True), D.SENS("switch:0:p", "Príkon", 1243.5, "W"),
               D.SENS("temperature:0", "Teplota", 41.2, "°C")],
    "shellycover": [D.B("cover:0:open", "Otvoriť", "Žalúzia", "up"), D.B("cover:0:stop", "Stop", "Žalúzia", "stop"),
                    D.B("cover:0:close", "Zatvoriť", "Žalúzia", "down"), D.S("cover:0:pos", "Poloha", 65, 0, 100, "%", "Žalúzia")],
    "tasmota": [D.T("power:POWER", "Napájanie", False), D.SENS("sns:ENERGY:Power", "Príkon", 0, "W"),
                D.SENS("sns:ENERGY:Today", "Dnes", 3.21, "kWh"), D.SENS("sns:ENERGY:Voltage", "Napätie", 231, "V")],
    "wled": [D.T("on", "Zapnuté", True), D.S("bri", "Jas", 180, 1, 255), D.C("col", "Farba", "#ff7a1a"),
             D.SEL("fx", "Efekt", 0, [[0, "Solid"], [1, "Blink"], [2, "Breathe"], [9, "Rainbow"], [65, "Fire 2012"]])],
    "hue": [D.T("group:0:on", "Všetky svetlá", True, "Celý dom"), D.T("group:1:on", "Obývačka", True, "Miestnosti"),
            D.T("group:2:on", "Kuchyňa", False, "Miestnosti"),
            D.T("light:1:on", "Zapnuté", True, "Stropné svetlo"), D.S("light:1:bri", "Jas", 200, 1, 254, "", "Stropné svetlo"),
            D.S("light:1:ct", "Teplota farby", 300, 153, 454, " mired", "Stropné svetlo"),
            D.T("light:2:on", "Zapnuté", True, "Hue Go"), D.S("light:2:bri", "Jas", 120, 1, 254, "", "Hue Go"),
            D.C("light:2:rgb", "Farba", "#6a5cff", "Hue Go"),
            D.INFO("Svetlo je nedostupné (vypnuté vypínačom?)", "Kuchynská linka", id="light:3:na")],
    "yeelight": [D.T("power", "Zapnuté", False), D.S("bright", "Jas", 40, 1, 100, "%"), D.C("rgb", "Farba", "#ffb070"),
                 D.S("ct", "Teplota farby", 2700, 1700, 6500, " K", step=100)],
    "lgwebos": [D.S("volume", "Hlasitosť", 14, 0, 100), D.T("mute", "Stlmiť", False), D.B("off", "Vypnúť TV", icon="power"),
                D.B("chdown", "Kanál −"), D.B("chup", "Kanál +"), D.B("play", "Play", icon="play"), D.B("pause", "Pauza", icon="pause"),
                D.SEL("app", "Aplikácia", "", [["", "—"], ["netflix", "Netflix"], ["youtube.leanback.v4", "YouTube"], ["com.webos.app.livetv", "Live TV"]]),
                D.SEL("input", "Vstup", "", [["", "—"], ["HDMI_1", "HDMI 1 – PlayStation"], ["HDMI_2", "HDMI 2"]])],
    "philips": [D.T("power", "Zapnutá", True), D.S("volume", "Hlasitosť", 18, 0, 60), D.T("mute", "Stlmiť", False),
                D.T("ambilight", "Ambilight", True), D.PAD("key", D.PHILIPS_PAD, "Ovládač"),
                D.SEL("app", "Spustiť aplikáciu", "", [["", "—"], ["0", "Netflix"], ["1", "YouTube"], ["2", "HBO Max"],
                                                        ["3", "Voyo"], ["4", "Prehliadač"], ["5", "Media"]])],
    "upnp": [D.SENS("state", "Stav", "Hrá"), D.S("volume", "Hlasitosť", 22, 0, 100), D.T("mute", "Stlmiť", False),
             D.B("Previous", "Predch.", icon="prev"), D.B("Play", "Play", icon="play"), D.B("Pause", "Pauza", icon="pause"),
             D.B("Next", "Ďalšia", icon="next")],
    "homeassistant": [
        D.T("ha|light.kuchyna|on", "Kuchyňa strop (Tuya)", True, "Svetlá"), D.S("ha|light.kuchyna|bri", "↳ jas", 160, 1, 255, "", "Svetlá"),
        D.T("ha|switch.zavlazovanie|on", "Zavlažovanie (Xiaomi)", False, "Vypínače"),
        D.T("ha|fan.ventilator|on", "Ventilátor spálňa", False, "Ventilátory"),
        D.SENS("ha|cover.garaz|st", "Garážová brána", "zatvorené", "", "Žalúzie a brány"),
        D.B("ha|cover.garaz|open", "Otvoriť", "Žalúzie a brány", "up"), D.B("ha|cover.garaz|stop", "Stop", "Žalúzie a brány", "stop"),
        D.B("ha|cover.garaz|close", "Zatvoriť", "Žalúzie a brány", "down"),
        D.SENS("ha|climate.obyvacka|cur", "Obývačka – aktuálne", 21.4, "°C", "Kúrenie / klíma"),
        D.S("ha|climate.obyvacka|temp", "Obývačka – cieľ", 22, 7, 30, "°C", "Kúrenie / klíma", step=0.5),
        D.B("ha|scene.kino|run", "Kino večer", "Scény", "play"), D.B("ha|scene.dobru_noc|run", "Dobrú noc", "Scény", "play")],
}


class DemoDriver(D.Driver):
    def __init__(self):
        self.state = {}

    def _st(self, dev):
        kind = dev["driver_info"]["demo"]
        return self.state.setdefault(dev["id"], copy.deepcopy(_STATE[kind]))

    def controls(self, dev, store):
        return copy.deepcopy(self._st(dev))

    def set(self, dev, store, cid, value):
        for c in self._st(dev):
            if c["id"] == cid and c["type"] in ("toggle", "slider", "color", "select"):
                c["value"] = bool(value) if c["type"] == "toggle" else value
                if dev["driver_info"]["demo"] == "shelly" and cid.endswith(":on"):
                    for s in self._st(dev):
                        if s["id"] == "switch:0:p":
                            s["value"] = 1243.5 if value else 0


def devices():
    now = time.time()
    out = []
    labels = {"shelly": "Shelly", "shellycover": "Shelly", "tasmota": "Tasmota", "wled": "WLED",
              "hue": "Philips Hue", "yeelight": "Yeelight", "lgwebos": "LG webOS TV", "philips": "Philips TV",
              "upnp": "UPnP/DLNA prehrávač", "homeassistant": "Home Assistant"}
    for row in _RAW:
        ip, mac, name, vendor, model, ports, mdns, extra = row[:8]
        drv = row[8] if len(row) > 8 else None
        d = {"id": mac, "ip": ip, "mac": mac, "name": name, "hostname": None, "vendor": vendor, "model": model,
             "open_ports": ports, "ports": [{"port": p, "service": PORTS.get(p, str(p))} for p in ports],
             "mdns_services": mdns, "ssdp_type": None, "ssdp_server": None, "is_self": False,
             "is_gateway": False, "random_mac": int(mac.split(":")[0], 16) & 2 == 2, "online": True,
             "last_seen": now, "first_seen": now - 86400 * 30, "new": ip == "192.168.1.102",
             "drivers": [{"key": drv, "label": labels[drv], "info": {"demo": drv}}] if drv else []}
        d.update(extra)
        d["category"] = classify(dict(d, drivers=[{"key": "upnp" if drv in ("lgwebos", "philips") else ("shelly" if drv and drv.startswith("shelly") else drv)}] if drv else []))
        if drv == "homeassistant":
            d["category"] = "server"
        d["controllable"] = bool(drv)
        d["links"] = [{"label": "Web", "url": "http://%s/" % ip}] if 80 in ports else []
        if 8123 in ports:
            d["links"] = [{"label": "Home Assistant", "url": "http://%s:8123/" % ip}]
        out.append(d)
    return out
