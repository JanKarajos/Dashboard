"""Trvalé úložisko (JSON): prezývky, párovacie kľúče, nastavenia, posledný sken."""
import json
import os
import threading


class Store:
    def __init__(self, path):
        self.path = path
        self.lock = threading.RLock()
        self.data = {"aliases": {}, "secrets": {}, "settings": {}, "devices": [], "meta": {}}
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    self.data.update(json.load(f))
            except (OSError, ValueError):
                pass

    def save(self):
        with self.lock:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)

    def get(self, section, key, default=None):
        with self.lock:
            return self.data.setdefault(section, {}).get(key, default)

    def put(self, section, key, value):
        with self.lock:
            sec = self.data.setdefault(section, {})
            if value is None or value == "":
                sec.pop(key, None)
            else:
                sec[key] = value
            self.save()
