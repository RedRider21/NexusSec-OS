#!/usr/bin/env python3
"""Genera le SKIN colore del pannello NexusSec (barra + menu + popup).

Ogni skin e' un file CSS statico in
  overlay/usr/local/share/nexussec/panel-themes/<id>.css
che sovrascrive SOLO le classi del pannello (.nxs-panel*, .nxs-popup, menu,
.nxs-menu-strip). Vengono caricate a priorita' piu' alta dell'accent del
profilo, quindi una skin a palette FISSA rende la barra indipendente dal
profilo. La skin speciale "profile" NON e' un file: assenza di skin = base +
accent del profilo (comportamento storico).

Uso:  python3 build/make-panel-themes.py     (rigenera i .css)
       make panel-themes
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "overlay", "usr", "local", "share",
                   "nexussec", "panel-themes")

# id -> palette. Chiavi colore:
#   bg   sfondo barra            pop  sfondo popup/menu
#   border bordi/separatori      text testo principale
#   dim  testo tenue             accent colore d'accento (icone, menu, attivo)
#   on_accent testo su fondo accent (pager attivo)
#   strip (3 stop del gradiente della banda verticale del menu)  brand testo banda
THEMES = {
    "hud": {
        "name": "HUD Cyan (fisso)",
        "bg": "#0a1a26", "pop": "#0a1a26", "border": "#1a3a52",
        "text": "#c8f5ff", "dim": "#5a8a9a", "accent": "#00e5ff",
        "on_accent": "#050a14",
        "strip": ("#03070f", "#00334a", "#00e5ff"), "brand": "#eafcff",
    },
    "dark": {
        "name": "Grigio scuro",
        "bg": "#1e1e1e", "pop": "#252525", "border": "#3a3a3a",
        "text": "#e6e6e6", "dim": "#8a8a8a", "accent": "#7aa2f7",
        "on_accent": "#0b0b0b",
        "strip": ("#161616", "#2a2a2a", "#7aa2f7"), "brand": "#ffffff",
    },
    "light": {
        "name": "Chiaro",
        "bg": "#f2f2f2", "pop": "#ffffff", "border": "#cfcfcf",
        "text": "#222222", "dim": "#6a6a6a", "accent": "#1a73e8",
        "on_accent": "#ffffff",
        "strip": ("#e6e6e6", "#c9d9f5", "#1a73e8"), "brand": "#0b3d91",
    },
    "nord": {
        "name": "Nord",
        "bg": "#2e3440", "pop": "#3b4252", "border": "#4c566a",
        "text": "#eceff4", "dim": "#81a1c1", "accent": "#88c0d0",
        "on_accent": "#2e3440",
        "strip": ("#2b303b", "#3b4252", "#88c0d0"), "brand": "#eceff4",
    },
    "solarized": {
        "name": "Solarized Dark",
        "bg": "#002b36", "pop": "#073642", "border": "#586e75",
        "text": "#eee8d5", "dim": "#93a1a1", "accent": "#2aa198",
        "on_accent": "#002b36",
        "strip": ("#00212b", "#073642", "#2aa198"), "brand": "#fdf6e3",
    },
    "matrix": {
        "name": "Terminal Green",
        "bg": "#000000", "pop": "#071a07", "border": "#0f3f0f",
        "text": "#33ff66", "dim": "#1f8f3f", "accent": "#33ff66",
        "on_accent": "#001100",
        "strip": ("#000000", "#052905", "#33ff66"), "brand": "#99ffaa",
    },
    "amber": {
        "name": "Retro Amber",
        "bg": "#140d00", "pop": "#1c1400", "border": "#4a3600",
        "text": "#ffb000", "dim": "#a06f00", "accent": "#ffb000",
        "on_accent": "#140d00",
        "strip": ("#0a0700", "#2a1e00", "#ffb000"), "brand": "#ffd27f",
    },
    "contrast": {
        "name": "Alto contrasto",
        "bg": "#000000", "pop": "#000000", "border": "#ffffff",
        "text": "#ffffff", "dim": "#cccccc", "accent": "#ffff00",
        "on_accent": "#000000",
        "strip": ("#000000", "#333300", "#ffff00"), "brand": "#ffff00",
    },
}

TEMPLATE = """\
/* name: {name} */
/* NexusSec - skin colore pannello (auto-generato da build/make-panel-themes.py).
   Palette FISSA: ignora l'accent del profilo. NON modificare a mano. */
