#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""Icone del menu del tasto destro (Openbox), tinte per NexusSec.

Openbox 3.6 mostra un'icona per voce (attributo icon="PERCORSO" in menu.xml;
il pacchetto Alpine e' compilato con librsvg, quindi gli SVG vanno bene), ma
NON ricolora le icone simboliche: quelle di Adwaita sono grigio scuro
(#2e3436) e sul fondo scuro del menu sparirebbero. Qui se ne fa una copia con
il colore fisso dentro.

Tinta: un ciano medio leggibile sia sul menu scuro (NexusSec-Core, Cards) sia
su quello bianco (Retro); il rosa d'allarme per le azioni distruttive.

Sorgente: le icone simboliche di adwaita-icon-theme (CC-BY-SA 3.0 / LGPL-3,
vedi THIRD-PARTY.md). Uso:
  python3 build/make-menu-icons.py /percorso/icons/Adwaita/symbolic
(per esempio estratte dal pacchetto adwaita-icon-theme dentro la ISO).
Output: overlay/usr/local/share/nexussec/menu-icons/<nome>.svg (committate).
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "overlay/usr/local/share/nexussec/menu-icons")

TINTA = "#33b5d1"          # ciano medio: leggibile su fondo scuro e chiaro
ALLARME = "#ff5a8a"        # palette NexusSec: allarme

# nome del file prodotto -> (icona simbolica Adwaita, colore)
ICONE = {
    "tools": ("applications-utilities", TINTA),
    "editor": ("accessories-text-editor", TINTA),
    "recorder": ("audio-input-microphone", TINTA),
    "images": ("image-x-generic", TINTA),
    "metadata": ("edit-clear-all", TINTA),
    "clipboard": ("edit-paste", TINTA),
    "nightlight": ("night-light", TINTA),
    "keyboard": ("input-keyboard", TINTA),
    "disks": ("drive-harddisk", TINTA),
    "cases": ("folder-documents", TINTA),
    "wizard": ("system-run", TINTA),
    "control-center": ("preferences-system", TINTA),
    "security": ("security-high", TINTA),
    "lock": ("system-lock-screen", TINTA),
    "screenshot": ("camera-photo", TINTA),
    "anon": ("network-vpn", TINTA),
    "firewall": ("channel-secure", TINTA),
    "mac": ("network-wireless", TINTA),
    "panic": ("dialog-warning", ALLARME),
    "profile": ("avatar-default", TINTA),
    "wallpaper": ("preferences-desktop-wallpaper", TINTA),
    "terminal": ("utilities-terminal", TINTA),
    "browser": ("web-browser", TINTA),
    "files": ("system-file-manager", TINTA),
    "horus": ("find-location", TINTA),
    "reload": ("view-refresh", TINTA),
    "shutdown": ("system-shutdown", TINTA),
}

_FILL = re.compile(r'(fill|stroke)="(?!none)[^"]*"')
_FILL_CSS = re.compile(r'(fill|stroke):(?!none)[^;"]+')
_COLOR = re.compile(r'\bcolor="[^"]*"')


def tingi(svg: str, colore: str) -> str:
    svg = _FILL.sub(lambda m: '%s="%s"' % (m.group(1), colore), svg)
    svg = _FILL_CSS.sub(lambda m: "%s:%s" % (m.group(1), colore), svg)
    return _COLOR.sub('color="%s"' % colore, svg)


def trova(src: str, nome: str):
    fn = nome + "-symbolic.svg"
    for base, _dirs, files in os.walk(src):
        if fn in files:
            return os.path.join(base, fn)
    return None


def main(argv):
    if len(argv) != 1 or not os.path.isdir(argv[0]):
        print(__doc__, file=sys.stderr)
        return 2
    os.makedirs(OUT, exist_ok=True)
    mancanti = []
    for out_name, (nome, colore) in sorted(ICONE.items()):
        p = trova(argv[0], nome)
        if not p:
            mancanti.append(nome)
            continue
        with open(p, encoding="utf-8") as f:
            svg = tingi(f.read(), colore)
        with open(os.path.join(OUT, out_name + ".svg"), "w", encoding="utf-8") as f:
            f.write(svg)
    if mancanti:
        print("icone non trovate:", mancanti, file=sys.stderr)
        return 1
    print("%d icone in %s" % (len(ICONE), OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
