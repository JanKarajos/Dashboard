"""Spustenie:  python -m netdash   (alebo python netdash.py)"""
import argparse
import os
import secrets
import sys
import threading
import time
import webbrowser

from . import netutil
from .scanner import Scanner
from .server import App, serve
from .store import Store


class DemoScanner(Scanner):
    def __init__(self, store):
        from . import demo
        super().__init__(store)
        self.devices = {d["id"]: d for d in demo.devices()}
        self.meta = {"network": "192.168.1.0/24", "gateway": "192.168.1.1", "self_ip": "192.168.1.10",
                     "scanned_at": time.time(), "duration": 14.2}

    def start(self, subnet=None):
        if self.progress["running"]:
            return False

        def fake():
            for phase, total in (("Hľadám zariadenia v sieti 192.168.1.0/24", 254),
                                 ("Skenujem porty (19 zariadení)", 760), ("Rozpoznávam zariadenia", 19)):
                self.progress.update(running=True, phase=phase, done=0, total=total)
                for i in range(20):
                    self.progress["done"] = int(total * (i + 1) / 20)
                    time.sleep(0.08)
            self.meta["scanned_at"] = time.time()
            self.progress.update(running=False, phase="Hotovo")
        self.progress.update(running=True)
        threading.Thread(target=fake, daemon=True).start()
        return True


def main(argv=None):
    ap = argparse.ArgumentParser(prog="netdash", description="Dashboard domácej siete s ovládaním zariadení")
    ap.add_argument("--port", type=int, default=8765, help="port webového servera (predvolene 8765)")
    ap.add_argument("--local-only", action="store_true", help="dashboard dostupný len z tohto počítača")
    ap.add_argument("--pin", help="PIN pre prístup z iných zariadení (predvolene sa vygeneruje a uloží)")
    ap.add_argument("--no-pin", action="store_true", help="vypnúť PIN (neodporúča sa)")
    ap.add_argument("--subnet", help="sieť na skenovanie, napr. 192.168.0.0/24 (predvolene automaticky)")
    ap.add_argument("--data", help="súbor s dátami (predvolene netdash_data.json vedľa programu)")
    ap.add_argument("--no-browser", action="store_true", help="neotvárať prehliadač")
    ap.add_argument("--no-scan", action="store_true", help="nespúšťať sken pri štarte")
    ap.add_argument("--demo", action="store_true", help="ukážkový režim s vymyslenými zariadeniami")
    args = ap.parse_args(argv)

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_path = args.data or os.path.join(root, "netdash_demo.json" if args.demo else "netdash_data.json")
    store = Store(data_path)

    pin = None
    if not args.local_only and not args.no_pin:
        pin = args.pin or store.get("settings", "pin")
        if not pin:
            pin = "%06d" % secrets.randbelow(10 ** 6)
        if store.get("settings", "pin") != pin:
            store.put("settings", "pin", pin)

    demo_driver = None
    if args.demo:
        from .demo import DemoDriver
        scanner, demo_driver = DemoScanner(store), DemoDriver()
    else:
        scanner = Scanner(store)

    app = App(store, scanner, pin=pin, demo=demo_driver)
    host = "127.0.0.1" if args.local_only else "0.0.0.0"
    try:
        httpd = serve(app, host, args.port)
    except OSError as e:
        print("Nepodarilo sa otvoriť port %d: %s\nSkús iný: --port 8766" % (args.port, e))
        return 1

    ip = netutil.local_ip()
    url_local = "http://localhost:%d/" % args.port
    print("=" * 60)
    print("  NetDash – dashboard domácej siete%s" % ("  [DEMO]" if args.demo else ""))
    print("=" * 60)
    print("  Na tomto počítači:  %s" % url_local)
    if not args.local_only:
        print("  Z mobilu / inde:    http://%s:%d/" % (ip, args.port))
        print("  PIN:                %s" % (pin or "vypnutý"))
    print("  Ukončenie:          Ctrl+C")
    print("=" * 60)
    sys.stdout.flush()

    if not args.no_scan and (args.demo is False):
        scanner.start(args.subnet)
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url_local)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nKončím…")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
