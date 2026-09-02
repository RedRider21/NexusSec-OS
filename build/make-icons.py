#!/usr/bin/env python3
"""Genera temi icone per profilo (NexusSec-<profilo>) tinti con l'accent.

Per ogni profilo (base/pentest/forensics/osint/web) crea un tema icone flat in
`overlay/usr/local/share/icons/NexusSec-<Profilo>/` con le icone piu' visibili
(cartelle, home, lanciatori NexusSec, browser, alcuni mimetype) colorate con
l'accent del profilo. Il tema EREDITA nuoveXT2/Adwaita per la copertura del
resto, quindi non serve disegnare centinaia di icone.

A runtime la live NON ha PIL: i temi sono pre-generati qui e la commutazione al
cambio profilo e' una semplice scelta di gtk-icon-theme-name (vedi
nxs_profiles.model.set_icon_theme).

Stile: tile flat arrotondato in accent + glifo bianco; le cartelle hanno la
classica forma a cartella in accent. Coerente con l'estetica piatta del progetto.
"""
from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ICONS_DIR = ROOT / "overlay/usr/local/share/icons"

# accent per profilo (allineato a profiles.json)
PROFILES = {
    "base":      ("NexusSec-Base",      "#00e5ff"),
    "pentest":   ("NexusSec-Pentest",   "#ff3b5c"),
    "forensics": ("NexusSec-Forensics", "#ffb000"),
    "osint":     ("NexusSec-Osint",     "#23d18b"),
    "web":       ("NexusSec-Web",       "#a06bff"),
}

SIZES = [16, 22, 24, 32, 48, 64, 128, 256]
R = 256  # risoluzione di disegno, poi downscale

WHITE = (245, 251, 255, 255)
DARK = (5, 10, 20, 255)


def hex2rgba(h: str, a: int = 255):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


def shade(rgba, f: float):
    """Scurisce/schiarisce un colore (f<1 scurisce, f>1 schiarisce)."""
    r, g, b, a = rgba
    return (max(0, min(255, int(r * f))), max(0, min(255, int(g * f))),
            max(0, min(255, int(b * f))), a)


def tile(d: ImageDraw.ImageDraw, accent):
    """Sfondo a tile flat arrotondato in accent (per le icone-app)."""
    pad = 24
    d.rounded_rectangle([pad, pad, R - pad, R - pad], radius=44,
                        fill=accent)


# ---- glifi (su tile, in bianco) ----------------------------------------
def g_browser(d, accent):
    tile(d, accent)
    cx, cy, rr = R // 2, R // 2, 64
    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=WHITE, width=10)
    d.line([cx - rr, cy, cx + rr, cy], fill=WHITE, width=8)
    d.arc([cx - 30, cy - rr, cx + 30, cy + rr], 0, 360, fill=WHITE, width=8)
    d.line([cx, cy - rr, cx, cy + rr], fill=WHITE, width=6)


def g_terminal(d, accent):
    tile(d, accent)
    d.rounded_rectangle([70, 80, R - 70, R - 80], radius=14, outline=WHITE,
                        width=9)
    d.line([92, 116, 122, 138, 92, 160], joint="curve", fill=WHITE, width=10)
    d.line([132, 162, 176, 162], fill=WHITE, width=10)


def g_gear(d, accent):
    tile(d, accent)
    import math
    cx, cy = R // 2, R // 2
    ro, ri = 70, 30
    pts = []
    teeth = 8
    for i in range(teeth * 2):
        ang = math.pi * i / teeth
        rad = ro if i % 2 == 0 else ro - 22
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    d.polygon(pts, fill=WHITE)
    d.ellipse([cx - ri, cy - ri, cx + ri, cy + ri], fill=accent)


def g_disk(d, accent):
    tile(d, accent)
    d.rounded_rectangle([74, 96, R - 74, R - 96], radius=16, outline=WHITE,
                        width=9)
    cx = cy = R // 2
    d.ellipse([cx - 16, cy - 16, cx + 16, cy + 16], outline=WHITE, width=8)
    d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=WHITE)


