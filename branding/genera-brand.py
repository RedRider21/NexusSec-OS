#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""Genera il set grafico di NexusSec (SVG sorgente + PNG via Chrome headless).

Emblema = esagono "circuito" della splash della distro: nodi agli angoli,
esagono interno sottile, N fatta di tracce e nodi, ciano #00e5ff con bagliore
su fondo #050a14. Font: Chakra Petch (titoli) e IBM Plex Mono, dalla distro.

  python3 branding/genera-brand.py      -> branding/svg/*.svg + branding/png/*.png
"""
import json
import math
import os
import random
import shutil
import subprocess
import tempfile
import time
import urllib.request

QUI = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(QUI, "..", "overlay", "usr", "share", "fonts", "nexussec")
CIANO, CIANO_CHIARO, FONDO, TESTO, TENUE = "#00e5ff", "#a8f8ff", "#050a14", "#c8f5ff", "#5a8a9a"


def esagono(cx, cy, r):
    return [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
            for a in (-90, -30, 30, 90, 150, 210)]


def emblema(cx, cy, s, id_="e"):
    """Emblema centrato in (cx,cy), lato di riferimento s (raggio esterno)."""
    est = esagono(cx, cy, s)
    inn = esagono(cx, cy, s * 0.71)
    pts = lambda P: " ".join("%.1f,%.1f" % p for p in P)
    w = s * 0.068
    nx, ny, nh = s * 0.28, s * 0.37, s * 0.37
    L, Rr, T, B = cx - nx, cx + nx, cy - nh, cy + nh
    nodi = "".join('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s"/>' % (x, y, s * 0.068, CIANO) for x, y in est)
    nodiN = "".join('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s"/>'
                    '<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s"/>'
                    % (x, y, s * 0.085, CIANO_CHIARO, x, y, s * 0.04, "#ffffff")
                    for x, y in ((L, B), (L, T), (Rr, B), (Rr, T)))
    return f'''
  <g filter="url(#glow-{id_})">
    <polygon points="{pts(est)}" fill="none" stroke="{CIANO}" stroke-width="{w:.1f}" stroke-linejoin="round"/>
    {nodi}
    <polygon points="{pts(inn)}" fill="none" stroke="{CIANO}" stroke-opacity=".38" stroke-width="{w*0.32:.1f}"/>
    <polyline points="{L:.1f},{B:.1f} {L:.1f},{T:.1f} {Rr:.1f},{B:.1f} {Rr:.1f},{T:.1f}" fill="none"
              stroke="{CIANO_CHIARO}" stroke-width="{w*1.15:.1f}" stroke-linecap="round" stroke-linejoin="round"/>
    {nodiN}
  </g>'''


def defs(id_, s):
    return f'''
  <filter id="glow-{id_}" x="-40%" y="-40%" width="180%" height="180%">
    <feGaussianBlur in="SourceGraphic" stdDeviation="{s*0.035:.1f}" result="b1"/>
    <feGaussianBlur in="SourceGraphic" stdDeviation="{s*0.012:.1f}" result="b2"/>
    <feMerge><feMergeNode in="b1"/><feMergeNode in="b2"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>'''


def font_face():
    return ('<style>@font-face{font-family:"Chakra";src:url("file://%s/ChakraPetch-Bold.ttf")}'
            '@font-face{font-family:"ChakraM";src:url("file://%s/ChakraPetch-Medium.ttf")}'
            '@font-face{font-family:"Plex";src:url("file://%s/IBMPlexMono-Regular.ttf")}</style>'
            % ((os.path.abspath(FONT),) * 3))


def sfondo(w, h, rete=True, seme=7, zona=None):
    """Fondo scuro con alone e (opz.) costellazione di nodi tenue, come lo
    screensaver della distro."""
    out = [f'<rect width="{w}" height="{h}" fill="{FONDO}"/>',
           f'<rect width="{w}" height="{h}" fill="url(#alone)"/>']
    if rete:
        rnd = random.Random(seme)
        P = [(rnd.uniform(0, w), rnd.uniform(0, h)) for _ in range(int(w * h / 9000))]
        if zona:  # niente rete dove sta il contenuto
            P = [p for p in P if not (zona[0] < p[0] < zona[2] and zona[1] < p[1] < zona[3])]
        lin = []
        for i, (x1, y1) in enumerate(P):
            for x2, y2 in P[i + 1:]:
                d = math.hypot(x1 - x2, y1 - y2)
                if d < min(w, h) * 0.17:
                    lin.append(f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" '
                               f'stroke="{CIANO}" stroke-opacity="{0.16*(1-d/(min(w,h)*0.17)):.3f}" stroke-width="1.4"/>')
        out += lin
        out += [f'<circle cx="{x:.0f}" cy="{y:.0f}" r="2.6" fill="{CIANO}" fill-opacity=".35"/>' for x, y in P]
    return "\n".join(out)


def svg(w, h, corpo, s, trasparente=False, alone_c=(0.5, 0.5), id_="e"):
    alone = (f'<radialGradient id="alone" cx="{alone_c[0]}" cy="{alone_c[1]}" r="0.6">'
             f'<stop offset="0" stop-color="#0d3448" stop-opacity=".95"/>'
             f'<stop offset="1" stop-color="{FONDO}" stop-opacity="0"/></radialGradient>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'{font_face()}<defs>{alone}{defs(id_, s)}</defs>{corpo}</svg>')


def wordmark(x, y, size, ancora="start"):
    return (f'<text x="{x}" y="{y}" font-family="Chakra" font-size="{size}" fill="{TESTO}" '
            f'text-anchor="{ancora}" letter-spacing="{size*0.04:.1f}">NexusSec'
            f'<tspan fill="{CIANO}" font-family="ChakraM"> OS</tspan></text>')


def disegni():
    D = {}
    # 1) profilo Facebook: solo emblema, sicuro nel ritaglio circolare
    D["fb-profilo"] = (1080, 1080, False, svg(1080, 1080,
        sfondo(1080, 1080, rete=True, seme=3, zona=(170, 170, 910, 910)) + emblema(540, 540, 330), 330))
    # 2) profilo con scritta (dentro al cerchio)
    D["fb-profilo-testo"] = (1080, 1080, False, svg(1080, 1080,
        sfondo(1080, 1080, rete=True, seme=5, zona=(170, 120, 910, 960)) + emblema(540, 470, 270)
        + wordmark(540, 860, 92, "middle"), 270, alone_c=(0.5, 0.44)))
    # 3) copertina Facebook 1640x624: contenuto nel centro (il telefono taglia i lati)
    # composizione CENTRATA (emblema 350 + spazio + testo ~830 = ~1240 px):
    # margini ~200 px per lato, cosi' il telefono (che taglia i lati) la mostra intera
    corpo = (sfondo(1640, 624, rete=True, seme=11, zona=(180, 60, 1460, 570))
             + emblema(375, 312, 170)
             + wordmark(600, 292, 112)
             + f'<text x="604" y="348" font-family="ChakraM" font-size="30" fill="{TESTO}">'
               'Distro live per la cybersecurity · basata su Alpine Linux</text>'
             + f'<text x="606" y="402" font-family="Plex" font-size="21" fill="{TENUE}">'
               'profili dinamici · HORUS OSINT · sandbox · persistenza cifrata</text>'
             + f'<line x1="604" y1="368" x2="1180" y2="368" stroke="{CIANO}" stroke-opacity=".5" stroke-width="2"/>')
    D["fb-copertina"] = (1640, 624, False, svg(1640, 624, corpo, 170, alone_c=(0.32, 0.5)))
    # 4) emblema trasparente
    D["emblema-trasparente"] = (1024, 1024, True,
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">'
        f'<defs>{defs("e", 360)}</defs>{emblema(512, 512, 360)}</svg>')
    # 5) logo orizzontale trasparente (emblema + scritta)
    D["logo-orizzontale-trasparente"] = (2000, 560, True,
        f'<svg xmlns="http://www.w3.org/2000/svg" width="2000" height="560" viewBox="0 0 2000 560">'
        f'{font_face()}<defs>{defs("e", 220)}</defs>{emblema(290, 280, 220)}{wordmark(590, 340, 190)}</svg>')
    # 6) logo orizzontale su fondo scuro
    D["logo-orizzontale-scuro"] = (2000, 560, False, svg(2000, 560,
        sfondo(2000, 560, rete=False) + emblema(290, 280, 220) + wordmark(590, 340, 190), 220, alone_c=(0.15, 0.5)))
    return D


def chrome_png(svgfile, png, w, h, trasparente):
    prof = tempfile.mkdtemp(prefix="nxs-brand-")
    html = os.path.join(prof, "p.html")
    with open(html, "w") as f:
        f.write('<html><body style="margin:0;background:transparent">%s</body></html>'
                % open(svgfile).read())
    args = ["google-chrome", "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--user-data-dir=" + prof, "--force-device-scale-factor=1",
            "--window-size=%d,%d" % (w, h), "--virtual-time-budget=3000",
            "--screenshot=" + png, "file://" + html]
    if trasparente:
        args.insert(1, "--default-background-color=00000000")
    subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    shutil.rmtree(prof, ignore_errors=True)


def main():
    os.makedirs(os.path.join(QUI, "svg"), exist_ok=True)
    os.makedirs(os.path.join(QUI, "png"), exist_ok=True)
    for nome, (w, h, trasp, s) in disegni().items():
        sv = os.path.join(QUI, "svg", nome + ".svg")
        open(sv, "w").write(s)
        chrome_png(sv, os.path.join(QUI, "png", nome + ".png"), w, h, trasp)
        print("ok", nome, "%dx%d" % (w, h))


if __name__ == "__main__":
    main()
