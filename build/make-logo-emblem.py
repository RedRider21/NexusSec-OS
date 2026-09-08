#!/usr/bin/env python3
# NexusSec - genera la silhouette ASCII dell'emblema per il fetch da terminale
# (nxs-fetch). Rende l'emblema UFFICIALE (splash/emblem.png) a "mezzi blocchi"
# Unicode (▀ ▄ █), MONOCROMO: nxs-fetch poi lo colora con l'accent del profilo.
#
# Perche' un file dati e non ASCII a mano: la forma resta fedele al logo vero e,
# soprattutto, ogni riga esce larga ESATTAMENTE W colonne (spazi finali inclusi)
# cosi' nel fetch le info a destra restano allineate senza calcolare larghezze
# di stringa UTF-8 (inaffidabili su musl/locale C).
#
# Uso:  python3 build/make-logo-emblem.py
# Output: overlay/usr/local/share/nexussec/logo-emblem.txt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMBLEM = os.path.join(ROOT, "overlay/usr/local/share/nexussec/splash/emblem.png")
OUT = os.path.join(ROOT, "overlay/usr/local/share/nexussec/logo-emblem.txt")
W = 24            # larghezza in colonne (celle); l'altezza segue le proporzioni
TH = 60           # soglia sul canale alpha (pixel "acceso" = parte del logo)


def main():
    try:
        from PIL import Image
    except Exception:
        print("PIL assente: impossibile rigenerare il logo (tengo quello esistente)",
              file=sys.stderr)
        return 0
    im = Image.open(EMBLEM).convert("RGBA")
    a = im.getchannel("A")
    bbox = a.getbbox()                 # ritaglia il margine trasparente
    if bbox:
        im = im.crop(bbox)
        a = im.getchannel("A")
    h = int(a.height * W / a.width)
    h += h % 2                         # pari: 2 pixel per riga (mezzi blocchi)
    a = a.resize((W, h), Image.LANCZOS)
    px = a.load()

    def on(x, y):
        return y < h and px[x, y] >= TH

    rows = []
    for y in range(0, h, 2):
        line = "".join(
            "█" if (on(x, y) and on(x, y + 1)) else      # █ pieno
            "▀" if on(x, y) else                          # ▀ sopra
            "▄" if on(x, y + 1) else " "                  # ▄ sotto
            for x in range(W))
        rows.append(line)
    while rows and not rows[0].strip():
        rows.pop(0)
    while rows and not rows[-1].strip():
        rows.pop()
    # ogni riga e' gia' larga W (le celle vuote sono spazi): NON fare rstrip.
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(rows) + "\n")
    print("scritto %s (%d righe x %d colonne)" % (OUT, len(rows), W))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
