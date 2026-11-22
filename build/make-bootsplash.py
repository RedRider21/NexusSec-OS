#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""make-bootsplash.py - la splash di avvio UNICA, stile Linux Mint (2026-11-22).

Un solo disegno per tutto l'avvio: sfondo scuro uniforme, logo NexusSec al
centro con un bagliore che PULSA, barra di avanzamento sottile sotto. Lo usano:

  - fbsplash (immagine fissa, initramfs): build-alpine/fbsplash.ppm
  - nxs_cc/fbanim.py (animazione sul framebuffer durante OpenRC)
  - nxs_cc/bootsplash.py (stessa animazione sotto X, poi il desktop)

Uscite:
  overlay/usr/local/share/nexussec/splash/pulse.bin  fotogrammi del logo (zlib)
  build-alpine/fbsplash.ppm                           primo fotogramma, 1280x720

Formato pulse.bin: "NXSP" + uint16 w, h, n + n blocchi (uint32 lunghezza +
zlib(RGB w*h)). Geometria condivisa (in pixel, rispetto al CENTRO schermo):
logo centrato in (0, -LOGO_DY); barra larga BAR_W, alta BAR_H, a +BAR_DY.
"""
import math
import os
import struct
import sys
import zlib

from PIL import Image, ImageFilter

QUI = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(QUI, "..")
OUT = os.path.join(ROOT, "overlay", "usr", "local", "share", "nexussec", "splash", "pulse.bin")
PPM = os.path.join(ROOT, "build-alpine", "fbsplash.ppm")
EMBLEMA = os.path.join(ROOT, "branding", "png", "emblema-trasparente.png")

BG = (5, 9, 15)
TRACK = (22, 40, 54)
FILL = (0, 229, 255)
LOGO = 200            # lato del logo
BOX = 300             # lato del fotogramma (logo + alone)
N = 24                # fotogrammi del ciclo di pulsazione
LOGO_DY = 40          # il logo sta un po' sopra il centro
BAR_W, BAR_H, BAR_DY = 260, 4, 120


def fotogrammi():
    em = Image.open(EMBLEMA).convert("RGBA")
    bb = em.getchannel("A").point(lambda a: 255 if a > 40 else 0).getbbox()
    em = em.crop(bb)
    w, h = em.size
    m = max(w, h)
    q = Image.new("RGBA", (m, m), (0, 0, 0, 0))
    q.paste(em, ((m - w) // 2, (m - h) // 2))
    logo = q.resize((LOGO, LOGO), Image.LANCZOS)
    # alone: il logo sfocato, ingrandito, colorato d'accento
    alone = Image.new("RGBA", (BOX, BOX), (0, 0, 0, 0))
    a = logo.getchannel("A")
    c = Image.new("RGBA", (LOGO, LOGO), FILL + (0,))
    c.putalpha(a)
    alone.paste(c, ((BOX - LOGO) // 2, (BOX - LOGO) // 2), c)
    alone = alone.filter(ImageFilter.GaussianBlur(22))
    out = []
    for i in range(N):
        t = 0.5 - 0.5 * math.cos(2 * math.pi * i / N)       # 0..1..0
        f = Image.new("RGBA", (BOX, BOX), BG + (255,))
        g = alone.copy()
        g.putalpha(g.getchannel("A").point(lambda v, k=0.25 + 0.75 * t: int(min(255, v * k * 1.8))))
        f.alpha_composite(g)
        lg = logo.copy()
        lg.putalpha(lg.getchannel("A").point(lambda v, k=0.82 + 0.18 * t: int(v * k)))
        f.alpha_composite(lg, ((BOX - LOGO) // 2, (BOX - LOGO) // 2))
        out.append(f.convert("RGB"))
    return out


def main():
    fr = fotogrammi()
    with open(OUT, "wb") as fh:
        fh.write(b"NXSP" + struct.pack("<HHH", BOX, BOX, len(fr)))
        for im in fr:
            z = zlib.compress(im.tobytes(), 9)
            fh.write(struct.pack("<I", len(z)) + z)
    # immagine fissa per fbsplash (initramfs): primo fotogramma + barra vuota,
    # con la STESSA geometria rispetto al centro (fbsplash la centra)
    W, H = 1280, 720
    ppm = Image.new("RGB", (W, H), BG)
    cx, cy = W // 2, H // 2
    ppm.paste(fr[0], (cx - BOX // 2, cy - LOGO_DY - BOX // 2))
    for y in range(BAR_H):
        for x in range(BAR_W):
            ppm.putpixel((cx - BAR_W // 2 + x, cy + BAR_DY + y), TRACK)
    ppm.save(PPM)
    print("pulse.bin: %d fotogrammi %dx%d, %d byte; fbsplash.ppm %dx%d"
          % (len(fr), BOX, BOX, os.path.getsize(OUT), W, H))
    if len(sys.argv) > 2 and sys.argv[1] == "--anteprima":
        st = Image.new("RGB", (BOX * 6, BOX * 4))
        for i, im in enumerate(fr):
            st.paste(im, ((i % 6) * BOX, (i // 6) * BOX))
        st.save(sys.argv[2])
    return 0


if __name__ == "__main__":
    sys.exit(main())
