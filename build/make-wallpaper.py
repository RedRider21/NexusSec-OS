#!/usr/bin/env python3
"""Generatore sfondi NexusSec (PIL) - stile sci-fi/HUD con piu' fantasia.

Per ogni profilo operativo produce uno sfondo 1920x1080 coerente con l'accent:
sfondo a gradiente radiale tinto, alone luminoso, griglia esagonale (honeycomb),
una "rete di nodi" (constellation/recon) e un EMBLEMA tematico diverso per ogni
modalita' (mirino, lente+impronta, globo, ecc.) con effetto glow, piu' vignette
e filigrana. Output in overlay/.../backgrounds/.

Uso:  python3 build/make-wallpaper.py
"""
from __future__ import annotations

import math
import os
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1920, 1080
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "overlay/home/nexus/.themes/NexusSec-Core/backgrounds")


def hx(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def font(size: int):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


# ----------------------------------------------------------------- background
def background(accent, deep, focal):
    """Gradiente radiale: leggermente tinto verso l'accent nel punto focale,
    quasi nero ai bordi. + vignette."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    fx, fy = focal
    d = np.sqrt(((xx - fx) / W) ** 2 + ((yy - fy) / H) ** 2)
    d = np.clip(d / d.max(), 0, 1)
    glow = (1 - d) ** 2.2                      # piu' luce al centro focale
    near = np.array(mix(deep, accent, 0.18), np.float32)
    far = np.array(deep, np.float32)
    img = far[None, None, :] + (near - far)[None, None, :] * glow[..., None]
    # vignette ai bordi
    vig = 1 - 0.55 * (d ** 2)
    img *= vig[..., None]
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB").convert("RGBA")


def starfield(seed):
    rnd = random.Random(seed)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(260):
        x, y = rnd.randint(0, W), rnd.randint(0, H)
        b = rnd.randint(40, 170)
        r = rnd.choice([0, 0, 0, 1])
        d.ellipse([x - r, y - r, x + r, y + r], fill=(b, b, b, b))
    return layer


# ----------------------------------------------------------------- honeycomb
def honeycomb(accent, size=46, alpha=22):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    col = accent + (alpha,)
    dx = size * 1.5
    dy = size * math.sqrt(3)
    col_i = 0
    x = -size
    while x < W + size:
        off = 0 if col_i % 2 == 0 else dy / 2
        y = -size + off
        while y < H + size:
            pts = [(x + size * math.cos(math.radians(a)),
                    y + size * math.sin(math.radians(a))) for a in range(0, 360, 60)]
            d.line(pts + [pts[0]], fill=col, width=1)
            y += dy
        x += dx
        col_i += 1
    return layer


# ----------------------------------------------------------------- node net
def node_network(accent, seed, focal, n=70):
    rnd = random.Random(seed + 99)
    pts = [(rnd.randint(0, W), rnd.randint(0, H)) for _ in range(n)]
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    R = 230
    for i, (x1, y1) in enumerate(pts):
        for (x2, y2) in pts[i + 1:]:
            dist = math.hypot(x1 - x2, y1 - y2)
            if dist < R:
                a = int(70 * (1 - dist / R))
                d.line([x1, y1, x2, y2], fill=accent + (a,), width=1)
    for (x, y) in pts:
        df = math.hypot(x - focal[0], y - focal[1]) / math.hypot(W, H)
        a = int(120 + 120 * (1 - df))
        r = rnd.choice([1, 2, 2, 3])
        d.ellipse([x - r, y - r, x + r, y + r], fill=accent + (min(a, 255),))
    return layer


# ----------------------------------------------------------------- emblems
def _ring(d, cx, cy, r, col, w=2):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col, width=w)


def emblem(profile, accent):
    """Emblema tematico (su layer trasparente, poi glow+crisp)."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = W // 2, H // 2 - 20
    A = accent
    soft = A + (140,)
    hard = A + (235,)
    faint = A + (60,)

    if profile == "pentest":          # mirino / target + radar sweep
        for r in (140, 220, 300, 360):
            _ring(d, cx, cy, r, soft, 2)
        d.line([cx - 400, cy, cx + 400, cy], fill=soft, width=1)
        d.line([cx, cy - 400, cx, cy + 400], fill=soft, width=1)
        for ang in range(0, 360, 30):       # tacche
            a = math.radians(ang)
            d.line([cx + 360 * math.cos(a), cy + 360 * math.sin(a),
                    cx + 392 * math.cos(a), cy + 392 * math.sin(a)], fill=hard, width=2)
        d.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=hard)
        sweep = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ds = ImageDraw.Draw(sweep)
        ds.pieslice([cx - 360, cy - 360, cx + 360, cy + 360], -60, -15, fill=A + (45,))
        layer = Image.alpha_composite(layer, sweep)

    elif profile == "forensics":      # lente d'ingrandimento + impronta
        lx, ly, lr = cx - 40, cy - 30, 230
        for off in range(0, 170, 26):       # impronta (archi concentrici)
            d.arc([lx - off, ly - off, lx + off, ly + off], 20, 320, fill=faint, width=2)
        _ring(d, lx, ly, lr, hard, 5)
        _ring(d, lx, ly, lr - 10, soft, 2)
        a = math.radians(45)
        d.line([lx + lr * math.cos(a), ly + lr * math.sin(a),
                lx + (lr + 190) * math.cos(a), ly + (lr + 190) * math.sin(a)],
               fill=hard, width=16)

    elif profile == "osint":          # globo + meridiani + pin
        r = 300
        _ring(d, cx, cy, r, hard, 3)
        for f in (0.4, 0.75):               # latitudini
            rr = int(r * f)
            d.ellipse([cx - r, cy - rr, cx + r, cy + rr], outline=soft, width=2)
        for f in (0.4, 0.75):               # meridiani
            rr = int(r * f)
            d.ellipse([cx - rr, cy - r, cx + rr, cy + r], outline=soft, width=2)
        d.line([cx - r, cy, cx + r, cy], fill=soft, width=2)
        rnd = random.Random(7)
        for _ in range(7):                  # pin
            a = rnd.uniform(0, 2 * math.pi)
            rr = rnd.uniform(0, r * 0.9)
            px, py = cx + rr * math.cos(a), cy + rr * math.sin(a) * 0.7
            d.ellipse([px - 5, py - 5, px + 5, py + 5], fill=hard)

    elif profile == "web":            # globo wireframe + brackets </>
        r = 280
        _ring(d, cx, cy, r, hard, 3)
        for f in (0.45, 0.8):
            d.ellipse([cx - int(r * f), cy - r, cx + int(r * f), cy + r],
                      outline=soft, width=2)
        d.line([cx - r, cy, cx + r, cy], fill=soft, width=2)
        d.ellipse([cx - r, cy - int(r * 0.45), cx + r, cy + int(r * 0.45)],
                  outline=soft, width=2)
        fb = font(150)
        d.text((cx - r - 150, cy - 95), "<", font=fb, fill=hard)
        d.text((cx + r + 30, cy - 95), ">", font=fb, fill=hard)
        d.text((cx - 28, cy - 95), "/", font=fb, fill=soft)

    else:                             # base: core esagonale + orbite
        for r, col in ((170, hard), (120, soft), (70, soft)):
            pts = [(cx + r * math.cos(math.radians(a)),
                    cy + r * math.sin(math.radians(a))) for a in range(0, 360, 60)]
            d.line(pts + [pts[0]], fill=col, width=3)
        for r in (250, 330):
            _ring(d, cx, cy, r, faint, 2)
        a = math.radians(40)
        d.ellipse([cx + 330 * math.cos(a) - 7, cy + 330 * math.sin(a) - 7,
                   cx + 330 * math.cos(a) + 7, cy + 330 * math.sin(a) + 7], fill=hard)
    return layer


