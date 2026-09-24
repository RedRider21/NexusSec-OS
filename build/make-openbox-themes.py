#!/usr/bin/env python3
# NexusSec - genera i temi Openbox "coordinati col profilo".
#
# Da un template mono-colore (placeholder @ACCENT@) produce, per OGNI profilo,
# un tema Openbox statico tinto col colore di quel profilo. Cosi' quando l'utente
# sceglie una FAMIGLIA (Retro / Cards) e cambia profilo, la decorazione delle
# finestre segue il colore coordinato, restando pero' un file STATICO e curato
# (nessuna generazione a runtime: vedi CLAUDE.md, "tema Openbox statico").
#
# Famiglie:
#   - Retro  : deriva dal tema "1977" di Thayer Williams (flat, chiaro).
#   - Cards  : stile "scheda" iOS (header pieno a colori, corpo scuro), come le
#              card dei profili sul sito.
#
# Uso:  python3 build/make-openbox-themes.py
# Output: overlay/home/nexus/.themes/NexusSec-<Famiglia>-<profilo>/openbox-3/
#
# I template stanno in build/openbox-templates/<famiglia>/openbox-3/ (themerc.in
# + eventuali .xbm dei glifi dei pulsanti). Rigenerare dopo aver toccato un
# template o i colori dei profili in profiles.json.
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def gen_button_masks(dest_dir):
    """Genera le maschere .xbm dei pulsanti "a sfera" stile macOS/iOS.

    CONVENZIONE OPENBOX: un bit ACCESO (1) e' disegnato in image.color (il
    colore semaforo del pulsante); un bit SPENTO (0) e' trasparente e mostra lo
    sfondo (parentrelative = barra graphite). Quindi la maschera corretta e':
      - DISCO PIENO di bit accesi  -> la sfera colorata;
      - SIMBOLO scavato a bit spenti dentro il disco -> il glifo appare nel
        colore della barra (come inciso).
    In PIL mode "1": bianco(1) -> bit 1 (sfera), nero(0) -> bit 0 (trasparente).
    Le vecchie maschere erano INVERTITE (quadrato pieno con foro tondo): la
    sfera si vedeva come "cerchietto scuro" dentro un quadrato colorato.
    Se PIL non c'e', si tengono le .xbm gia' presenti nel template.
    """
    try:
        from PIL import Image, ImageDraw
    except Exception:
        print("  [i] PIL assente: uso le .xbm gia' presenti nel template")
        return
    # DIMENSIONE = 16px: Openbox NON scala le maschere dei pulsanti, le disegna
    # 1:1 e le RITAGLIA se piu' grandi del pulsante -> una maschera troppo grande
    # (es. 22px) si vede come una "fetta". 16px entra nel pulsante. Per un cerchio
    # 1-bit il piu' tondo possibile: disegno il DISCO in grigio ad alta risoluzione
    # (bordo-a-bordo), lo riduco con LANCZOS (antialias) e soglio -> scelta ottimale
    # dei pixel di contorno. Il GLIFO invece lo incido NITIDO alla dimensione
    # finale (linee crisp), cosi' - e + sono puliti e la X ben leggibile.
    # DIMENSIONE 14px: e' la dimensione STANDARD dei pulsanti Openbox. A 16px la
    # maschera eccedeva il pulsante e Openbox la RITAGLIAVA -> il disco (che tocca
    # i bordi) perdeva le calotte e sembrava "squadrato". A 14px combacia col
    # pulsante e resta TONDO. Geometria/dimensione allineate al tema Arc-Round
    # (the-zero885, GPL-3), la cui close.xbm e' un disco 14px con glifo scavato.
    S = 14
    q = 8
    SS = S * q
    C = (S - 1) / 2.0        # centro esatto (6.5): glifi SIMMETRICI
    ARM = 3.6                # semi-lunghezza dei tratti del glifo
    TH = 0.9                # semi-spessore dei tratti (~2px)

    def _disc():
        big = Image.new("L", (SS, SS), 0)
        ImageDraw.Draw(big).ellipse([0, 0, SS - 1, SS - 1], fill=255)
        return (big.resize((S, S), Image.LANCZOS)
                   .point(lambda p: 255 if p >= 128 else 0).convert("1"))

    def _hole(glyph, dx, dy):
        # dx,dy = distanza dal centro. Glifo = "foro" (bit 0) nel disco.
        if glyph == "close":                    # X: le due diagonali
            return (min(abs(dx - dy), abs(dx + dy)) <= TH
                    and max(abs(dx), abs(dy)) <= ARM)
        if glyph == "iconify":                  # - : barra orizzontale
            return abs(dy) <= TH and abs(dx) <= ARM
        # max / max_toggled -> + : barra orizzontale + verticale
        return ((abs(dx) <= TH and abs(dy) <= ARM)
                or (abs(dy) <= TH and abs(dx) <= ARM))

    def render(glyph):
        d = _disc()
        px = d.load()
        for y in range(S):
            for x in range(S):
                if px[x, y] and _hole(glyph, x - C, y - C):
                    px[x, y] = 0
        return d

    masks = {"close.xbm": "close", "iconify.xbm": "iconify",
             "max.xbm": "max", "max_toggled.xbm": "max"}
    for fname, glyph in masks.items():
        render(glyph).save(os.path.join(dest_dir, fname))
    print("  + maschere pulsanti a sfera rigenerate (%dpx, disco antialias + glifo simmetrico)" % S)


