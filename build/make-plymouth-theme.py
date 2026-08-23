#!/usr/bin/env python3
"""Genera gli ASSET grafici del tema Plymouth 'nexussec' (splash di boot vera).

Rende una scena "cyber command" coerente con l'estetica NexusSec:
  sfondo #050a14 con griglia esagonale + vignette + glow centrale,
  emblema esagonale con glifo "N" e bagliore, glow pulsante, particelle
  orbitanti, wordmark luminoso, barra di avanzamento con testa luminosa,
  scanline. L'ANIMAZIONE e' in nexussec.script (Plymouth Script); qui creiamo
  solo i PNG che quello compone/anima.

A runtime la live NON gira PIL: gli asset sono pre-generati qui e committati in
overlay/usr/share/plymouth/themes/nexussec/. Coerente con make-icons.py.

Uso:  python3 build/make-plymouth-theme.py
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "overlay/usr/local/share/nexussec/splash"

# --- palette (coerente con nxs_cc / CLAUDE.md) --------------------------------
BG_TOP = (5, 10, 20)
BG_BOT = (8, 19, 31)
ACCENT = (0, 229, 255)
ACCENT_HI = (150, 245, 255)
TEXT = (200, 245, 255)
DIM = (90, 138, 154)
BORDER = (26, 58, 82)

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"


# --- helper -------------------------------------------------------------------
def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def hexagon_points(cx, cy, r):
    """Esagono punta-in-alto (come splash.py)."""
    pts = []
    for i in range(6):
        a = math.pi / 2 + i * math.pi / 3
        pts.append((cx + r * math.cos(a), cy - r * math.sin(a)))
    return pts


def add_glow(img, radius, gain=1.0):
    """Ritorna un layer di bagliore (blur) dello stesso contenuto RGBA."""
    glow = img.filter(ImageFilter.GaussianBlur(radius))
    if gain != 1.0:
        r, g, b, a = glow.split()
        a = a.point(lambda v: min(255, int(v * gain)))
        glow = Image.merge("RGBA", (r, g, b, a))
    return glow


def radial(size, color, max_alpha, power=2.0):
    """Glow radiale: centro brillante -> bordo trasparente."""
    grad = Image.radial_gradient("L").resize((size, size))  # 0 centro -> 255 bordo
    alpha = grad.point(lambda v: int(max_alpha * (1.0 - v / 255.0) ** power))
    img = Image.new("RGBA", (size, size), color + (0,))
    img.putalpha(alpha)
    return img


def vgradient(w, h, top, bot):
    base = Image.new("RGB", (1, h))
    px = base.load()
    for y in range(h):
        t = y / max(1, h - 1)
        px[0, y] = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
    return base.resize((w, h)).convert("RGBA")


def hgradient_rgba(w, h, left, right, a_left=255, a_right=255):
    base = Image.new("RGBA", (w, 1))
    px = base.load()
    for x in range(w):
        t = x / max(1, w - 1)
        px[x, 0] = tuple(int(left[i] + (right[i] - left[i]) * t) for i in range(3)) \
            + (int(a_left + (a_right - a_left) * t),)
    return base.resize((w, h))


def rounded_mask(w, h, r):
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
    return m


# --- asset generici -----------------------------------------------------------
def make_background(w=1920, h=1080):
    img = vgradient(w, h, BG_TOP, BG_BOT)
    cx, cy = w / 2, h * 0.355          # centro = dove sta l'emblema
    # esagoni concentrici tenui che "irradiano" dal logo (pulito, non affollato)
    hl = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dh = ImageDraw.Draw(hl)
    r = 250.0
    while r < w * 0.9:
        a = max(4, int(30 * (1.0 - (r - 250) / (w * 0.9))))
        dh.polygon(hexagon_points(cx, cy, r), outline=ACCENT + (a,), width=2)
        r += 150
    img.alpha_composite(hl)
    # glow centrale morbido dietro al logo
    g = radial(int(h * 1.05), ACCENT, 46, power=2.4)
    img.alpha_composite(g, (int(cx - g.width / 2), int(cy - g.height / 2)))
    # vignette (scurisce i bordi -> aria e profondita')
    vig = Image.new("L", (w, h), 0)
    ImageDraw.Draw(vig).ellipse([-w * 0.20, -h * 0.30, w * 1.20, h * 1.30], fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(200))
    dark = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dark.putalpha(Image.eval(vig, lambda v: 210 - int(v * 210 / 255)))
    img.alpha_composite(dark)
    # HUD: brackets angolari (aspetto "strumento" professionale)
    d = ImageDraw.Draw(img, "RGBA")
    m, L, tw = 74, 104, 3
    col = ACCENT + (150,)
    for (ox, oy, sx, sy) in [(m, m, 1, 1), (w - m, m, -1, 1),
                             (m, h - m, 1, -1), (w - m, h - m, -1, -1)]:
        d.line([ox, oy, ox + sx * L, oy], fill=col, width=tw)
        d.line([ox, oy, ox, oy + sy * L], fill=col, width=tw)
        d.ellipse([ox - 4, oy - 4, ox + 4, oy + 4], fill=col)
    img.save(OUT / "bg.png")


def make_ring(size=460):
    """Anello 'strumento' con tacche attorno all'emblema (statico, elegante)."""
    S = size * 2
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = S / 2
    R = S * 0.44
    d.ellipse([cx - R, cy - R, cx + R, cy + R], outline=ACCENT + (70,),
              width=max(2, int(S * 0.004)))
    # tacche radiali
    for i in range(60):
        ang = i * math.pi / 30
        long = (i % 5 == 0)
        r0 = R - (S * 0.028 if long else S * 0.014)
        a = 150 if long else 70
        d.line([cx + r0 * math.cos(ang), cy + r0 * math.sin(ang),
                cx + R * math.cos(ang), cy + R * math.sin(ang)],
               fill=ACCENT + (a,), width=max(2, int(S * 0.004)))
    # due archi piu' luminosi (dettaglio dinamico "attivo")
    bb = [cx - R, cy - R, cx + R, cy + R]
    d.arc(bb, -18, 42, fill=ACCENT_HI + (230,), width=max(3, int(S * 0.008)))
    d.arc(bb, 162, 222, fill=ACCENT_HI + (230,), width=max(3, int(S * 0.008)))
    img = img.resize((size, size), Image.LANCZOS)
    glow = add_glow(img, radius=size * 0.02, gain=1.4)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.alpha_composite(glow)
    out.alpha_composite(img)
    out.save(OUT / "ring.png")


