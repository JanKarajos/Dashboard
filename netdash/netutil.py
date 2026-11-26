"""Nízkoúrovňové sieťové pomôcky (multiplatformové, iba štandardná knižnica)."""
import errno
import ipaddress
import json
import platform
import re
import socket
import ssl
import subprocess
import urllib.error
import urllib.request

SYSTEM = platform.system()
IS_WIN = SYSTEM == "Windows"
IS_MAC = SYSTEM == "Darwin"

IP_RE = r"(\d{1,3}(?:\.\d{1,3}){3})"
MAC_RE = r"((?:[0-9a-fA-F]{1,2}[:-]){5}[0-9a-fA-F]{1,2})"

_NO_PROXY = urllib.request.ProxyHandler({})
_SSL = ssl.create_default_context()
# Zariadenia v LAN majú takmer vždy self-signed certifikáty.
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE
_OPENER = urllib.request.build_opener(_NO_PROXY, urllib.request.HTTPSHandler(context=_SSL))


def run(cmd, timeout=5):
    kw = {}
    if IS_WIN:
        kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout, **kw)
        out = p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")
        return p.returncode, out
    except (OSError, subprocess.SubprocessError):
        return -1, ""


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # nič sa neposiela, len sa vyberie rozhranie
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _prefix_from_mask(mask):
    try:
        return ipaddress.IPv4Network("0.0.0.0/" + mask).prefixlen
    except ValueError:
        return None


def detect_network(ip):
    """Vráti IPv4Network lokálnej siete (max. /22, inak sa zúži na /24)."""
    prefix = None
    if IS_WIN:
        _, out = run(["ipconfig"])
        lines = out.splitlines()
        for i, line in enumerate(lines):
            if ip in line:
                for nxt in lines[i + 1:i + 4]:
                    m = re.search(r"(255\.\d{1,3}\.\d{1,3}\.\d{1,3})", nxt)
                    if m:
                        prefix = _prefix_from_mask(m.group(1))
                        break
                break
    else:
        _, out = run(["ip", "-o", "-4", "addr", "show"])
        m = re.search(re.escape(ip) + r"/(\d+)", out)
        if m:
            prefix = int(m.group(1))
        else:
            _, out = run(["ifconfig"])
            m = re.search(r"inet " + re.escape(ip) + r"\s+netmask\s+(0x[0-9a-fA-F]+|[\d.]+)", out)
            if m:
                mask = m.group(1)
                if mask.startswith("0x"):
                    mask = str(ipaddress.IPv4Address(int(mask, 16)))
                prefix = _prefix_from_mask(mask)
    if prefix is None or prefix < 22 or prefix > 30:
        prefix = 24
    return ipaddress.IPv4Network("%s/%d" % (ip, prefix), strict=False)


def default_gateway():
    if IS_WIN:
        _, out = run(["route", "print", "-4", "0.0.0.0"])
        m = re.search(r"0\.0\.0\.0\s+0\.0\.0\.0\s+" + IP_RE, out)
    elif IS_MAC:
        _, out = run(["route", "-n", "get", "default"])
        m = re.search(r"gateway:\s*" + IP_RE, out)
    else:
        _, out = run(["ip", "route", "show", "default"])
        m = re.search(r"default via " + IP_RE, out)
    return m.group(1) if m else None


def norm_mac(mac):
    parts = re.split(r"[:-]", mac)
    return ":".join(p.zfill(2) for p in parts).lower()


def arp_table():
    """{ip: mac} z ARP/neighbor tabuľky operačného systému."""
    outs = []
    if not IS_WIN and not IS_MAC:
        _, out = run(["ip", "neigh"])
        outs.append(out)
        try:
            with open("/proc/net/arp") as f:
                outs.append(f.read())
        except OSError:
            pass
    _, out = run(["arp", "-a"])
    outs.append(out)
    table = {}
    for out in outs:
        for line in out.splitlines():
            ip = re.search(IP_RE, line)
            mac = re.search(MAC_RE, line)
            if not ip or not mac:
                continue
            m = norm_mac(mac.group(1))
            if m in ("ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00") or m.startswith("01:00:5e"):
                continue
            table[ip.group(1)] = m
    return table


def is_random_mac(mac):
    try:
        return bool(int(mac.split(":")[0], 16) & 0x02)
    except (ValueError, AttributeError, IndexError):
        return False


def ping(ip, timeout_ms=800):
    if IS_WIN:
        cmd = ["ping", "-n", "1", "-w", str(timeout_ms), ip]
    elif IS_MAC:
        cmd = ["ping", "-c", "1", "-W", str(timeout_ms), ip]
    else:
        cmd = ["ping", "-c", "1", "-W", str(max(1, timeout_ms // 1000)), ip]
    code, out = run(cmd, timeout=timeout_ms / 1000 + 2)
    return code == 0 and "ttl" in out.lower()


_REFUSED = {errno.ECONNREFUSED, 10061}


def tcp_probe(ip, port, timeout=0.5):
    """'open', 'closed' (hostiteľ žije, port zatvorený) alebo None."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        r = s.connect_ex((ip, port))
    except (OSError, socket.timeout):
        return None
    finally:
        s.close()
    if r == 0:
        return "open"
    if r in _REFUSED:
        return "closed"
    return None


def http(method, url, body=None, headers=None, timeout=3.0):
    """Vráti (status, text). Pri chybe spojenia vyhodí OSError."""
    headers = dict(headers or {})
    if body is not None and not isinstance(body, (bytes, str)):
        body = json.dumps(body)
        headers.setdefault("Content-Type", "application/json")
    if isinstance(body, str):
        body = body.encode("utf-8")
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            txt = e.read().decode("utf-8", "replace")
        except Exception:
            txt = ""
        return e.code, txt


def get_json(url, timeout=2.5, headers=None):
    try:
        status, txt = http("GET", url, timeout=timeout, headers=headers)
    except (OSError, ValueError):
        return None
    if status >= 400 and status != 401:
        return None
    try:
        return json.loads(txt)
    except ValueError:
        return None


def get_text(url, timeout=2.5):
    try:
        status, txt = http("GET", url, timeout=timeout)
    except (OSError, ValueError):
        return None
    return txt if status < 400 else None


def xml_tag(xml, tag):
    import html
    m = re.search(r"<(?:\w+:)?%s>(.*?)</(?:\w+:)?%s>" % (tag, tag), xml or "", re.S)
    return html.unescape(m.group(1).strip()) if m else None


def reverse_dns(ip):
    try:
        name = socket.gethostbyaddr(ip)[0]
    except (OSError, UnicodeError):
        return None
    return None if name == ip else name


def wake_on_lan(mac, broadcast_addrs=("255.255.255.255",)):
    raw = bytes.fromhex(mac.replace(":", "").replace("-", ""))
    if len(raw) != 6:
        raise ValueError("Neplatná MAC adresa")
    pkt = b"\xff" * 6 + raw * 16
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        for addr in broadcast_addrs:
            for port in (9, 7):
                try:
                    s.sendto(pkt, (addr, port))
                except OSError:
                    pass
    finally:
        s.close()


def hex_to_rgb(h):
    h = (h or "").lstrip("#")
    if len(h) < 6:
        return 255, 255, 255
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(r, g, b):
    return "#%02x%02x%02x" % (int(r) & 255, int(g) & 255, int(b) & 255)