PROFILES_JSON = os.path.join(
    ROOT, "overlay/usr/local/share/nexussec/profiles.json")
TEMPLATES = os.path.join(ROOT, "build/openbox-templates")
THEMES_OUT = os.path.join(ROOT, "overlay/home/nexus/.themes")

# famiglia -> (nome cartella tema "NexusSec-<Suffix>-<profilo>")
FAMILIES = {"retro": "Retro", "cards": "Cards"}


def load_accents():
    with open(PROFILES_JSON, encoding="utf-8") as f:
        data = json.load(f)
    profs = data.get("profiles", data)
    out = {}
    for key, val in profs.items():
        acc = (val or {}).get("accent")
        if acc:
            out[key] = acc
    return out


def darken(hex_color, factor=0.72):
    """Restituisce una variante piu' scura di #rrggbb (per hover/pressed)."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return hex_color
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    r, g, b = (max(0, min(255, int(c * factor))) for c in (r, g, b))
    return "#%02x%02x%02x" % (r, g, b)


def render(template_text, accent):
    return (template_text
            .replace("@ACCENT_DK@", darken(accent))
            .replace("@ACCENT@", accent))


def gen_family(fam_dir, suffix, accents):
    src_ob = os.path.join(TEMPLATES, fam_dir, "openbox-3")
    themerc_in = os.path.join(src_ob, "themerc.in")
    if not os.path.isfile(themerc_in):
        print("  [!] template mancante: %s (salto)" % themerc_in)
        return 0
    with open(themerc_in, encoding="utf-8") as f:
        tpl = f.read()
    # La famiglia Cards usa maschere .xbm "a sfera": le (ri)generiamo nel
    # template stesso cosi' restano l'unica fonte di verita' (color-agnostiche).
    if fam_dir == "cards":
        gen_button_masks(src_ob)
    # glifi .xbm da copiare (color-agnostici); niente = pulsanti default Openbox
    xbms = [n for n in os.listdir(src_ob) if n.endswith(".xbm")]
    made = 0
    for key, accent in accents.items():
        name = "NexusSec-%s-%s" % (suffix, key)
        dest_ob = os.path.join(THEMES_OUT, name, "openbox-3")
        os.makedirs(dest_ob, exist_ok=True)
        with open(os.path.join(dest_ob, "themerc"), "w", encoding="utf-8") as f:
            f.write(render(tpl, accent))
        for x in xbms:
            shutil.copyfile(os.path.join(src_ob, x),
                            os.path.join(dest_ob, x))
        made += 1
        print("  + %s  (%s)" % (name, accent))
    return made


def mix(accent, bg, frac):
    """Miscela accent e bg (frac = quota di accent), per tinte scure coordinate."""
    a = [int(accent.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    b = [int(bg.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    return "#%02x%02x%02x" % tuple(
        int(round(x * frac + y * (1 - frac))) for x, y in zip(a, b))


# NexusSec-Core resta il tema HUD fisso per la DECORAZIONE delle finestre, ma il
# MENU del tasto destro deve seguire il profilo come il resto del desktop (prima
# restava ciano anche col profilo rosso/verde/ambra). Per ogni profilo diverso da
# base si genera NexusSec-Core-<profilo>: stesso themerc, cambiano SOLO le
# chiavi menu.* legate al colore. Base = NexusSec-Core originale (nessuna copia).
CORE_MENU_KEYS = {
    "menu.title.text.color": lambda a: a,
    "menu.items.active.bg.color": lambda a: mix(a, "#0a1a26", 0.25),
    "menu.items.active.text.color": lambda a: a,
    "menu.bullet.image.color": lambda a: darken(a, 0.85),
    "menu.bullet.selected.image.color": lambda a: a,
    "menu.separator.color": lambda a: mix(a, "#0a1a26", 0.2),
}
MENU_ICONS = os.path.join(ROOT, "overlay/usr/local/share/nexussec/menu-icons")
MENU_ICON_TINT = "#33b5d1"      # tinta delle icone di serie (make-menu-icons.py)


def gen_core_menu(accents):
    src = os.path.join(THEMES_OUT, "NexusSec-Core", "openbox-3")
    with open(os.path.join(src, "themerc"), encoding="utf-8") as f:
        righe = f.read().splitlines()
    made = 0
    for key, accent in accents.items():
        if key == "base":
            continue
        out = []
        for r in righe:
            k = r.split(":", 1)[0].strip()
            if k in CORE_MENU_KEYS and ":" in r:
                r = "%s: %s" % (k, CORE_MENU_KEYS[k](accent))
            out.append(r)
        dest = os.path.join(THEMES_OUT, "NexusSec-Core-%s" % key, "openbox-3")
        os.makedirs(dest, exist_ok=True)
        with open(os.path.join(dest, "themerc"), "w", encoding="utf-8") as f:
            f.write("# GENERATO da build/make-openbox-themes.py da NexusSec-Core:\n"
                    "# cambiano solo i colori del menu (profilo %s).\n" % key)
            f.write("\n".join(out) + "\n")
        for x in os.listdir(src):
            if x.endswith(".xbm"):
                shutil.copyfile(os.path.join(src, x), os.path.join(dest, x))
        made += 1
        print("  + NexusSec-Core-%s  (menu %s)" % (key, accent))
    return made


def gen_menu_icons(accents):
    """Icone del menu tinte col colore di ogni profilo: menu-icons-<profilo>/
    (base usa menu-icons/ di serie). Le icone d'allarme restano rosa."""
    made = 0
    for key, accent in accents.items():
        if key == "base":
            continue
        tinta = darken(accent, 0.85)
        dest = MENU_ICONS + "-" + key
        os.makedirs(dest, exist_ok=True)
        for n in sorted(os.listdir(MENU_ICONS)):
            if not n.endswith(".svg"):
                continue
            with open(os.path.join(MENU_ICONS, n), encoding="utf-8") as f:
                svg = f.read()
            svg = svg.replace(MENU_ICON_TINT, tinta).replace(
                MENU_ICON_TINT.upper(), tinta)
            with open(os.path.join(dest, n), "w", encoding="utf-8") as f:
                f.write(svg)
        made += 1
        print("  + menu-icons-%s  (%s)" % (key, tinta))
    return made


def main():
    accents = load_accents()
    if not accents:
        print("Nessun accent trovato in profiles.json", file=sys.stderr)
        return 1
    print("Profili: " + ", ".join("%s=%s" % kv for kv in accents.items()))
    total = 0
    for fam_dir, suffix in FAMILIES.items():
        print("Famiglia %s -> NexusSec-%s-*" % (fam_dir, suffix))
        total += gen_family(fam_dir, suffix, accents)
    print("Famiglia core (solo menu) -> NexusSec-Core-*")
    total += gen_core_menu(accents)
    print("Icone del menu per profilo")
    gen_menu_icons(accents)
    print("Fatto: %d temi generati in %s" % (total, THEMES_OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
