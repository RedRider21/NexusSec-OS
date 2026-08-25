"""Dati e stato dei profili NexusSec (base Alpine Linux).

Attivare un profilo = installare il suo META-PACCHETTO apk
(`apk add --no-cache sec-profile-<chiave>`), che tira con se' tutti i tool.
Il codice Python e' quindi un semplice "direttore d'orchestra": apk fa il
lavoro pesante (download, dipendenze, integrazione nel sistema).

- catalogo profili/tool: /usr/local/share/nexussec/{profiles,repo}.json
- profilo attivo: /etc/sec_os/state.json  ({"active_profile": "<chiave>"})
  (fallback scrivibile: ~/.config/nxs/profile, utile in live read-only/dev)
- sfondi: ~/.themes/NexusSec-Core/backgrounds/<wallpaper>

Nessuna dipendenza GTK: importabile da CLI (nxs-tool) e dal pannello.
Percorsi ridefinibili via env (NXS_PREFIX, NXS_STATE, NXS_CONF_DIR,
NXS_BG_DIR) per test/sviluppo su host.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

PREFIX = Path(os.environ.get("NXS_PREFIX", "/usr/local/share/nexussec"))
PROFILES_JSON = PREFIX / "profiles.json"
REPO_JSON = PREFIX / "repo.json"
# Catalogo dell'INTERO arsenale Kali (categoria/profilo/bin per ~360 tool): serve
# a categorizzare nel menu i tool installati on-demand che NON sono in repo.json.
KALI_CATALOG_JSON = PREFIX / "kali_catalog.json"

HOME = Path(os.path.expanduser("~"))
CONF_DIR = Path(os.environ.get("NXS_CONF_DIR", str(HOME / ".config" / "nxs")))
USER_PROFILE_FILE = CONF_DIR / "profile"     # fallback se /etc/sec_os non scrivibile
STATE_FILE = Path(os.environ.get("NXS_STATE", "/etc/sec_os/state.json"))
ACCENT_CSS = CONF_DIR / "accent.css"
# Tema Openbox (decorazioni/bordi finestre): i colori "accent" del themerc vanno
# tinti col profilo, altrimenti le finestre restano sempre col base (cyan).
OB_THEMERC = HOME / ".themes" / "NexusSec-Core" / "openbox-3" / "themerc"
_OB_ACCENT_KEYS = (
    "window.active.grip.bg.color",
    "window.active.border.color",
    "window.active.label.text.color",
    "window.active.button.unpressed.image.color",
    "window.active.button.pressed.image.color",
    "menu.title.text.color",
    "menu.items.active.text.color",
    "osd.label.text.color",
)

BG_DIR = Path(os.environ.get(
    "NXS_BG_DIR", str(HOME / ".themes" / "NexusSec-Core" / "backgrounds")))
# themerc di Openbox: la DECORAZIONE delle finestre (cornice, barra titolo,
# pulsanti). La rigeneriamo con l'accent del profilo e lo stile finestre scelto
# cosi' anche il bordo/titlebar seguono vetro/telaio/flat (non piu' fisso ciano).
OB_THEMERC = Path(os.environ.get("NXS_OB_THEMERC",
    str(HOME / ".themes" / "NexusSec-Core" / "openbox-3" / "themerc")))


_JSON_CACHE: dict = {}   # path -> (mtime, dati): evita di ri-parsare i cataloghi
                         # (repo.json ~200 + kali_catalog ~360) ad ogni tool_data
                         # durante la costruzione del menu (centinaia di voci).


def _load_json(path: Path) -> dict:
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {}
    cached = _JSON_CACHE.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    _JSON_CACHE[path] = (mtime, data)
    return data


# ---------------------------------------------------------------- catalogo
def profiles() -> dict:
    return _load_json(PROFILES_JSON).get("profiles", {})


def default_profile() -> str:
    return _load_json(PROFILES_JSON).get("default", "base")


def repo() -> dict:
    return _load_json(REPO_JSON).get("tools", {})


def kali_catalog() -> dict:
    """Catalogo dell'intero arsenale Kali (pkg -> {category, profile, bin, ...}).
    Usato per categorizzare i tool installati on-demand non presenti in repo.json."""
    return _load_json(KALI_CATALOG_JSON)


def kali_installed() -> list[str]:
    """Pacchetti Kali gia installati nell'ambiente condiviso (file di stato di
    isolation._kali_mark). Letto come semplice file per evitare cicli di import."""
    try:
        return [ln.strip() for ln in (CONF_DIR / "kali_installed.txt")
                .read_text().splitlines() if ln.strip()]
    except OSError:
        return []


def tool_data(name: str) -> dict:
    """Dati del tool: prima repo.json, poi (fallback) il catalogo Kali completo,
    cosi anche un tool installato ma non elencato ha categoria/bin/descrizione."""
    return repo().get(name) or kali_catalog().get(name, {})


def profile_data(key: str | None = None) -> dict:
    if key is None:
        key = current_profile()
    return profiles().get(key, {})


def profile_tools(key: str | None = None) -> list[str]:
    """Tool del profilo = elenco statico (profiles.json) PIU i tool Kali
    installati on-demand che appartengono a questo profilo ma non erano elencati.
    Cosi qualunque programma aggiuntivo installato compare da solo nel menu, nella
    sezione (categoria) giusta ricavata dal catalogo Kali."""
    key = key or current_profile()
    tools = list(profile_data(key).get("tools", []))
    have = set(tools)
    known_apt = {t.get("apt") for t in repo().values() if t.get("method") == "kali"}
    cat = kali_catalog()
    for pkg in kali_installed():
        if pkg in have or pkg in known_apt:
            continue                       # gia rappresentato in repo.json
        info = cat.get(pkg)
        if info and info.get("profile") == key:
            tools.append(pkg)
            have.add(pkg)
    return tools


def accent(key: str | None = None) -> str:
    return profile_data(key).get("accent", "#00e5ff")


# ---------------------------------------------------------------- stato
def current_profile() -> str:
    """Chiave del profilo attivo, da state.json (o fallback utente)."""
    for src in (STATE_FILE, USER_PROFILE_FILE):
        try:
            txt = src.read_text().strip()
        except OSError:
            continue
        key = json.loads(txt).get("active_profile", "") if txt.startswith("{") else txt
        if key and key in profiles():
            return key
    return default_profile()


def set_current(key: str) -> None:
    """Salva il profilo attivo. Prova /etc/sec_os, poi la home dell'utente."""
    payload = json.dumps({"active_profile": key}) + "\n"
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(payload)
        return
    except OSError:
        pass
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    USER_PROFILE_FILE.write_text(payload)


