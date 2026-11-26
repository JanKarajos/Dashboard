"""Pasívne/broadcast objavovanie: SSDP (UPnP), Yeelight, mDNS (Bonjour), NetBIOS."""
import os
import re
import socket
import struct
import time
from concurrent.futures import ThreadPoolExecutor

from . import netutil

# ---------------------------------------------------------------- SSDP / UPnP

def _mcast_socket(local_ip):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    try:
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(local_ip))
        s.bind((local_ip, 0))
    except OSError:
        s.bind(("", 0))
    return s


def ssdp_discover(local_ip, timeout=3.5):
    """{ip: {"server", "locations", "st", "yeelight": {...}}}"""
    found = {}
    try:
        s = _mcast_socket(local_ip)
    except OSError:
        return found
    msgs = [
        (b'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\n'
         b"MX: 2\r\nST: ssdp:all\r\n\r\n", ("239.255.255.250", 1900)),
        (b'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\n'
         b"MX: 2\r\nST: upnp:rootdevice\r\n\r\n", ("239.255.255.250", 1900)),
        (b'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1982\r\nMAN: "ssdp:discover"\r\n'
         b"ST: wifi_bulb\r\n\r\n", ("239.255.255.250", 1982)),
    ]
    deadline = time.time() + timeout
    try:
        for _ in range(2):
            for m, addr in msgs:
                try:
                    s.sendto(m, addr)
                except OSError:
                    pass
        while time.time() < deadline:
            s.settimeout(max(0.05, deadline - time.time()))
            try:
                data, addr = s.recvfrom(8192)
            except (socket.timeout, OSError):
                break
            headers = {}
            for line in data.decode("utf-8", "replace").split("\r\n")[1:]:
                if ":" in line:
                    k, v = line.split(":", 1)
                    headers[k.strip().lower()] = v.strip()
            ip = addr[0]
            entry = found.setdefault(ip, {"server": None, "locations": [], "st": []})
            loc = headers.get("location", "")
            if loc.startswith("yeelight://"):
                entry["yeelight"] = {
                    "name": headers.get("name") or "",
                    "model": headers.get("model") or "",
                    "support": headers.get("support", "").split(),
                }
                continue
            if headers.get("server"):
                entry["server"] = headers["server"]
            if loc and loc not in entry["locations"]:
                entry["locations"].append(loc)
            st = headers.get("st")
            if st and st not in entry["st"]:
                entry["st"].append(st)
    finally:
        s.close()

    def describe(item):
        ip, entry = item
        for loc in entry["locations"][:3]:
            xml = netutil.get_text(loc, timeout=2.5)
            if xml and "<device" in xml:
                entry["friendlyName"] = netutil.xml_tag(xml, "friendlyName")
                entry["manufacturer"] = netutil.xml_tag(xml, "manufacturer")
                entry["modelName"] = netutil.xml_tag(xml, "modelName")
                entry["modelDescription"] = netutil.xml_tag(xml, "modelDescription")
                entry["deviceType"] = netutil.xml_tag(xml, "deviceType")
                entry["description_url"] = loc
                entry["description_xml"] = xml
                break

    with ThreadPoolExecutor(16) as ex:
        list(ex.map(describe, found.items()))
    return found


# ---------------------------------------------------------------- mDNS

MDNS_SERVICES = [
    "_services._dns-sd._udp.local", "_googlecast._tcp.local", "_airplay._tcp.local",
    "_raop._tcp.local", "_spotify-connect._tcp.local", "_hap._tcp.local",
    "_homekit._tcp.local", "_companion-link._tcp.local", "_apple-mobdev2._tcp.local",
    "_device-info._tcp.local", "_shelly._tcp.local", "_esphomelib._tcp.local",
    "_wled._tcp.local", "_hue._tcp.local", "_sonos._tcp.local", "_http._tcp.local",
    "_ipp._tcp.local", "_printer._tcp.local", "_pdl-datastream._tcp.local",
    "_smb._tcp.local", "_afpovertcp._tcp.local", "_ssh._tcp.local",
    "_home-assistant._tcp.local", "_miio._udp.local", "_androidtvremote2._tcp.local",
    "_amzn-wplay._tcp.local", "_matter._tcp.local", "_workstation._tcp.local",
]


def _encode_name(name):
    out = b""
    for label in name.strip(".").split("."):
        b = label.encode("utf-8")
        out += bytes([len(b)]) + b
    return out + b"\x00"


def _read_name(data, off):
    labels, jumped, end, hops = [], False, None, 0
    while True:
        if off >= len(data):
            raise ValueError("name overflow")
        ln = data[off]
        if ln & 0xC0 == 0xC0:
            ptr = ((ln & 0x3F) << 8) | data[off + 1]
            if not jumped:
                end = off + 2
            off, jumped = ptr, True
            hops += 1
            if hops > 30:
                raise ValueError("loop")
            continue
        if ln == 0:
            off += 1
            break
        labels.append(data[off + 1:off + 1 + ln].decode("utf-8", "replace"))
        off += 1 + ln
    return ".".join(labels), (end if jumped else off)


