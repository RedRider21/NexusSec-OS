#!/usr/bin/env python3
# NexusSec - genera gli SFONDI abbinati ai TEMI DEL PANNELLO (skin).
#
# Sono una scelta SEPARATA e indipendente dal profilo e dalla skin attiva: si
# selezionano a parte dal Centro di Controllo (o con `nxs-wallpaper`). Per ogni
# palette skin produce uno sfondo 1920x1080 nello stesso stile "badge" degli
# sfondi profilo (gradiente + honeycomb + nodi + emblema), tinto con l'ACCENT
# della skin, cosi' "va in accordo" con quella colorazione.
#
# Uso:  python3 build/make-panel-wallpapers.py   (oppure: make panel-wallpapers)
# Output: overlay/usr/local/share/nexussec/wallpapers/skin-<id>.png
import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "overlay/usr/local/share/nexussec/wallpapers")

# id skin -> (accent, deep bg, etichetta). Palette allineate a make-panel-themes.
# 'deep' = fondo molto scuro: anche per la skin "Chiaro" lo sfondo resta scuro
# (dietro le finestre) ma con l'ACCENT della skin, cosi' armonizza col tema.
SKINS = {
    "hud":       ("#00e5ff", "#04101a", "HUD"),
    "dark":      ("#7aa2f7", "#0c0e12", "Grigio scuro"),
    "light":     ("#1a73e8", "#080d16", "Chiaro"),
    "nord":      ("#88c0d0", "#20262f", "Nord"),
    "solarized": ("#2aa198", "#00212b", "Solarized"),
    "matrix":    ("#33ff66", "#010a01", "Matrix"),
    "amber":     ("#ffb000", "#0a0700", "Amber"),
    "contrast":  ("#ffff00", "#000000", "Alto contrasto"),
    "black":     ("#e8e8e8", "#000000", "Nero"),
}
# "white" ha uno sfondo CHIARO: generato a parte (il maker scuro userebbe testi
# chiari invisibili sul bianco).


def _load_maker():
    path = os.path.join(ROOT, "build/make-wallpaper.py")
    spec = importlib.util.spec_from_file_location("nxs_make_wallpaper", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_white(mw):
    """Sfondo CHIARO per la skin 'Bianco': gradiente bianco->grigio chiarissimo,
    honeycomb tenue e badge esagonale SCURO con wordmark scuro (leggibile su
    fondo chiaro)."""
    from PIL import Image, ImageDraw, ImageFilter
    W, H = mw.W, mw.H
    ink = (26, 26, 26)          # inchiostro scuro
    img = Image.new("RGB", (W, H), (255, 255, 255))
    # gradiente verticale bianco -> grigio chiarissimo
    top, bot = (255, 255, 255), (232, 236, 241)
    px = img.load()
    for y in range(H):
        t = y / (H - 1)
        row = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
        for x in range(W):
            px[x, y] = row
    img = img.convert("RGBA")
    # honeycomb tenue (grigio)
    img = Image.alpha_composite(img, mw.honeycomb((120, 130, 140), alpha=16))
    d = ImageDraw.Draw(img, "RGBA")
    cx, cy = W // 2, int(H * 0.44)
    R = 150
    pts = mw._hexpts(cx, cy, R)
    d.polygon(pts, fill=(255, 255, 255, 255), outline=ink + (255,))
    d.line(pts + [pts[0]], fill=ink + (255,), width=3)
    fN = mw.font(190)
    tw = d.textlength("N", font=fN)
    d.text((cx - tw / 2, cy - 118), "N", font=fN, fill=ink + (255,))
    fW = mw.font(72)
    wm = "NexusSec"; ww = d.textlength(wm, font=fW)
    d.text((cx - ww / 2, cy + 180), wm, font=fW, fill=ink + (255,))
    ft = mw.font(30)
    spaced = " ".join("BIANCO")
    lw = d.textlength(spaced, font=ft)
    px0, py0 = cx - lw / 2 - 28, cy + 292
    d.rounded_rectangle([px0, py0, cx + lw / 2 + 28, py0 + 56], radius=28,
                        fill=(240, 242, 246), outline=ink + (255,))
    d.text((cx - lw / 2, py0 + 11), spaced, font=ft, fill=ink + (255,))
    out = os.path.join(OUT, "skin-white.png")
    img.convert("RGB").save(out, "PNG")
    print("generato", out)


def main():
    os.makedirs(OUT, exist_ok=True)
    try:
        mw = _load_maker()
    except Exception as e:                       # noqa: BLE001
        print("impossibile caricare make-wallpaper.py (serve PIL):", e)
        return 1
    mw.DEST = OUT                                 # reindirizza l'output
    W, H = mw.W, mw.H
    for sid, (accent, deep, label) in SKINS.items():
        mw.make("skin-" + sid, accent, deep, label, (W * 0.5, H * 0.44))
    make_white(mw)                               # sfondo chiaro dedicato
    print("[panel-wallpapers] fatto: %d sfondi in %s" % (len(SKINS) + 1, OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