.nxs-panel {{ background-color:{bg}; border-top:1px solid {border}; }}
.nxs-panel.nxs-panel-top {{ border-top:none; border-bottom:1px solid {border}; }}
.nxs-panel button {{ color:{text}; }}
.nxs-panel button:hover {{ background-color:{hover}; border-color:{border}; }}
.nxs-panel button:active {{ background-color:{active}; }}
.nxs-panel button image {{ color:{accent}; }}
.nxs-panel button.nxs-icon:hover image {{ color:{text}; }}
.nxs-panel button.nxs-menu {{ color:{accent}; }}
.nxs-panel button.nxs-menu image {{ color:{accent}; }}
.nxs-panel button.nxs-launcher image {{ color:{accent}; }}
.nxs-panel button.nxs-task {{ color:{dim}; }}
.nxs-panel button.nxs-task:hover {{ color:{text}; }}
.nxs-panel button.nxs-task-active {{ color:{accent}; background-color:{hover}; border-color:{border}; }}
.nxs-panel button.nxs-pager-btn {{ color:{dim}; border-color:{border}; }}
.nxs-panel button.nxs-pager-btn:hover {{ color:{text}; }}
.nxs-panel button.nxs-pager-active {{ color:{on_accent}; background-color:{accent}; border-color:{accent}; }}
.nxs-panel label.nxs-clock {{ color:{text}; }}
.nxs-panel label.nxs-clock-date {{ color:{dim}; }}
.nxs-panel separator {{ background-color:{border}; }}
.nxs-popup, .nxs-popup.background {{ background-color:{pop}; border:1px solid {border}; }}
menu, .menu, menu.background {{ background-color:{pop}; color:{text}; border:1px solid {border}; }}
menu menuitem {{ color:{text}; }}
menu menuitem:hover {{ background-color:{hover}; }}
popover.nxs-startmenu, popover.nxs-startmenu.background {{ background-color:{pop}; border:1px solid {border}; }}
popover.nxs-startmenu > arrow {{ background-color:{strip1}; border:1px solid {border}; }}
.nxs-menu-strip {{ background-image: linear-gradient(to top, {strip0}, {strip1} 45%, {strip2}); border-right:1px solid {border}; }}
.nxs-menu-strip label.brand {{ color:{brand}; }}
.nxs-menu-strip label.brand-sub {{ color:{brand}; }}
.nxs-startmenu-list button.nxs-menu-item {{ color:{text}; }}
/* Colore del TESTO di TUTTE le voci menu (lista E footer esci/riavvia/spegni):
   il CSS base forza le label a un colore chiaro (button.nxs-menu-item label),
   che sulla skin "Chiaro" sparirebbe sul fondo bianco. Sovrascriviamo con lo
   stesso selettore (stessa specificita', ma priorita' skin piu' alta). */
button.nxs-menu-item label {{ color:{text}; }}
.nxs-startmenu-list button.nxs-menu-item:hover {{ background-color:{hover}; }}
.nxs-startmenu-list button.nxs-menu-item:hover label {{ color:{accent}; }}
/* TUTTE le icone del menu start seguono la skin (righe tool, categorie, app,
   e il FOOTER esci/riavvia/spegni). NB: il menu e' una Gtk.Window (classe
   .nxs-popup) col contenuto in .nxs-startmenu, NON un elemento <popover>:
   quindi i selettori DEVONO essere per-CLASSE (element-agnostici), altrimenti
   il footer e altre parti restano col colore dell'accent del profilo. */
.nxs-startmenu button image,
.nxs-startmenu-list button image,
.nxs-startmenu-footer button image,
.nxs-popup button image {{ color:{accent}; }}
.nxs-startmenu-list label {{ color:{text}; }}
button.nxs-menu-cat, label.nxs-menu-cat {{ color:{dim}; }}
button.nxs-menu-cat:hover {{ color:{accent}; border-left-color:{accent}; }}
button.nxs-tool-item {{ color:{text}; }}
button.nxs-tool-item:hover {{ background-color:{hover}; }}
button.nxs-tool-item:hover label {{ color:{accent}; }}
entry.nxs-menu-search {{ background-color:{pop}; color:{text}; border:1px solid {border}; }}
entry.nxs-menu-search image {{ color:{dim}; }}
entry.nxs-menu-search:focus {{ border-color:{accent}; }}
"""


def _rgba(hexcol, alpha):
    h = hexcol.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return "rgba(%d,%d,%d,%.2f)" % (r, g, b, alpha)


def main():
    os.makedirs(OUT, exist_ok=True)
    for tid, p in THEMES.items():
        css = TEMPLATE.format(
            name=p["name"], bg=p["bg"], pop=p["pop"], border=p["border"],
            text=p["text"], dim=p["dim"], accent=p["accent"],
            on_accent=p["on_accent"], brand=p["brand"],
            hover=_rgba(p["accent"], 0.14), active=_rgba(p["accent"], 0.24),
            strip0=p["strip"][0], strip1=p["strip"][1], strip2=p["strip"][2],
        )
        with open(os.path.join(OUT, tid + ".css"), "w") as f:
            f.write(css)
        print("generato", tid + ".css", "(" + p["name"] + ")")
    print("skin in", os.path.normpath(OUT))


if __name__ == "__main__":
    main()
