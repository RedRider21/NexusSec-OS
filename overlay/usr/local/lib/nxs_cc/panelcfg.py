"""Configurazione condivisa del pannello NexusSec (posizione e margini Openbox).

Usato sia da `panel.py` (legge la posizione all'avvio) sia dal Centro di
Controllo (la cambia). La posizione e' persistita in ~/.config/nxs/panel.conf
e riflessa nei <margins> di rc.xml cosi' le finestre massimizzate non
coprono il pannello, sia in basso che in alto.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
CONF = HOME / ".config/nxs/panel.conf"
RC_XML = HOME / ".config/openbox/rc.xml"
PANEL_HEIGHT = 34


def get_position() -> str:
    """Ritorna 'bottom' (default) o 'top'."""
    try:
        for line in CONF.read_text().splitlines():
            line = line.strip()
            if line.startswith("position"):
                val = line.split("=", 1)[1].strip().lower()
                if val in ("top", "bottom"):
                    return val
    except OSError:
        pass
    return "bottom"


def set_position(pos: str) -> None:
    if pos not in ("top", "bottom"):
        return
    CONF.parent.mkdir(parents=True, exist_ok=True)
    CONF.write_text("# Configurazione pannello NexusSec\nposition = %s\n" % pos)


def apply_openbox_margin(pos: str) -> None:
    """Riserva PANEL_HEIGHT sul lato giusto nei <margins> di rc.xml."""
    try:
        txt = RC_XML.read_text()
    except OSError:
        return
    top = PANEL_HEIGHT if pos == "top" else 0
    bottom = PANEL_HEIGHT if pos == "bottom" else 0
    txt = re.sub(r"<top>\d+</top>", "<top>%d</top>" % top, txt, count=1)
    txt = re.sub(r"<bottom>\d+</bottom>", "<bottom>%d</bottom>" % bottom, txt, count=1)
    RC_XML.write_text(txt)


def openbox_reconfigure() -> None:
    try:
        subprocess.Popen(["openbox", "--reconfigure"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        pass


def restart_panel() -> None:
    # Riavvio ROBUSTO anche quando la chiamata parte DAL pannello stesso (voce
    # "Sposta pannello" del menu). Il vecchio approccio faceva
    # `subprocess.run(pkill -f nxs_cc.panel)` DENTRO il pannello: il segnale
    # uccideva il pannello corrente PRIMA di arrivare alla Popen del nuovo, e la
    # barra spariva senza tornare (con nxs-profile funzionava solo perche' il
    # restart partiva da un altro processo).
    #
    # Fix: delego kill+riavvio a un processo DETACHED (start_new_session) che
    # uccide il vecchio pannello PER PID (non per pattern). Cosi':
    #  - il suo argv contiene solo un numero e "nxs-panel": niente "nxs_cc.panel"
    #    -> il killer non si auto-uccide (gotcha noto);
    #  - il pannello corrente resta vivo finche' il nuovo non e' pronto a partire.
    old_pid = os.getpid()
    subprocess.Popen(
        ["sh", "-c",
         "sleep 0.3; kill %d 2>/dev/null; sleep 0.3; exec nxs-panel" % old_pid],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True)


def move_panel(pos: str) -> None:
    """Cambia posizione: persiste, aggiorna i margini, ricarica, riavvia."""
    set_position(pos)
    apply_openbox_margin(pos)
    openbox_reconfigure()
    restart_panel()
