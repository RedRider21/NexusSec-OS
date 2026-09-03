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
    print("Fatto: %d temi generati in %s" % (total, THEMES_OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
