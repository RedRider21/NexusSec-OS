"""Configurazione persistente di NexusSec Browser.

Portata dall'originale (ola-browser/config.py): la classe e' identica nella
logica, cambia solo la directory dati (~/.nxs-browser) e la homepage di
default. I dati (config, preferiti) vivono nella home, quindi su
un'installazione NexusSec persistente vengono salvati in mydata.tgz.
"""

import json
from pathlib import Path


class Config:
    def __init__(self):
        self.config_dir = Path.home() / ".nxs-browser"
        self.config_file = self.config_dir / "config.json"
        self.default_config = {
            "homepage": "https://duckduckgo.com",
            # scuro di default: coerente con l'ambiente NexusSec (navy/cyan)
            "dark_mode": True,
            "zoom_level": 1.0,
            "show_bookmarks_bar": True,
            "sidebar_width": 250,
            "user_agent": "",
        }
        self.config = self.load_config()

    def load_config(self):
        self.config_dir.mkdir(exist_ok=True)
        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    loaded = json.load(f)
                cfg = self.default_config.copy()
                cfg.update(loaded)
                return cfg
            except Exception:
                return self.default_config.copy()
        return self.default_config.copy()

    def save_config(self):
        try:
            with open(self.config_file, "w") as f:
                json.dump(self.config, f, indent=2)
            return True
        except Exception:
            return False

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self.save_config()


config = Config()
