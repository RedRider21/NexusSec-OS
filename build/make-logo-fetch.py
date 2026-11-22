#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""make-logo-fetch.py - logo del terminale (nxs-fetch) a DUE TONI, 2026-11-22.

Disegna l'emblema NexusSec (stessa geometria di branding/genera-brand.py:
esagono a nodi + esagono interno tenue + N a nodi) su una griglia di pixel
"quadrati" e lo codifica per i MEZZI BLOCCHI del terminale: ogni carattere
contiene due pixel (sopra/sotto), quindi 16 righe = 32 pixel di altezza.

Classi di colore: 0 vuoto, 1 accent del profilo (esagono e nodi), 2 chiaro
(la N), 3 accent tenue (esagono interno). Ogni cella = una cifra esadecimale
(sopra*4 + sotto); nxs-fetch la traduce in caratteri e colori truecolor.

Uscita: overlay/usr/local/share/nexussec/logo-fetch.txt (16 righe x LARG).
Anteprima PNG: --anteprima FILE.
"""
import math
import os
import sys

from PIL import Image, ImageDraw

QUI = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(QUI, "..", "overlay", "usr", "local", "share", "nexussec", "logo-fetch.txt")
LARG, ALT = 30, 32            # pixel (ALT pari: 2 pixel per riga di terminale)
SS = 16                       # sovracampionamento


def esagono(cx, cy, r):
    return [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
            for a in (-90, -30, 30, 90, 150, 210)]


def disegna():
    W, H = LARG * SS, ALT * SS
    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)
    cx, cy = W / 2, H / 2
    s = H * 0.41                               # raggio esterno (nodi dentro)
    w = s * 0.11                               # spessore (piu' del logo: pixel grossi)
    est = esagono(cx, cy, s)
    d.line(est + [est[0]], fill=1, width=int(w), joint="curve")
    inn = esagono(cx, cy, s * 0.71)
    d.line(inn + [inn[0]], fill=3, width=int(w * 0.4), joint="curve")
    for x, y in est:                           # nodi dell'esagono
        r = s * 0.13
        d.ellipse((x - r, y - r, x + r, y + r), fill=1)
    nx, nh = s * 0.28, s * 0.37
    L, R, T, B = cx - nx, cx + nx, cy - nh, cy + nh
    d.line([(L, B), (L, T), (R, B), (R, T)], fill=2, width=int(w * 1.15), joint="curve")
    for x, y in ((L, B), (L, T), (R, B), (R, T)):
        r = s * 0.095
        d.ellipse((x - r, y - r, x + r, y + r), fill=2)
    # riduzione: per ogni pixel la classe piu' presente (vuoto se < 35%)
    px = im.load()
    out = []
    for gy in range(ALT):
        riga = []
        for gx in range(LARG):
            conta = {}
            for yy in range(gy * SS, (gy + 1) * SS):
                for xx in range(gx * SS, (gx + 1) * SS):
                    v = px[xx, yy]
                    if v:
                        conta[v] = conta.get(v, 0) + 1
            tot = sum(conta.values())
            if tot < SS * SS * 0.35:
                riga.append(0)
            else:
                # la N (2) e l'esagono (1) vincono sul tenue (3)
                riga.append(max(conta, key=lambda k: conta[k] * (1.6 if k in (1, 2) else 1)))
        out.append(riga)
    return out


def main(argv):
    g = disegna()
    righe = []
    for y in range(0, ALT, 2):
        righe.append("".join("%x" % (g[y][x] * 4 + g[y + 1][x]) for x in range(LARG)))
    open(OUT, "w").write("\n".join(righe) + "\n")
    print("logo-fetch.txt: %d righe x %d colonne" % (len(righe), LARG))
    if len(argv) > 2 and argv[1] == "--anteprima":
        col = {0: (5, 10, 20), 1: (0, 229, 255), 2: (200, 245, 255), 3: (0, 100, 115)}
        im = Image.new("RGB", (LARG * 10, ALT * 10))
        d = ImageDraw.Draw(im)
        for y in range(ALT):
            for x in range(LARG):
                d.rectangle((x * 10, y * 10, x * 10 + 9, y * 10 + 9), fill=col[g[y][x]])
        im.save(argv[2])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