def make_emblem(size=460):
    S = size * 2  # supersampling per bordi netti
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = S / 2
    ro = S * 0.34          # esagono esterno
    rm = S * 0.235         # esagono interno
    lw = max(6, int(S * 0.018))
    # esagono esterno pieno-accent
    d.polygon(hexagon_points(cx, cy, ro), outline=ACCENT + (255,), width=lw)
    # esagono interno tenue
    d.polygon(hexagon_points(cx, cy, rm), outline=ACCENT + (120,),
              width=max(3, lw // 2))
    # glifo "N" (due montanti + diagonale), come splash.py, scalato
    gx = S * 0.093
    gy = S * 0.107
    nlw = max(8, int(S * 0.026))
    pts = [(cx - gx, cy + gy), (cx - gx, cy - gy),
           (cx + gx, cy + gy), (cx + gx, cy - gy)]
    d.line(pts, fill=ACCENT_HI + (255,), width=nlw, joint="curve")
    # pallini ai vertici del glifo (dettaglio "nodo")
    for (px, py) in [pts[0], pts[1], pts[2], pts[3]]:
        rr = nlw * 0.9
        d.ellipse([px - rr, py - rr, px + rr, py + rr], fill=ACCENT_HI + (255,))
    # sei nodi luminosi ai vertici dell'esagono esterno
    for (px, py) in hexagon_points(cx, cy, ro):
        rr = lw * 1.15
        d.ellipse([px - rr, py - rr, px + rr, py + rr], fill=ACCENT + (255,))
    img = img.resize((size, size), Image.LANCZOS)
    # bagliore morbido sotto
    glow = add_glow(img, radius=size * 0.03, gain=1.6)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.alpha_composite(glow)
    out.alpha_composite(img)
    out.save(OUT / "emblem.png")


def make_glow():
    radial(760, ACCENT, 150, power=2.2).save(OUT / "glow.png")


def make_particle():
    p = radial(40, ACCENT_HI, 255, power=1.6)
    p.save(OUT / "particle.png")


def make_bar(w=760, h=14):
    # track: pillola scura bordata
    track = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dt = ImageDraw.Draw(track)
    dt.rounded_rectangle([0, 0, w - 1, h - 1], radius=h // 2,
                         fill=(10, 26, 38, 220), outline=BORDER + (255,), width=2)
    track.save(OUT / "bar_track.png")
    # fill: gradiente accent, mascherato a pillola
    fill = hgradient_rgba(w, h, (0, 150, 190), ACCENT_HI)
    fill.putalpha(rounded_mask(w, h, h // 2))
    fill.save(OUT / "bar_fill.png")
    # head: bagliore luminoso alla testa della barra
    radial(64, ACCENT_HI, 255, power=1.7).save(OUT / "bar_head.png")


def _text_png(text, font, color, name, glow_radius=8, glow_gain=1.6,
              tracking=0, pad=60):
    f = font
    # misura
    tmp = Image.new("RGBA", (10, 10))
    dd = ImageDraw.Draw(tmp)
    if tracking:
        widths = [dd.textbbox((0, 0), ch, font=f)[2] for ch in text]
        tw = sum(widths) + tracking * (len(text) - 1)
        bbox = dd.textbbox((0, 0), text, font=f)
        th = bbox[3] - bbox[1]
    else:
        bbox = dd.textbbox((0, 0), text, font=f)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
    W = int(tw + pad * 2)
    H = int(th + pad * 2)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if tracking:
        x = pad
        for ch in text:
            d.text((x, pad - bbox[1]), ch, font=f, fill=color + (255,))
            x += dd.textbbox((0, 0), ch, font=f)[2] + tracking
    else:
        d.text((pad - bbox[0], pad - bbox[1]), text, font=f, fill=color + (255,))
    if glow_radius:
        glow = add_glow(img, glow_radius, glow_gain)
        out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        out.alpha_composite(glow)
        out.alpha_composite(img)
        img = out
    img.save(OUT / name)


def make_texts():
    _text_png("NexusSec OS", _font(FONT_BOLD, 96), ACCENT, "wordmark.png",
              glow_radius=14, glow_gain=1.8)
    # tagline: professionale + richiamo all'IA (cuore del progetto)
    _text_png("AI-AUGMENTED SECURITY PLATFORM",
              _font(FONT_MONO, 28), (120, 200, 220), "tagline.png",
              glow_radius=6, glow_gain=1.2, tracking=8, pad=36)
    # footer: scope professionale multi-dominio + base
    _text_png("PENTEST   ·   FORENSICS   ·   OSINT   ·   WEB       ALPINE LINUX EDGE",
              _font(FONT_MONO, 20), DIM, "footer.png",
              glow_radius=0, tracking=4, pad=24)
    _text_png("edition 2026.08", _font(FONT_MONO, 18), BORDER, "version.png",
              glow_radius=0, tracking=3, pad=18)


def make_scan(w=1920, h=140):
    band = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    # linea centrale netta + alone (sottile e discreta)
    d = ImageDraw.Draw(band)
    d.rectangle([0, h // 2 - 1, w, h // 2 + 1], fill=ACCENT + (60,))
    band = band.filter(ImageFilter.GaussianBlur(2))
    halo = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(halo).rectangle([0, 0, w, h], fill=ACCENT + (8,))
    # sfuma verticalmente l'alone
    vmask = Image.new("L", (1, h))
    for y in range(h):
        t = 1.0 - abs(y - h / 2) / (h / 2)
        vmask.putpixel((0, y), int(255 * max(0, t) ** 1.5))
    halo.putalpha(vmask.resize((w, h)))
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.alpha_composite(halo)
    out.alpha_composite(band)
    out.save(OUT / "scan.png")


def make_scene():
    """Compone la scena STATICA completa e la salva come PNG (per riferimento)
    e come fbsplash.ppm (splash di BOOT nativo Alpine, initramfs -> copre tutto
    l'avvio incl. installazione desktop in RAM). 1920x1080; su pannelli piu'
    piccoli l'init la centra (IMG_ALIGN=CM) e i bordi scuri si fondono."""
    W, H = 1920, 1080
    cx, ecy = W // 2, int(H * 0.34)

    def L(n):
        return Image.open(OUT / (n + ".png")).convert("RGBA")

    scene = L("bg").resize((W, H))
    # glow dietro emblema
    g = L("glow")
    r, gg, b, a = g.split()
    g.putalpha(a.point(lambda v: int(v * 0.5)))
    scene.alpha_composite(g, (cx - g.width // 2, ecy - g.height // 2))
    # anello
    ring = L("ring")
    scene.alpha_composite(ring, (cx - ring.width // 2, ecy - ring.height // 2))
    # particelle statiche sull'anello
    part = L("particle")
    R = 175
    for i in range(6):
        ang = i * math.pi / 3 + 0.5
        px = int(cx + R * math.cos(ang))
        py = int(ecy + R * math.sin(ang))
        scene.alpha_composite(part, (px - part.width // 2, py - part.height // 2))
    # emblema
    em = L("emblem")
    scene.alpha_composite(em, (cx - em.width // 2, ecy - em.height // 2))
    # testi (stessa disposizione della splash X)
    for name, wfrac, yfrac in (("wordmark", 0.375, 0.585),
                               ("tagline", 0.44, 0.70),
                               ("footer", 0.52, 0.93),
                               ("version", 0.13, 0.965)):
        im = L(name)
        w = int(W * wfrac)
        h = int(im.height * (w / im.width))
        im = im.resize((w, h))
        scene.alpha_composite(im, (cx - w // 2, int(H * yfrac) - h // 2))
    scene = scene.convert("RGB")
    scene.save(OUT / "scene.png")
    scene.save(ROOT / "build-alpine" / "fbsplash.ppm")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    make_background()
    make_ring()
    make_emblem()
    make_glow()
    make_particle()
    make_bar()
    make_texts()
    make_scan()
    make_scene()
    print(f"[plymouth] asset generati in {OUT.relative_to(ROOT)}")
    for p in sorted(OUT.glob("*.png")):
        print(f"   {p.name:16} {p.stat().st_size:>8} B")


if __name__ == "__main__":
    main()
