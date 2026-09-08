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
    S = 16

    def base():
        img = Image.new("1", (S, S), 0)          # sfondo trasparente (bit 0)
        d = ImageDraw.Draw(img)
        d.ellipse([1, 1, S - 2, S - 2], fill=1)  # disco pieno (bit 1)
        return img, d

    def carve(d, segs, w=2):
        for seg in segs:
            d.line(seg, fill=0, width=w)         # scava il glifo (bit 0)

    masks = {
        # chiudi: X simmetrica
        "close.xbm":       [[(5, 5), (10, 10)], [(10, 5), (5, 10)]],
        # minimizza: barra orizzontale
        "iconify.xbm":     [[(5, 8), (10, 8)]],
        # massimizza: croce +
        "max.xbm":         [[(8, 5), (8, 10)], [(5, 8), (10, 8)]],
        "max_toggled.xbm": [[(8, 5), (8, 10)], [(5, 8), (10, 8)]],
    }
    for fname, segs in masks.items():
        img, d = base()
        carve(d, segs)
        img.save(os.path.join(dest_dir, fname))
    print("  + maschere pulsanti a sfera rigenerate (disco + glifo scavato)")


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