def g_doc(d, accent):
    """Mimetype generico: documento bianco con bordo e angolo, tinta accent."""
    x0, y0, x1, y1 = 78, 50, R - 78, R - 50
    fold = 44
    d.polygon([(x0, y0), (x1 - fold, y0), (x1, y0 + fold), (x1, y1), (x0, y1)],
              fill=WHITE)
    d.polygon([(x1 - fold, y0), (x1 - fold, y0 + fold), (x1, y0 + fold)],
              fill=shade(accent, 0.7))
    for yy in (110, 140, 170, 200):
        d.line([x0 + 26, yy, x1 - 26, yy], fill=accent, width=8)


def g_exec(d, accent):
    tile(d, accent)
    # chip
    d.rounded_rectangle([88, 88, R - 88, R - 88], radius=12, outline=WHITE,
                        width=9)
    for off in (-40, 0, 40):
        d.line([R // 2 + off, 60, R // 2 + off, 88], fill=WHITE, width=8)
        d.line([R // 2 + off, R - 88, R // 2 + off, R - 60], fill=WHITE, width=8)
        d.line([60, R // 2 + off, 88, R // 2 + off], fill=WHITE, width=8)
        d.line([R - 88, R // 2 + off, R - 60, R // 2 + off], fill=WHITE, width=8)


def g_folder(d, accent, opened=False):
    """Cartella flat in accent (per places)."""
    top = shade(accent, 1.15)
    body = accent
    # linguetta
    d.rounded_rectangle([40, 70, 130, 110], radius=10, fill=top)
    # corpo
    d.rounded_rectangle([40, 92, R - 40, R - 56], radius=18, fill=body)
    if opened:
        d.polygon([(40, R - 56), (84, 132), (R - 16, 132), (R - 40, R - 56)],
                  fill=shade(accent, 1.25))


def g_home(d, accent):
    tile(d, accent)
    # casetta
    d.polygon([(R // 2, 70), (R - 78, 140), (78, 140)], fill=WHITE)
    d.rectangle([96, 140, R - 96, R - 86], fill=WHITE)
    d.rectangle([R // 2 - 22, R - 150, R // 2 + 22, R - 86], fill=accent)


def g_editor(d, accent):
    """Editor di testo: tile accent + foglio con righe + matita (coerente con le
    altre icone-app tile+glifo). Serve per Icon=accessories-text-editor, che il
    tema di sistema renderebbe grigia (non tinta col profilo)."""
    tile(d, accent)
    # foglio bianco con angolo ripiegato (a sinistra)
    x0, y0, x1, y1 = 72, 56, 178, R - 56
    fold = 32
    d.polygon([(x0, y0), (x1 - fold, y0), (x1, y0 + fold), (x1, y1), (x0, y1)],
              fill=WHITE)
    d.polygon([(x1 - fold, y0), (x1 - fold, y0 + fold), (x1, y0 + fold)],
              fill=shade(accent, 0.7))
    for yy in (104, 134, 164, 194):
        d.line([x0 + 20, yy, x1 - 22, yy], fill=accent, width=7)
    # matita diagonale verso l'angolo in alto a destra
    d.line([150, R - 82, R - 64, 150], fill=WHITE, width=20)
    d.line([150, R - 82, R - 64, 150], fill=shade(accent, 0.5), width=8)
    d.polygon([(R - 64, 150), (R - 46, 132), (R - 38, 168)], fill=WHITE)


def g_theme(d, accent):
    """Aspetto/tema: tavolozza del pittore con gocce di colore."""
    tile(d, accent)
    d.ellipse([60, 70, R - 60, R - 62], fill=WHITE)
    d.ellipse([150, 150, 198, 198], fill=accent)          # foro del pollice
    for px, py, col in [(104, 116, (255, 59, 92, 255)),
                        (152, 100, (255, 176, 0, 255)),
                        (198, 122, (35, 209, 139, 255)),
                        (108, 170, (160, 107, 255, 255))]:
        d.ellipse([px - 15, py - 15, px + 15, py + 15], fill=col)


def g_wallpaper(d, accent):
    """Sfondo: cornice con montagne e sole (icona 'immagine')."""
    tile(d, accent)
    d.rounded_rectangle([60, 72, R - 60, R - 72], radius=16, fill=WHITE)
    d.rectangle([78, 90, R - 78, R - 90], fill=shade(accent, 0.9))
    d.ellipse([R - 140, 108, R - 106, 142], fill=WHITE)   # sole
    d.polygon([(78, R - 90), (146, 150), (196, R - 90)], fill=WHITE)
    d.polygon([(150, R - 90), (200, 168), (R - 78, R - 90)],
              fill=shade(WHITE, 0.88))


def g_window(d, accent):
    """Finestra: cornice con barra del titolo e tre bottoni."""
    tile(d, accent)
    d.rounded_rectangle([68, 72, R - 68, R - 72], radius=14, fill=WHITE)
    d.rectangle([74, 78, R - 74, 112], fill=shade(accent, 0.72))
    for cx in (92, 116, 140):
        d.ellipse([cx - 6, 89, cx + 6, 101], fill=WHITE)


def g_mouse(d, accent):
    """Mouse: corpo arrotondato, divisorio e rotella."""
    tile(d, accent)
    d.rounded_rectangle([100, 68, R - 100, R - 68], radius=48,
                        outline=WHITE, width=11)
    d.line([R // 2, 80, R // 2, 128], fill=WHITE, width=8)
    d.rounded_rectangle([R // 2 - 7, 92, R // 2 + 7, 116], radius=7, fill=WHITE)


def g_monitor(d, accent):
    """Schermo/computer: monitor con piede."""
    tile(d, accent)
    d.rounded_rectangle([58, 76, R - 58, R - 104], radius=14, fill=WHITE)
    d.rectangle([76, 92, R - 76, R - 120], fill=shade(accent, 0.88))
    d.rectangle([R // 2 - 28, R - 104, R // 2 + 28, R - 84], fill=WHITE)
    d.rounded_rectangle([R // 2 - 58, R - 86, R // 2 + 58, R - 66],
                        radius=8, fill=WHITE)


def g_monitor_graph(d, accent):
    """Monitor di sistema: riquadro con istogramma."""
    tile(d, accent)
    d.rounded_rectangle([66, 68, R - 66, R - 68], radius=14,
                        outline=WHITE, width=10)
    base = R - 92
    for x, h in [(102, 46), (138, 92), (174, 64)]:
        d.rectangle([x, base - h, x + 22, base], fill=WHITE)


def g_package(d, accent):
    """Installa pacchetto: freccia verso il basso dentro una scatola."""
    tile(d, accent)
    cx = R // 2
    d.line([cx, 62, cx, 128], fill=WHITE, width=13)
    d.polygon([(cx - 28, 112), (cx + 28, 112), (cx, 150)], fill=WHITE)
    d.rounded_rectangle([78, 150, R - 78, R - 70], radius=12, fill=WHITE)
    d.rounded_rectangle([78, 150, R - 78, R - 70], radius=12,
                        outline=shade(accent, 0.7), width=7)


def g_keyboard(d, accent):
    """Tastiera: file di tasti + barra spaziatrice."""
    tile(d, accent)
    d.rounded_rectangle([54, 86, R - 54, R - 86], radius=16, fill=WHITE)
    for ry in (104, 132):
        rx = 78
        while rx < R - 92:
            d.rounded_rectangle([rx, ry, rx + 22, ry + 18], radius=4,
                                fill=accent)
            rx += 32
    d.rounded_rectangle([104, 156, R - 104, 172], radius=4, fill=accent)


def g_network(d, accent):
    """Rete: tre nodi collegati."""
    tile(d, accent)
    nodes = [(R // 2, 92), (94, R - 100), (R - 94, R - 100)]
    for a, b in [(0, 1), (0, 2), (1, 2)]:
        d.line([nodes[a][0], nodes[a][1], nodes[b][0], nodes[b][1]],
               fill=WHITE, width=8)
    for nx, ny in nodes:
        d.ellipse([nx - 24, ny - 24, nx + 24, ny + 24], fill=WHITE)
        d.ellipse([nx - 12, ny - 12, nx + 12, ny + 12], fill=accent)


def g_security(d, accent):
    """Sicurezza/hardening: scudo bianco con spunta accent. Distinto dal
    firewall (muro di mattoni) perche' vivono nella stessa sezione."""
    tile(d, accent)
    cx = R // 2
    d.polygon([(cx, 58), (R - 70, 88), (R - 70, 142), (cx, R - 76),
               (70, 142), (70, 88)], fill=WHITE)
    # spunta interna in accent (unico colore del tema, ricolorata per profilo)
    d.line([(98, 134), (118, 154)], fill=accent, width=16, joint="curve")
    d.line([(118, 154), (160, 106)], fill=accent, width=16, joint="curve")


def g_users(d, accent):
    """Utenti: gruppo di due persone (testa + spalle), una dietro l'altra."""
    tile(d, accent)
    # persona posteriore
    d.ellipse([98, 66, 142, 110], fill=WHITE)
    d.pieslice([84, 122, 156, 194], 180, 360, fill=WHITE)
    # persona anteriore (piu' grande, davanti)
    d.ellipse([140, 104, 190, 154], fill=WHITE)
    d.pieslice([128, 160, 202, 222], 180, 360, fill=WHITE)


def g_bluetooth(d, accent):
    """Bluetooth: glifo runico riconoscibile (asta verticale + doppio
    triangolo/diamante al centro)."""
    tile(d, accent)
    cx = R // 2
    d.line([(cx, 56), (cx, R - 56)], fill=WHITE, width=13)
    for xa, ya in ((86, 100), (R - 86, 100), (R - 86, R - 100), (86, R - 100)):
        d.line([(cx, cx), (xa, ya)], fill=WHITE, width=13)


def g_firewall(d, accent):
    """Firewall: muro di mattoni bianco con malta accent (leggibile anche
    piccolo, giunti verticali sfalsati riga per riga)."""
    tile(d, accent)
    x0, x1 = 58, R - 58
    y0, y1 = 60, R - 60
    d.rounded_rectangle([x0, y0, x1, y1], radius=14, fill=WHITE)
    my = (104, 148)                    # righe di malta orizzontali
    for y in my:
        d.line([x0 + 8, y, x1 - 8, y], fill=accent, width=7)
    rows = [(110, 160), (78, 128, 180), (110, 160)]   # giunti verticali sfalsati
    yb = (y0, my[0], my[1], y1)
    for ri, xs in enumerate(rows):
        for x in xs:
            d.line([x, yb[ri] + 8, x, yb[ri + 1] - 8], fill=accent, width=7)


def g_run(d, accent):
    """Avvia/autostart: triangolo play."""
    tile(d, accent)
    d.polygon([(106, 78), (106, R - 78), (R - 86, R // 2)], fill=WHITE)


def g_refresh(d, accent):
    """Aggiorna: freccia circolare."""
    tile(d, accent)
    cx = cy = R // 2
    rr = 62
    d.arc([cx - rr, cy - rr, cx + rr, cy + rr], 300, 200, fill=WHITE, width=15)
    d.polygon([(cx + rr - 26, cy - rr + 6), (cx + rr + 20, cy - rr - 4),
               (cx + rr + 6, cy - rr + 40)], fill=WHITE)


def g_check(d, accent):
    """Conferma (emblem-ok): spunta bianca."""
    tile(d, accent)
    d.line([86, R // 2, 138, R - 92], fill=WHITE, width=22, joint="curve")
    d.line([138, R - 92, R - 82, 92], fill=WHITE, width=22, joint="curve")


def g_close(d, accent):
    """Chiudi: X bianca."""
    tile(d, accent)
    d.line([94, 94, R - 94, R - 94], fill=WHITE, width=20)
    d.line([R - 94, 94, 94, R - 94], fill=WHITE, width=20)


def g_logo(d, accent):
    """Logo NexusSec per il pulsante Start della barra: esagono PIENO in accent
    con monogramma N scuro. Full-color (non simbolico) -> resta tinto per profilo
    senza essere ricolorato dal CSS del pannello."""
    import math
    cx = cy = R // 2
    r = R * 0.44
    pts = [(cx + r * math.cos(math.pi / 6 + math.pi / 3 * i),
            cy + r * math.sin(math.pi / 6 + math.pi / 3 * i)) for i in range(6)]
    d.polygon(pts, fill=accent)
    w = 24
    x0, x1 = cx - 42, cx + 42
    yt, yb = cy - 54, cy + 54
    d.line([x0, yb, x0, yt], fill=DARK, width=w)
    d.line([x1, yb, x1, yt], fill=DARK, width=w)
    d.line([x0, yt, x1, yb], fill=DARK, width=w)


def g_screensaver(d, accent):
    """Salvaschermo: monitor con stelle/nebulosa (per preferences-desktop-
    screensaver, che Adwaita a colori non copre piu')."""
    tile(d, accent)
    d.rounded_rectangle([58, 72, R - 58, R - 104], radius=14, fill=WHITE)
    d.rectangle([76, 90, R - 76, R - 120], fill=shade(accent, 0.85))
    # piede
    d.rectangle([R // 2 - 28, R - 104, R // 2 + 28, R - 84], fill=WHITE)
    d.rounded_rectangle([R // 2 - 58, R - 86, R // 2 + 58, R - 66],
                        radius=8, fill=WHITE)
    # stelline nello schermo
    for sx, sy, rr in [(112, 128, 7), (150, 108, 5), (176, 150, 6),
                       (200, 120, 4), (132, 160, 4)]:
        d.ellipse([sx - rr, sy - rr, sx + rr, sy + rr], fill=WHITE)


def g_video(d, accent):
    """Visualizzatore video: tile accent + schermo bianco con triangolo play.

    Per Icon=nxs-video (nxs-video.desktop): senza, il tema userebbe un'icona
    generica grigia. Cosi' segue l'accent del profilo come le altre app."""
    tile(d, accent)
    # schermo bianco arrotondato
    d.rounded_rectangle([64, 84, R - 64, R - 84], radius=16, fill=WHITE)
    # triangolo play in accent al centro
    cx, cy = R // 2, R // 2
    d.polygon([(cx - 26, cy - 40), (cx - 26, cy + 40), (cx + 42, cy)],
              fill=accent)


def g_player(d, accent):
    """Lettore audio: tile accent + nota musicale (croma) bianca.

    Serve per Icon=nxs-player (nxs-player.desktop). Senza, il tema di sistema
    userebbe 'multimedia-player' che Adwaita recente rende grigia (non tinta
    col profilo). Cosi' segue l'accent del profilo come le altre icone-app."""
    tile(d, accent)
    # gambo destro
    d.line([R - 96, 78, R - 96, R - 96], fill=WHITE, width=16)
    # gambo sinistro
    d.line([120, 104, 120, R - 78], fill=WHITE, width=16)
    # traversa che unisce le due teste (bandierina della nota doppia)
    d.polygon([(120, 78), (R - 88, 60), (R - 88, 104), (120, 122)], fill=WHITE)
    # testa sinistra
    d.ellipse([80, R - 118, 152, R - 62], fill=WHITE)
    # testa destra
    d.ellipse([R - 136, R - 136, R - 64, R - 80], fill=WHITE)


# nome-icona -> (funzione, contesto)
def g_forensic(d, accent):
    """Caso forense: lente d ingrandimento sul piatto di un disco.

    Si legge come "esaminare un supporto" - il gesto che nxs-case automatizza -
    e resta riconoscibile anche a 16 px, dove restano solo due cerchi e un
    manico. Volutamente NON una cartella: la cartella e' il contenitore, non
    il mestiere.
    """
    tile(d, accent)
    # piatto del disco, in basso a sinistra
    d.ellipse([44, 92, 168, 216], outline=WHITE, width=9)
    d.ellipse([98, 146, 114, 162], fill=WHITE)
    # lente: cerchio spesso in alto a destra, leggermente sovrapposto
    d.ellipse([116, 40, 212, 136], outline=WHITE, width=13)
    # impugnatura verso il basso a destra
    d.line([200, 124, 226, 150], fill=WHITE, width=17)


def _qbez(p0, p1, p2, n=24):
    """Campiona una bezier quadratica in n punti (PIL non le disegna nativamente)."""
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        x = u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0]
        y = u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]
        pts.append((x, y))
    return pts


def g_horus(d, accent):
    """Occhio di Horus (Wedjat) con pupilla a globo: l'occhio che vede il globo.

    Horus e' il figlio di Osiris: il logo del discendente 'locale e privato'
    dello strumento OSIRIS. Sopracciglio + palpebre + la linea che scende e la
    spirale (i tratti canonici del Wedjat); la pupilla e' un piccolo globo con
    meridiani. A 16 px restano l'occhio e il globo, che bastano a riconoscerlo.
    """
    tile(d, accent)
    w = 14
    # sopracciglio
    d.line(_qbez((44, 80), (124, 36), (220, 68)), fill=WHITE, width=w, joint="curve")
    # palpebra superiore
    d.line(_qbez((32, 136), (104, 72), (216, 108)), fill=WHITE, width=w, joint="curve")
    # palpebra inferiore
    d.line(_qbez((32, 136), (112, 176), (184, 148)), fill=WHITE, width=w, joint="curve")
    # linea che scende dall'angolo interno
    d.line([(60, 156), (48, 208)], fill=WHITE, width=w, joint="curve")
    # spirale/curl dall'angolo esterno
    curl = _qbez((180, 152), (188, 200), (148, 208)) + _qbez((148, 208), (124, 212), (128, 184))
    d.line(curl, fill=WHITE, width=w, joint="curve")
    # pupilla = globo con meridiani
    d.ellipse([80, 96, 146, 162], outline=WHITE, width=w)
    d.line([(84, 129), (142, 129)], fill=WHITE, width=6)
    d.ellipse([106, 96, 120, 162], outline=WHITE, width=6)


ICONS = {
    "nxs-browser":          (g_browser, "apps"),
    "applications-internet": (g_browser, "apps"),
    "web-browser":          (g_browser, "apps"),
    "nxs-player":           (g_player, "apps"),
    "multimedia-player":    (g_player, "apps"),
    "audio-x-generic":      (g_player, "apps"),
    "nxs-video":            (g_video, "apps"),
    "video-x-generic":      (g_video, "apps"),
    "nxs-logo":             (g_logo, "apps"),
    "nxs-case":             (g_forensic, "apps"),
    "nxs-horus":            (g_horus, "apps"),
    "utilities-terminal":   (g_terminal, "apps"),
    "preferences-system":   (g_gear, "apps"),
    "drive-harddisk":       (g_disk, "apps"),
    "system-file-manager":  (lambda d, a: g_folder(d, a, opened=True), "apps"),
    "accessories-text-editor": (g_editor, "apps"),
    "application-x-executable": (g_exec, "apps"),
    # Centro di Controllo (main.py) e viste (views.py): icone fullcolor a
    # dimensione DIALOG/BUTTON che Adwaita recente non copre piu' -> generiamo
    # noi il glifo tinto col profilo, cosi' nessuna voce resta senza icona.
    "preferences-desktop-theme":     (g_theme, "apps"),
    "preferences-desktop-wallpaper": (g_wallpaper, "apps"),
    "preferences-system-windows":    (g_window, "apps"),
    "input-mouse":                   (g_mouse, "apps"),
    "preferences-desktop-display":   (g_monitor, "apps"),
    "computer":                      (g_monitor, "apps"),
    "utilities-system-monitor":      (g_monitor_graph, "apps"),
    "system-software-install":       (g_package, "apps"),
    "input-keyboard":                (g_keyboard, "apps"),
    "preferences-desktop-keyboard":  (g_keyboard, "apps"),
    "preferences-desktop-keyboard-shortcuts": (g_keyboard, "apps"),
    "network-wired":                 (g_network, "apps"),
    "network-transmit-receive":      (g_network, "apps"),
    "security-high":                 (g_security, "apps"),
    "system-users":                  (g_users, "apps"),
    "bluetooth":                     (g_bluetooth, "apps"),
    "network-firewall":              (g_firewall, "apps"),
    "system-run":                    (g_run, "apps"),
    "media-playback-start":          (g_run, "apps"),
    "preferences-desktop-screensaver": (g_screensaver, "apps"),
    "preferences-desktop-locale":    (g_browser, "apps"),
    "emblem-ok":                     (g_check, "apps"),
    "view-refresh":                  (g_refresh, "apps"),
    "window-close":                  (g_close, "apps"),
    "folder":               (lambda d, a: g_folder(d, a, opened=False), "places"),
    "folder-open":          (lambda d, a: g_folder(d, a, opened=True), "places"),
    "user-home":            (g_home, "places"),
    "user-desktop":         (g_home, "places"),
    "inode-directory":      (lambda d, a: g_folder(d, a, opened=False), "places"),
    "folder-documents":     (lambda d, a: g_folder(d, a, opened=False), "places"),
    "folder-download":      (lambda d, a: g_folder(d, a, opened=False), "places"),
    "folder-desktop":       (g_home, "places"),
    "text-x-generic":       (g_doc, "mimetypes"),
    "application-x-generic": (g_doc, "mimetypes"),
}

CONTEXTS = {"apps": "Applications", "places": "Places",
            "mimetypes": "MimeTypes"}


def render(name, fn, accent_hex) -> Image.Image:
    img = Image.new("RGBA", (R, R), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fn(d, hex2rgba(accent_hex))
    return img


def write_theme(key, theme_name, accent_hex):
    base = ICONS_DIR / theme_name
    # index.theme
    dirs = []
    for ctx in ("apps", "places", "mimetypes"):
        for s in SIZES:
            dirs.append(f"{ctx}/{s}")
    idx = [f"[Icon Theme]", f"Name={theme_name}",
           f"Comment=NexusSec icone profilo {key} (accent {accent_hex})",
           "Inherits=NexusSec-Core,nuoveXT2,Adwaita,gnome,hicolor",
           "Directories=" + ",".join(dirs), ""]
    for ctx in ("apps", "places", "mimetypes"):
        for s in SIZES:
            idx += [f"[{ctx}/{s}]", f"Size={s}",
                    f"Context={CONTEXTS[ctx]}", "Type=Fixed", ""]
    base.mkdir(parents=True, exist_ok=True)
    (base / "index.theme").write_text("\n".join(idx))

    # icone
    for name, (fn, ctx) in ICONS.items():
        master = render(name, fn, accent_hex)
        for s in SIZES:
            outdir = base / ctx / str(s)
            outdir.mkdir(parents=True, exist_ok=True)
            master.resize((s, s), Image.LANCZOS).save(outdir / f"{name}.png")
    return base


def main():
    for key, (theme_name, accent) in PROFILES.items():
        b = write_theme(key, theme_name, accent)
        print(f"[icons] {key:9} -> {b.relative_to(ROOT)}  (accent {accent})")
    print("Fatto. Temi icone per profilo generati.")


if __name__ == "__main__":
    main()
