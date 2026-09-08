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
}


def _load_maker():
    path = os.path.join(ROOT, "build/make-wallpaper.py")
    spec = importlib.util.spec_from_file_location("nxs_make_wallpaper", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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
    print("[panel-wallpapers] fatto: %d sfondi in %s" % (len(SKINS), OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