# ---------------------------------------------------------------- aspetto
def wallpaper_path(key: str | None = None) -> Path:
    return BG_DIR / profile_data(key).get("wallpaper", "nebula.png")


def set_wallpaper(path: Path) -> bool:
    if not path.exists():
        return False
    # Preferisci pcmanfm: gestisce desktop (icone) E sfondo insieme, cosi' lo
    # sfondo NON viene coperto dal desktop di pcmanfm (con feh succedeva).
    # Richiede 'pcmanfm --desktop' gia' in esecuzione (vedi autostart).
    if shutil.which("pcmanfm"):
        try:
            subprocess.run(
                ["pcmanfm", "--set-wallpaper", str(path),
                 "--wallpaper-mode=stretch"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:                 # noqa: BLE001
            pass
    # Fallback: feh (se pcmanfm assente, es. in dev/host).
    try:
        subprocess.Popen(["feh", "--bg-scale", str(path)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except FileNotFoundError:
        return False


def write_accent_css(key: str | None = None) -> None:
    """Genera ~/.config/nxs/accent.css con gli accenti del profilo (override
    mirati, caricati da nxs_cc.common.apply_css)."""
    ac = accent(key)
    try:
        h = ac.lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, IndexError):
        r, g, b = 0, 229, 255
    rgb = f"{r},{g},{b}"
    css = f"""/* accent del profilo NexusSec - generato da nxs_profiles
   Restyle 'badge' 2026-08-25: colorazione raffinata per profilo su barra,
   menu e finestre (accent usato con parsimonia: filetti, tag, aloni morbidi).
   Caricato con priorita' sopra il tema base (vedi nxs_cc.common.apply_css). */

/* --- BARRA: filetto accento + stati con alone morbido --- */
.nxs-panel {{ border-top: 2px solid {ac}; }}
.nxs-panel.nxs-panel-top {{ border-top: none; border-bottom: 2px solid {ac}; }}
.nxs-panel button.nxs-menu, .nxs-panel button.nxs-menu image {{ color: {ac}; }}
.nxs-panel button image {{ color: {ac}; }}
.nxs-panel button:hover {{ background-color: rgba({rgb},0.14); border-color: transparent; }}
.nxs-panel button.nxs-icon:hover image {{ color: {ac}; }}
.nxs-panel button.nxs-task-active {{
  color: {ac}; background-color: rgba({rgb},0.14);
  border-color: transparent; box-shadow: inset 0 -2px {ac}; }}
.nxs-panel button.nxs-pager-active {{
  color: #050a14; background-color: {ac}; border-color: {ac}; }}

/* --- MENU: striscia, categorie a tag, hover e selezione --- */
.nxs-menu-strip {{ background-image: linear-gradient(to top, #03070f, {ac} 60%, {ac}); }}
label.nxs-menu-cat {{ color: {ac}; }}
button.nxs-menu-cat {{ border-left-color: {ac}; }}
button.nxs-menu-cat:hover {{ border-left-color: {ac}; color: {ac};
  background-image: linear-gradient(to right, rgba({rgb},0.16), rgba({rgb},0)); }}
button.nxs-menu-item image {{ color: {ac}; }}
button.nxs-menu-item:hover {{ background-color: rgba({rgb},0.14); border-color: transparent; }}
button.nxs-menu-item:hover label {{ color: {ac}; }}
button.nxs-tool-item:hover {{ border-left-color: {ac}; background-color: rgba({rgb},0.12); }}

/* --- FINESTRE (Centro di Controllo, viste, dialoghi): raffinato --- */
.nxs-section {{ color: {ac}; border-bottom-color: {ac}; }}
.nxs-headerbar {{ border-bottom-color: {ac}; box-shadow: inset 0 -2px {ac}; }}
.nxs-headerbar label.title {{ color: {ac}; }}
.nxs-eyebrow {{ color: {ac}; }}
.nxs-key, .nxs-card-title {{ color: {ac}; }}
.nxs-tile-badge {{ background-color: rgba({rgb},0.16); }}
.nxs-tile-badge image {{ color: {ac}; }}
.nxs-tile:hover, .nxs-card:hover {{ border-color: {ac}; box-shadow: inset 0 2px {ac}; }}
button.nxs-primary {{ color: {ac}; border-color: {ac}; background-color: rgba({rgb},0.12); }}
button.nxs-primary:hover {{ background-color: rgba({rgb},0.22); box-shadow: 0 6px 22px rgba({rgb},0.28); }}
button:hover {{ border-color: {ac}; background-color: rgba({rgb},0.12); }}
button:hover image {{ color: {ac}; }}
entry:focus {{ border-color: {ac}; box-shadow: 0 0 0 3px rgba({rgb},0.18); }}
switch:checked {{ background-color: rgba({rgb},0.30); border-color: {ac}; }}
switch:checked slider {{ background-color: {ac}; }}
notebook tab:checked {{ color: {ac}; box-shadow: inset 0 -2px {ac}; }}
progressbar > trough > progress {{ background-color: {ac}; }}
treeview:selected {{ background-color: rgba({rgb},0.20); color: {ac}; }}
list row:selected {{ background-color: rgba({rgb},0.20); box-shadow: inset 3px 0 {ac}; }}
list row:selected label {{ color: {ac}; }}
scale highlight {{ background-color: {ac}; }}
scale slider {{ background-color: {ac}; border-color: {ac}; }}
"""
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    ACCENT_CSS.write_text(css)
    # rigenera anche lo stile finestre (usa lo stesso accent del profilo)
    write_window_style_css(key=key)
    # e la decorazione Openbox (cornice/titlebar/pulsanti) intonata al profilo
    write_openbox_theme(key=key)


# ---- Stile finestre (flat / vetro / telaio) commutabile -------------------
WINDOW_STYLE_CONF = CONF_DIR / "window-style"
WINDOW_STYLE_CSS = CONF_DIR / "window-style.css"
WINDOW_STYLES = ("flat", "vetro", "telaio")
DEFAULT_WINDOW_STYLE = "vetro"


def get_window_style() -> str:
    """Ritorna lo stile finestre scelto (default 'vetro')."""
    try:
        s = WINDOW_STYLE_CONF.read_text().strip().lower()
        if s in WINDOW_STYLES:
            return s
    except OSError:
        pass
    return DEFAULT_WINDOW_STYLE


def set_window_style(style: str, key: str | None = None) -> None:
    """Persiste lo stile e rigenera il CSS relativo con l'accent corrente."""
    if style not in WINDOW_STYLES:
        style = DEFAULT_WINDOW_STYLE
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    WINDOW_STYLE_CONF.write_text(style + "\n")
    write_window_style_css(style=style, key=key)
    write_openbox_theme(style=style, key=key)


def write_window_style_css(style: str | None = None, key: str | None = None) -> None:
    """Genera ~/.config/nxs/window-style.css per lo stile scelto, tinto con
    l'accent del profilo. Caricato SOPRA accent.css (vedi nxs_cc.common)."""
    if style is None:
        style = get_window_style()
    ac = accent(key)
    try:
        h = ac.lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, IndexError):
        r, g, b = 0, 229, 255
    rgb = f"{r},{g},{b}"
    head = ("/* stile finestre NexusSec: %s - generato da nxs_profiles.\n"
            "   Caricato sopra accent.css (nxs_cc.common.apply_css). */\n" % style)
    if style == "flat":
        css = head + "/* Flat arrotondato: nessun override, usa il tema base + accent. */\n"
    elif style == "telaio":
        # Fedele al mockup "Telaio a contorno": fondo quasi nero (#05090f),
        # header con barretta laterale d'accento, tessere #070d14 col bordo
        # d'accento e un filetto verticale sinistro. Primario pieno.
        css = head + f"""
/* TELAIO A CONTORNO (neon outline): fondo quasi NERO, elementi definiti da un
   bordo d'accento e da una barretta laterale. Estetica terminale/cyber. */
window, .background, dialog {{ background-color: #05090f; }}
.nxs-headerbar {{
  background-color: #070d14;
  border-top: none;
  border-left: 3px solid {ac};
  border-bottom: 1px solid rgba({rgb},0.24);
  box-shadow: none;
}}
.nxs-tile, .nxs-card, .nxs-profilo-card {{
  background-color: #070d14;
  border: 1px solid rgba({rgb},0.20);
  border-left: 3px solid rgba({rgb},0.55);
  border-radius: 6px;
}}
.nxs-tile:hover, .nxs-card:hover, .nxs-profilo-card:hover {{
  background-color: rgba({rgb},0.10);
  border-color: {ac}; border-left-color: {ac}; box-shadow: none; }}
.nxs-profilo-card.sel {{ border-color: {ac}; border-left-color: {ac};
  background-color: rgba({rgb},0.12); }}
.nxs-section {{ border-bottom: 1px solid rgba({rgb},0.24); }}
button {{ border-radius: 5px; background-color: #080f18; border: 1px solid rgba({rgb},0.30); }}
button:hover {{ border-color: {ac}; background-color: rgba({rgb},0.10); }}
button.nxs-primary {{ background-color: {ac}; color: #04121a; border-color: {ac};
  box-shadow: none; }}
entry {{ border-radius: 5px; background-color: #05090f; border: 1px solid rgba({rgb},0.24); }}
frame > border {{ border-color: rgba({rgb},0.24); border-radius: 6px; }}
notebook tab {{ border-radius: 5px 5px 0 0; }}
progressbar > trough {{ background-color: #071019; border-radius: 999px; }}
progressbar > trough > progress {{ border-radius: 999px; background-color: {ac}; }}
switch {{ background-color: #05090f; border-color: rgba({rgb},0.30); }}
"""
    else:  # vetro (default)
        # FEDELE AL MOCKUP "Vetro / HUD". Il tratto distintivo NON e' un fondo
        # piu' chiaro (il mockup resta su #0a1220, vicino al base) ma:
        #  1) la TRAMA A RIGHE verticali nell'header (repeating-linear-gradient);
        #  2) il filetto superiore d'accento 2px + velatura sull'header;
        #  3) le tessere con velatura d'accento e bordo ciano;
        #  4) il primario pieno con glow.
        # NB GTK3: gradienti con sintassi vecchia (to bottom/to right, niente
        # angoli), e repeating-linear-gradient con DUE stop espliciti per colore.
        css = head + f"""
/* VETRO / HUD: velatura d'accento, filo superiore colorato e trama a righe
   nell'header. "Console operativa" ma elegante (identico al mockup). */
window, .background, dialog {{
  background-color: #0a1220;
  background-image: linear-gradient(to bottom, rgba({rgb},0.06), rgba(10,18,32,0.0) 55%);
}}
.nxs-headerbar {{
  background-color: #0a1220;
  border-top: 2px solid {ac};
  border-bottom: 1px solid #122536;
  background-image:
    repeating-linear-gradient(to right,
      rgba({rgb},0.07) 0px, rgba({rgb},0.07) 1px,
      rgba(10,18,32,0.0) 1px, rgba(10,18,32,0.0) 7px),
    linear-gradient(to bottom, rgba({rgb},0.10), rgba(10,18,32,0.0));
}}
.nxs-tile, .nxs-card, .nxs-profilo-card {{
  background-color: rgba({rgb},0.05);
  border: 1px solid rgba({rgb},0.16);
  border-radius: 10px;
}}
.nxs-tile:hover, .nxs-card:hover, .nxs-profilo-card:hover {{
  background-color: rgba({rgb},0.12); border-color: {ac};
  box-shadow: inset 0 0 0 1px rgba({rgb},0.30); }}
.nxs-profilo-card.sel {{ border-color: {ac}; background-color: rgba({rgb},0.16);
  box-shadow: inset 0 0 0 1px rgba({rgb},0.40); }}
button {{ background-color: rgba({rgb},0.05); border: 1px solid #173042; border-radius: 9px; }}
button:hover {{ border-color: {ac}; background-color: rgba({rgb},0.12); }}
button.nxs-primary {{ background-color: {ac}; color: #04121a; border-color: {ac};
  box-shadow: 0 0 18px rgba({rgb},0.55); }}
button.nxs-primary:hover {{ background-color: {ac}; box-shadow: 0 0 24px rgba({rgb},0.80); }}
entry {{ background-color: rgba({rgb},0.04); border: 1px solid #173042; }}
frame > border {{ border-color: rgba({rgb},0.16); }}
progressbar > trough {{ background-color: #1a2d3a; border-radius: 999px; }}
progressbar > trough > progress {{ border-radius: 999px; background-color: {ac}; }}
"""
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    WINDOW_STYLE_CSS.write_text(css)


def _mix(fg: str, bg: str, frac: float) -> str:
    """Miscela fg su bg (frac = quota di fg, 0..1) -> #rrggbb."""
    def _rgb(h):
        h = h.lstrip("#")
        return [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    try:
        f, b = _rgb(fg), _rgb(bg)
    except (ValueError, IndexError):
        return bg
    return "#%02x%02x%02x" % tuple(
        max(0, min(255, round(frac * f[i] + (1 - frac) * b[i]))) for i in range(3))


def write_openbox_theme(style: str | None = None, key: str | None = None) -> None:
    """Rigenera il themerc di Openbox (DECORAZIONE finestre: cornice, barra
    titolo, pulsanti) intonandolo all'accent del profilo e allo stile scelto.
    Vetro: titlebar con gradiente velato + bordo d'accento sottile. Telaio:
    titlebar piatta scurissima + bordo d'accento fine. Flat: sobrio classico."""
    if style is None:
        style = get_window_style()
    ac = accent(key)
    g2 = "#0a1220"          # fondo finestra "vetro" del mockup
    title_top = _mix(ac, g2, 0.28)     # velatura d'accento in cima alla barra
    title_bot = g2
    dim = _mix(ac, "#050a14", 0.45)    # accent tenue (bordo inattivo/telaio)
    if style == "telaio":
        border_w = 1
        act_border = ac
        title_bg = ("window.active.title.bg: flat solid\n"
                    "window.active.title.bg.color: #070d14\n")
        handle_c = "#070d14"
    elif style == "flat":
        border_w = 3
        act_border = ac
        title_bg = ("window.active.title.bg: flat solid\n"
                    "window.active.title.bg.color: #0a1a26\n")
        handle_c = "#0a1a26"
    else:                  # vetro (default): NIENTE cornice colorata: il colore
        # sta SOLO in alto (barra del titolo con velatura d'accento), come nel
        # mockup. Il bordo laterale/inferiore e' scuro e discreto (solo per
        # afferrare il resize), non piu' il filo ciano attorno alla finestra.
        border_w = 1
        act_border = "#122536"
        title_bg = ("window.active.title.bg: gradient vertical\n"
                    "window.active.title.bg.color: %s\n"
                    "window.active.title.bg.colorTo: %s\n" % (title_top, title_bot))
        handle_c = title_bot
    txt = f"""# NexusSec-Core - tema finestre Openbox (GENERATO da nxs_profiles).
# Rigenerato con l'accent del profilo e lo stile finestre '{style}'.
# NON modificare a mano: viene sovrascritto al cambio profilo/stile.
padding.width: 4
padding.height: 3
border.width: {border_w}
window.client.padding.width: 0
window.handle.width: 6
window.active.handle.bg: flat solid
window.active.handle.bg.color: {handle_c}
window.inactive.handle.bg: flat solid
window.inactive.handle.bg.color: #050a14
window.active.grip.bg: flat solid
window.active.grip.bg.color: {ac}
window.inactive.grip.bg: flat solid
window.inactive.grip.bg.color: #1a3a52

# Bordi
window.active.border.color: {act_border}
window.inactive.border.color: #1a3a52

# Barra del titolo
{title_bg}window.inactive.title.bg: flat solid
window.inactive.title.bg.color: #050a14

# Testo titolo
window.active.label.text.color: {ac}
window.inactive.label.text.color: #5a8a9a
window.label.text.justify: center

# Pulsanti (minimizza / massimizza / chiudi)
window.active.button.unpressed.image.color: {ac}
window.inactive.button.unpressed.image.color: #5a8a9a
window.active.button.hover.image.color: #c8f5ff
window.active.button.pressed.image.color: #ffffff
window.active.button.disabled.image.color: {dim}

# Menu
menu.title.bg: flat solid
menu.title.bg.color: #0a1a26
menu.title.text.color: {ac}
menu.items.bg: flat solid
menu.items.bg.color: #0a1a26
menu.items.text.color: #c8f5ff
menu.items.active.bg: flat solid
menu.items.active.bg.color: {_darken(ac)}
menu.items.active.text.color: {ac}

# OSD
osd.bg: flat solid
osd.bg.color: #0a1a26
osd.label.text.color: {ac}
"""
    try:
        OB_THEMERC.parent.mkdir(parents=True, exist_ok=True)
        OB_THEMERC.write_text(txt)
    except OSError:
        return
    # applica a caldo se Openbox e' in esecuzione (best-effort)
    try:
        subprocess.Popen(["openbox", "--reconfigure"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (FileNotFoundError, OSError):
        pass


def _darken(hex_color: str, factor: float = 0.32) -> str:
    """Versione scura di un colore #rrggbb (per lo sfondo voce-menu attiva)."""
    try:
        h = hex_color.lstrip("#")
        r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
        return "#%02x%02x%02x" % (int(r*factor), int(g*factor), int(b*factor))
    except (ValueError, IndexError):
        return hex_color


def set_window_theme(key: str | None = None, reconfigure: bool = True) -> None:
    """Tinge le decorazioni finestra Openbox (bordi/titolo attivo/menu) con
    l'accent del profilo, riscrivendo le chiavi 'accent' del themerc e ricaricando
    Openbox. Senza questo i bordi di QUALSIASI finestra restavano sempre base."""
    if not OB_THEMERC.exists():
        return
    ac = accent(key)
    try:
        lines = OB_THEMERC.read_text().splitlines()
    except OSError:
        return
    out = []
    for ln in lines:
        k = ln.split(":", 1)[0].strip() if ":" in ln else ""
        if k in _OB_ACCENT_KEYS:
            out.append(f"{k}: {ac}")
        elif k == "menu.items.active.bg.color":
            out.append(f"{k}: {_darken(ac)}")
        else:
            out.append(ln)
    try:
        OB_THEMERC.write_text("\n".join(out) + "\n")
    except OSError:
        return
    if reconfigure and shutil.which("openbox"):
        subprocess.run(["openbox", "--reconfigure"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------------------------------------------------------------- tema icone
def icon_theme_name(key: str | None = None) -> str:
    """Nome del tema icone tinto per il profilo (NexusSec-<Profilo>).
    I temi sono pre-generati al build da build/make-icons.py ed ereditano
    NexusSec-Core/nuoveXT2/Adwaita per la copertura completa."""
    k = key or current_profile()
    return "NexusSec-" + (k[:1].upper() + k[1:])


def _replace_line(path: Path, prefix: str, newline: str) -> None:
    """Sostituisce (o aggiunge) una riga che inizia con prefix in un file di
    config a righe, senza toccare le altre impostazioni."""
    try:
        lines = path.read_text().splitlines() if path.exists() else []
    except Exception:                     # noqa: BLE001
        lines = []
    out, done = [], False
    for ln in lines:
        if ln.strip().startswith(prefix):
            out.append(newline); done = True
        else:
            out.append(ln)
    if not done:
        out.append(newline)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n")


def set_icon_theme(key: str | None = None, refresh: bool = False) -> str:
    """Imposta il tema icone GTK2/GTK3 sul profilo (icone tinte con l'accent).
    Con refresh=True riavvia il desktop pcmanfm per ricaricarle a caldo."""
    theme = icon_theme_name(key)
    _replace_line(HOME / ".config" / "gtk-3.0" / "settings.ini",
                  "gtk-icon-theme-name", f"gtk-icon-theme-name={theme}")
    _replace_line(HOME / ".gtkrc-2.0",
                  "gtk-icon-theme-name", f'gtk-icon-theme-name="{theme}"')
    if refresh and shutil.which("pcmanfm"):
        # pcmanfm legge il tema icone all'avvio: lo riavvio (poi il chiamante
        # riapplica lo sfondo, che richiede pcmanfm --desktop attivo).
        subprocess.run(["pkill", "-f", "pcmanfm --desktop"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.Popen(["pcmanfm", "--desktop", "--profile=NexusSec"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return theme


# ---------------------------------------------------------------- attivazione
def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _forensic_writeblock(key: str, log=print) -> None:
    """Write-blocker forense agganciato al profilo (nxs-writeblock).

    In 'forensics' mette in sola lettura a livello di BLOCCO i dischi/partizioni
    fisici non in uso dal sistema, per impedire scritture accidentali sulle prove
    (anche il replay del journal al mount). In OGNI altro profilo rilascia
    l'eventuale blocco: la distro resta polifunzionale, nessuna collisione.

    Best-effort e NON bloccante: non deve mai far fallire il cambio profilo.
    Inerte se il comando non c'e' (host di sviluppo)."""
    if not _have("nxs-writeblock"):
        return
    action = "on" if key == "forensics" else "off"
    try:
        subprocess.run(["nxs-writeblock", action],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=30)
        if action == "on":
            log("[*] write-blocker forense ATTIVO: dischi esterni in sola lettura "
                "(sblocco destinazione: nxs-writeblock unlock <dev>).")
    except Exception:                        # noqa: BLE001
        pass


def activate_profile(key: str, clean_previous: bool = False, log=print) -> bool:
    """Attiva un profilo: installa il meta-pacchetto apk, poi applica
    sfondo + accent e salva lo stato.

    clean_previous=True rimuove prima il meta-pacchetto del profilo
    precedente (modalita' "monomissione": sistema sempre pulito).
    """
    if key not in profiles():
        log(f"[!] profilo sconosciuto: {key}")
        return False

    meta = profile_data(key).get("meta")
    prev = current_profile()
    prev_meta = profile_data(prev).get("meta")

    if _have("apk"):
        if clean_previous and prev_meta and prev != key:
            log(f"[*] rimuovo profilo precedente: {prev_meta}")
            subprocess.run(["apk", "del", prev_meta])
        if meta:
            log(f"[*] attivo profilo: apk add --no-cache {meta}")
            r = subprocess.run(["apk", "add", "--no-cache", meta])
            if r.returncode != 0:
                log(f"[!] apk add {meta} fallito (continuo con sfondo/accent).")
    else:
        log("[*] apk non disponibile (dev/host): salto l'installazione tool.")

    set_current(key)
    # Tema icone PRIMA dello sfondo: set_icon_theme(refresh) riavvia pcmanfm
    # --desktop, e set_wallpaper ne ha bisogno attivo per disegnare lo sfondo.
    # Breve attesa per dare tempo al daemon pcmanfm di ripartire.
    set_icon_theme(key, refresh=True)
    time.sleep(0.8)
    set_wallpaper(wallpaper_path(key))
    write_accent_css(key)
    set_window_theme(key)          # bordi/decorazioni finestra col profilo
    _forensic_writeblock(key, log)
    return True


def apply_current() -> dict:
    """Riapplica sfondo + accent del profilo gia' corrente (uso all'avvio,
    senza reinstallare nulla)."""
    key = current_profile()
    # Sincronizza il tema icone col profilo (senza refresh: a boot pcmanfm
    # parte gia' col tema scritto qui/nel default; lo switch a caldo avviene
    # quando l'utente cambia profilo via activate_profile).
    set_icon_theme(key)
    set_wallpaper(wallpaper_path(key))
    write_accent_css(key)
    set_window_theme(key)          # bordi/decorazioni finestra col profilo
    _forensic_writeblock(key)
    return profile_data(key)


# Compatibilita': il selettore chiama apply_profile.
def apply_profile(key: str) -> dict:
    activate_profile(key)
    return profile_data(key)