def brand_badge(accent):
    """Monogramma del SO: badge esagonale con 'NXS' + 'NEXUSSEC OS', in alto al
    centro. E' il marchio del sistema, coerente col motivo honeycomb."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy, r = W // 2, 118, 56
    pts = [(cx + r * math.cos(math.radians(a)),
            cy + r * math.sin(math.radians(a))) for a in range(0, 360, 60)]
    d.line(pts + [pts[0]], fill=accent + (225,), width=3)
    r2 = r - 12
    pts2 = [(cx + r2 * math.cos(math.radians(a)),
             cy + r2 * math.sin(math.radians(a))) for a in range(0, 360, 60)]
    d.line(pts2 + [pts2[0]], fill=accent + (90,), width=1)
    d.text((cx, cy + 2), "NXS", font=font(42), fill=accent + (255,), anchor="mm")
    d.text((cx, cy + r + 24), "N E X U S S E C   O S", font=font(20),
           fill=accent + (160,), anchor="mm")
    return layer


def corner_hud(accent):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    c = accent + (110,)
    m, ln = 46, 90
    for (x, y, sx, sy) in ((m, m, 1, 1), (W - m, m, -1, 1),
                           (m, H - m, 1, -1), (W - m, H - m, -1, -1)):
        d.line([x, y, x + sx * ln, y], fill=c, width=2)
        d.line([x, y, x, y + sy * ln], fill=c, width=2)
    return layer


# ----------------------------------------------------------------- compose
def glow_compose(base, layer, radius=9):
    blurred = layer.filter(ImageFilter.GaussianBlur(radius))
    base = Image.alpha_composite(base, blurred)
    return Image.alpha_composite(base, layer)


def make(name, accent_hex, deep_hex, label, focal=(W // 2, H // 2)):
    accent = hx(accent_hex)
    deep = hx(deep_hex)
    img = background(accent, deep, focal)
    img = Image.alpha_composite(img, starfield(hash(name) & 0xffff))
    img = Image.alpha_composite(img, honeycomb(accent))
    img = glow_compose(img, node_network(accent, hash(name) & 0xffff, focal), 4)
    img = glow_compose(img, emblem(name, accent), 10)
    img = Image.alpha_composite(img, corner_hud(accent))
    img = glow_compose(img, brand_badge(accent), 6)   # monogramma NXS in alto

    # filigrana: nome del profilo in basso a destra (il marchio e' in alto).
    d = ImageDraw.Draw(img)
    if label:
        d.text((W - 70, H - 86), label, font=font(40),
               fill=accent + (110,), anchor="ra")
    d.text((70, H - 74), "SECURE LIVE OS", font=font(20), fill=accent + (70,))
    out = os.path.join(DEST, name_to_file(name))
    img.convert("RGB").save(out, "PNG")
    print("generato", out)


def name_to_file(name):
    return {"base": "nebula.png"}.get(name, name + ".png")


if __name__ == "__main__":
    os.makedirs(DEST, exist_ok=True)
    make("base",      "#00e5ff", "#020611", "",            (W * 0.5,  H * 0.45))
    make("pentest",   "#ff3b5c", "#0c0205", "PEN TESTING", (W * 0.5,  H * 0.5))
    make("forensics", "#ffb000", "#05070f", "FORENSICS",   (W * 0.42, H * 0.45))
    make("osint",     "#23d18b", "#02100a", "OSINT",       (W * 0.5,  H * 0.5))
    make("web",       "#a06bff", "#070310", "WEB PENTEST", (W * 0.5,  H * 0.48))
    print("[wallpaper] fatto.")
