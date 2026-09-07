"""Skin colore del pannello NexusSec (barra + menu + popup).

INDIPENDENTI dai profili: una skin definisce una palette FISSA per la barra e i
suoi menu; la skin speciale "profile" NON impone colori e lascia decidere
all'accent del profilo attivo (comportamento predefinito storico).

Le skin sono file CSS:
  /usr/local/share/nexussec/panel-themes/*.css   (di serie, generate da
                                                   build/make-panel-themes.py)
  ~/.config/nxs/panel-themes/*.css               (aggiunte dall'utente: basta
                                                   lasciarci un .css e compare)
La scelta e' in ~/.config/nxs/panel-theme (una riga: l'id della skin).

Modulo SENZA dipendenze GTK: importabile da CLI e dal pannello. Il caricamento
del CSS a runtime lo fa nxs_cc.common (apply_panel_theme_live).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
CONF = HOME / ".config" / "nxs" / "panel-theme"
SYS_DIR = Path("/usr/local/share/nexussec/panel-themes")
USER_DIR = HOME / ".config" / "nxs" / "panel-themes"
DEFAULT = "profile"


def _meta_name(path: Path) -> str:
    """Nome leggibile da un commento '/* name: ... */' in testa al file."""
    try:
        for line in path.read_text().splitlines()[:6]:
            m = re.search(r"name:\s*(.+?)\s*(?:\*/|$)", line)
            if m:
                return m.group(1).strip()
    except OSError:
        pass
    return path.stem


def list_themes():
    """Ritorna [(id, nome, sorgente)]; 'profile' e' sempre la prima voce.
    Un file utente con lo STESSO id di una skin di sistema la sostituisce."""
    out = [("profile", "Segui il profilo (predefinito)", "builtin")]
    seen = {"profile"}
    # utente prima cosi' un id ripetuto mostra la variante utente
    for d, src in ((USER_DIR, "utente"), (SYS_DIR, "sistema")):
        try:
            files = sorted(d.glob("*.css"))
        except OSError:
            files = []
        for f in files:
            tid = f.stem
            if tid in seen:
                continue
            seen.add(tid)
            out.append((tid, _meta_name(f), src))
    return out


def css_path(tid: str):
    """Percorso del CSS per l'id (utente prevale), o None per 'profile'/assente."""
    if not tid or tid == "profile":
        return None
    for d in (USER_DIR, SYS_DIR):
        p = d / (tid + ".css")
        if p.exists():
            return p
    return None


def get_theme() -> str:
    try:
        v = CONF.read_text().strip().splitlines()[0].strip()
        return v or DEFAULT
    except (OSError, IndexError):
        return DEFAULT


def set_theme(tid: str) -> None:
    CONF.parent.mkdir(parents=True, exist_ok=True)
    CONF.write_text((tid or DEFAULT) + "\n")


def valid_ids():
    return [t[0] for t in list_themes()]