def _parse_dns(data):
    qd, an, ns, ar = struct.unpack(">HHHH", data[4:12])
    off = 12
    for _ in range(qd):
        _, off = _read_name(data, off)
        off += 4
    records = []
    for _ in range(an + ns + ar):
        name, off = _read_name(data, off)
        rtype, _cls, _ttl, rdlen = struct.unpack(">HHIH", data[off:off + 10])
        off += 10
        rdata_off = off
        off += rdlen
        rec = {"name": name, "type": rtype}
        if rtype == 12:  # PTR
            rec["target"] = _read_name(data, rdata_off)[0]
        elif rtype == 1 and rdlen == 4:
            rec["ip"] = socket.inet_ntoa(data[rdata_off:rdata_off + 4])
        elif rtype == 33:
            rec["port"] = struct.unpack(">H", data[rdata_off + 4:rdata_off + 6])[0]
            rec["target"] = _read_name(data, rdata_off + 6)[0]
        elif rtype == 16:
            txt, p = {}, rdata_off
            while p < off:
                ln = data[p]
                s = data[p + 1:p + 1 + ln].decode("utf-8", "replace")
                if "=" in s:
                    k, v = s.split("=", 1)
                    txt[k.lower()] = v
                p += 1 + ln
            rec["txt"] = txt
        records.append(rec)
    return records


def mdns_discover(local_ip, timeout=3.5):
    """{ip: {"services": set, "names": set, "hostname", "txt": {...}}}"""
    found = {}
    try:
        s = _mcast_socket(local_ip)
    except OSError:
        return found

    def query(names):
        q = struct.pack(">HHHHHH", 0, 0, len(names), 0, 0, 0)
        for n in names:
            q += _encode_name(n) + struct.pack(">HH", 12, 1)
        return q

    pkts = [query(MDNS_SERVICES[i:i + 10]) for i in range(0, len(MDNS_SERVICES), 10)]
    extra_sent = set()
    deadline = time.time() + timeout
    try:
        for _ in range(2):
            for p in pkts:
                try:
                    s.sendto(p, ("224.0.0.251", 5353))
                except OSError:
                    pass
        while time.time() < deadline:
            s.settimeout(max(0.05, deadline - time.time()))
            try:
                data, addr = s.recvfrom(9000)
            except (socket.timeout, OSError):
                break
            try:
                recs = _parse_dns(data)
            except (ValueError, struct.error, IndexError):
                continue
            ip = addr[0]
            e = found.setdefault(ip, {"services": set(), "names": set(), "hostname": None, "txt": {}})
            new_types = []
            for r in recs:
                if r["type"] == 12:
                    if r["name"] == "_services._dns-sd._udp.local":
                        if r["target"] not in MDNS_SERVICES and r["target"] not in extra_sent:
                            new_types.append(r["target"])
                        continue
                    e["services"].add(r["name"])
                    inst = r["target"]
                    svc = r["name"]
                    if inst.endswith("." + svc):
                        e["names"].add((svc, inst[: -len(svc) - 1]))
                elif r["type"] == 16:
                    for k in ("fn", "md", "model", "mf", "manufacturer", "ty", "n", "id"):
                        if k in r["txt"] and r["txt"][k]:
                            e["txt"].setdefault(k, r["txt"][k])
                elif r["type"] in (1, 33) and r.get("target", r["name"]).endswith(".local"):
                    host = r.get("target") if r["type"] == 33 else r["name"]
                    if not e["hostname"] and host:
                        e["hostname"] = host[:-6]
            if new_types:
                extra_sent.update(new_types)
                for i in range(0, len(new_types), 10):
                    try:
                        s.sendto(query(new_types[i:i + 10]), ("224.0.0.251", 5353))
                    except OSError:
                        pass
    finally:
        s.close()
    return found


# ---------------------------------------------------------------- NetBIOS

def netbios_name(ip, timeout=0.8):
    pkt = os.urandom(2) + b"\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00" + b"\x20" + \
        b"CK" + b"A" * 30 + b"\x00" + b"\x00\x21\x00\x01"
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(pkt, (ip, 137))
        data, _ = s.recvfrom(2048)
    except OSError:
        return None
    finally:
        s.close()
    try:
        off = 12 + (34 if data[12] == 0x20 else 2) + 10
        count = data[off]
        off += 1
        for i in range(count):
            entry = data[off + i * 18: off + i * 18 + 18]
            name = entry[:15].decode("latin-1").strip()
            suffix = entry[15]
            flags = struct.unpack(">H", entry[16:18])[0]
            if suffix == 0x00 and not flags & 0x8000 and name:
                return name
    except (IndexError, struct.error):
        return None
    return None
