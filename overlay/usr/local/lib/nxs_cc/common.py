"""Helper condivisi e tema del Centro di Controllo NexusSec."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib  # noqa: E402

HOME = Path(os.path.expanduser("~"))

# Palette Nebula
COL_BG = "#050a14"
COL_PANEL = "#0a1a26"
COL_ACCENT = "#00e5ff"
COL_TEXT = "#c8f5ff"
COL_DIM = "#5a8a9a"
COL_BORDER = "#1a3a52"
COL_ALERT = "#ff5a8a"

CSS = b"""
window, .background, dialog { background-color: #050a14; color: #c8f5ff; }
/* Font dell'interfaccia (inclusi in /usr/share/fonts/nexussec): titoli ed
   etichette in Chakra Petch (look "tech" del mockup), meta in IBM Plex Mono. */
.nxs-headerbar label.title, .nxs-section, .nxs-key, .nxs-card-title,
.nxs-tile label, frame > label, .nxs-primary, .nxs-primary label {
  font-family: "Chakra Petch", "DejaVu Sans", sans-serif;
}
.nxs-headerbar label.subtitle, .nxs-footer {
  font-family: "IBM Plex Mono", monospace;
}
.nxs-section {
  color: #00e5ff; font-weight: bold; font-size: 11pt;
  padding: 10px 4px 6px 4px; border-bottom: 1px solid #1a3a52; margin-bottom: 8px;
}
.nxs-tile {
  background-color: #0a1422; color: #c8f5ff;
  border: 1px solid #12202e; border-radius: 12px;
  padding: 14px; min-width: 110px; min-height: 96px;
  transition: background-color 120ms ease, border-color 120ms ease;
}
.nxs-tile:hover { background-color: rgba(0,229,255,0.10); border-color: #00e5ff; }
.nxs-tile:active, .nxs-tile:focus { background-color: rgba(0,229,255,0.18); border-color: #00e5ff; }
.nxs-tile label { color: #c8f5ff; font-size: 9pt; }
.nxs-tile-badge { background-color: rgba(0,229,255,0.14); border-radius: 9px;
  padding: 7px; min-width: 20px; min-height: 20px; }
.nxs-tile-badge image { color: #00e5ff; }
.nxs-headerbar {
  background-color: #0a1a26; color: #c8f5ff;
  border-bottom: 1px solid #00e5ff; padding: 8px 14px;
}
.nxs-headerbar label.title { color: #00e5ff; font-weight: bold; font-size: 12pt; }
.nxs-headerbar label.subtitle { color: #5a8a9a; font-size: 9pt; }
/* Eyebrow: marchietto "NexusSec" discreto in cima all'header (mono, accent). */
.nxs-eyebrow { color: #35d0e0; font-family: "IBM Plex Mono", monospace;
  font-size: 8pt; margin-bottom: 2px; }
.nxs-footer {
  background-color: #050a14; color: #5a8a9a;
  border-top: 1px solid #1a3a52; padding: 6px 12px; font-size: 8pt;
}
.nxs-key { color: #00e5ff; font-weight: bold; font-size: 11pt; }
.nxs-val { color: #c8f5ff; font-size: 11pt; }
.nxs-card {
  background-color: #0a1422; border: 1px solid #12202e;
  border-radius: 12px; padding: 14px; margin: 4px;
}
.nxs-card-title { color: #00e5ff; font-weight: bold; }
textview, textview text {
  background-color: #050a14; color: #c8f5ff;
  font-family: monospace; caret-color: #00e5ff;
}
textview text selection { background-color: #00e5ff; color: #050a14; }
button {
  background-image: none; background-color: #0d1622; color: #c8f5ff;
  border: 1px solid #17293a; border-radius: 9px; padding: 7px 16px;
  transition: background-color 120ms ease, border-color 120ms ease;
}
button:hover { border-color: #00e5ff; background-color: #12202e; }
button:active, button:checked { background-color: #00e5ff; color: #050a14; }
button.nxs-primary { background-color: #00334a; border-color: #00e5ff; color: #00e5ff; }
button.nxs-primary:hover { background-color: #00475f; }
entry {
  background-color: #070f1a; color: #c8f5ff;
  border: 1px solid #17293a; border-radius: 9px; caret-color: #00e5ff; padding: 6px 12px;
}
entry:focus { border-color: #00e5ff; }
treeview {
  background-color: #050a14; color: #c8f5ff;
}
treeview:selected { background-color: #00334a; color: #00e5ff; }
treeview header button {
  background-color: #0a1a26; color: #00e5ff; border: none;
  border-bottom: 1px solid #1a3a52; border-radius: 0; font-weight: bold;
}
progressbar > trough { background-color: #0a1422; border: 1px solid #17293a;
  min-height: 12px; border-radius: 7px; }
progressbar > trough > progress { background-color: #00e5ff; border-radius: 7px; }
progressbar.nxs-warn > trough > progress { background-color: #ffaa00; }
progressbar.nxs-alert > trough > progress { background-color: #ff5a8a; }
levelbar block.filled { background-color: #00e5ff; }
notebook header { background-color: #0a1a26; }
notebook tab { background-color: transparent; color: #5a8a9a; padding: 6px 12px;
  margin: 2px 1px 0 1px; border-radius: 8px 8px 0 0; }
notebook tab:hover { background-color: #101b28; color: #c8f5ff; }
notebook tab:checked { color: #00e5ff; background-color: #0d1622;
  box-shadow: inset 0 -2px #00e5ff; }
switch { background-color: #0a1422; border: 1px solid #17293a; border-radius: 13px; }
switch:checked { background-color: #00334a; border-color: #00e5ff; }
switch slider { background-color: #5a8a9a; border-radius: 50%; }
switch:checked slider { background-color: #00e5ff; }
radiobutton, checkbutton { color: #c8f5ff; }
combobox { color: #c8f5ff; }
frame { border-radius: 12px; }
frame > border { border: 1px solid #17293a; border-radius: 12px; }
frame > label { color: #00e5ff; font-weight: bold; }
spinner { color: #00e5ff; }

/* ---- Pannello inferiore stile MATE (nxs-panel) ---- */
.nxs-panel {
  background-color: #0a1a26;
  border-top: 1px solid #1a3a52;
}
.nxs-panel.nxs-panel-top { border-top: none; border-bottom: 1px solid #1a3a52; }
.nxs-panel button {
  background-color: transparent; background-image: none;
  border: 1px solid transparent; border-radius: 3px;
  color: #c8f5ff; padding: 2px 10px; margin: 3px 1px;
}
.nxs-panel button:hover { background-color: rgba(0,229,255,0.10); border-color: #1a3a52; }
.nxs-panel button:active { background-color: rgba(0,229,255,0.20); }
/* Icone simboliche monocrome in cyan Nebula */
.nxs-panel button image { color: #00e5ff; -gtk-icon-style: symbolic; }
.nxs-panel button.nxs-icon { padding: 3px 8px; margin: 2px 1px; }
.nxs-panel button.nxs-icon:hover image { color: #c8f5ff; }
.nxs-panel button.nxs-menu { color: #00e5ff; font-weight: bold; padding: 2px 12px; }
.nxs-panel button.nxs-menu image { color: #00e5ff; }
.nxs-panel button.nxs-launcher { padding: 2px 8px; }
.nxs-panel button.nxs-task {
  color: #5a8a9a; padding: 2px 12px; margin: 3px 1px;
}
.nxs-panel button.nxs-task:hover { color: #c8f5ff; }
.nxs-panel button.nxs-task-active {
  color: #00e5ff; background-color: rgba(0,229,255,0.12);
  border-color: #1a3a52;
}
/* Pager desktop virtuali (workspaces) */
.nxs-panel button.nxs-pager-btn {
  color: #5a8a9a; padding: 1px 8px; margin: 4px 1px; font-size: 9pt;
  min-width: 20px; border: 1px solid #163040; border-radius: 6px;
}
.nxs-panel button.nxs-pager-btn:hover { color: #c8f5ff; }
.nxs-panel button.nxs-pager-active {
  color: #050a14; background-color: #00e5ff; border-color: #00e5ff;
  font-weight: bold;
}
.nxs-panel label.nxs-clock { color: #c8f5ff; font-size: 10pt; padding: 0 6px; }
.nxs-panel label.nxs-clock-date { color: #5a8a9a; font-size: 8pt; padding: 0 6px; }
.nxs-panel separator { background-color: #1a3a52; margin: 5px 4px; }
/* Menu a comparsa del pulsante NexusSec */
menu, .menu, menu.background {
  background-color: #0a1a26; color: #c8f5ff; border: 1px solid #1a3a52;
}
menu menuitem { padding: 6px 14px; }
menu menuitem:hover { background-color: rgba(0,229,255,0.14); color: #00e5ff; }
menu separator { background-color: #1a3a52; }

/* Popup del pannello come finestre toplevel (menu start, calendario) */
.nxs-popup, .nxs-popup.background {
  background-color: #0a1a26; border: 1px solid #1a3a52;
}

/* Menu NexusSec con banda verticale stile Windows */
popover.nxs-startmenu, popover.nxs-startmenu.background {
  background-color: #0a1a26; border: 1px solid #1a3a52; padding: 0;
}
popover.nxs-startmenu > arrow {
  background-color: #00334a; border: 1px solid #1a3a52;
}
.nxs-menu-strip {
  background-image: linear-gradient(to top, #03070f, #00334a 45%, #00e5ff);
  border-right: 1px solid #1a3a52;
  padding: 10px 6px;
}
.nxs-menu-strip label.brand {
  color: #eafcff; font-weight: bold; font-size: 14pt;
  text-shadow: 0 1px 2px rgba(0,0,0,0.6);
}
.nxs-menu-strip label.brand-sub {
  color: #dff6ff; font-weight: bold; font-size: 9pt;
  text-shadow: 0 1px 2px rgba(0,0,0,0.7);
}
.nxs-startmenu-list { padding: 6px; }
button.nxs-menu-item {
  background-color: transparent; background-image: none;
  border: 1px solid transparent; border-radius: 3px;
  color: #c8f5ff; padding: 7px 16px 7px 10px; margin: 1px 2px;
}
button.nxs-menu-item label { color: #c8f5ff; }
button.nxs-menu-item image { color: #00e5ff; }
button.nxs-menu-item:hover {
  background-color: rgba(0,229,255,0.14); border-color: #1a3a52;
}
button.nxs-menu-item:hover label { color: #00e5ff; }
.nxs-startmenu-list separator { background-color: #1a3a52; margin: 4px 6px; }

/* Ricerca strumenti in cima al menu start */
entry.nxs-menu-search {
  background-color: #050a14; color: #c8f5ff;
  border: 1px solid #1a3a52; border-radius: 3px;
  margin: 6px 8px 2px 8px; padding: 4px 6px;
}
entry.nxs-menu-search:focus { border-color: #00e5ff; }
entry.nxs-menu-search image { color: #5a8a9a; }

/* Intestazione di categoria nella lista tool: banda di sezione con marcatore
   accent a sinistra e lieve gradiente (NB: niente text-transform/letter-spacing
   = proprieta' GTK4, in GTK3 fanno fallire il parser CSS). */
label.nxs-menu-cat {
  color: #5a8a9a; font-size: 10px; font-weight: bold;
  padding: 8px 10px 2px 12px;
}
button.nxs-menu-cat {
  background-image: linear-gradient(to right, rgba(0,229,255,0.06), rgba(0,229,255,0));
  border: none; border-left: 2px solid #1a3a52; box-shadow: none;
  padding: 7px 10px 7px 12px; margin: 3px 4px 1px 4px;
  color: #7fb0c2; font-size: 10px; font-weight: bold;
}
button.nxs-menu-cat:hover {
  background-image: linear-gradient(to right, rgba(0,229,255,0.16), rgba(0,229,255,0));
  border-left-color: #00e5ff; color: #00e5ff;
}
/* Righe-tool (e app): rientrate sotto la categoria, con barra accent all'hover
   e sfondo tenue, per una lista piu' leggibile e curata. */
button.nxs-tool-item {
  padding-left: 26px; margin: 1px 4px 1px 8px;
  border-left: 2px solid transparent; border-radius: 0 3px 3px 0;
}
button.nxs-tool-item:hover {
  border-left-color: #00e5ff; background-color: rgba(0,229,255,0.12);
}
button.nxs-tool-item label { font-size: 10.5px; }
/* Pallino di stato del tool: verde=installato, ambra=da scaricare, grigio=ignoto */
label.nxs-tool-dot { font-size: 11px; margin-left: 6px; }
label.nxs-tool-dot.ok { color: #4be38a; text-shadow: 0 0 4px rgba(75,227,138,0.6); }
label.nxs-tool-dot.todo { color: #e5b34b; text-shadow: 0 0 4px rgba(229,179,75,0.5); }
label.nxs-tool-dot.unknown { color: #5a8a9a; }
/* Lo scroller del menu non deve disegnare un fondo opaco sopra il popup */
.nxs-startmenu-scroll, .nxs-startmenu-scroll viewport {
  background-color: transparent; border: none;
}

/* Pulsante orologio + calendario a comparsa (stile MATE) */
.nxs-panel button.nxs-clock-btn { padding: 1px 8px; margin: 2px 1px; }
.nxs-calbox { padding: 6px; }
calendar.nxs-calendar {
  background-color: #0a1a26; color: #c8f5ff;
  border: 1px solid #1a3a52; padding: 4px;
}
calendar.nxs-calendar:selected {
  background-color: #00e5ff; color: #050a14; border-radius: 3px;
}
calendar.nxs-calendar.header { color: #00e5ff; font-weight: bold; }
calendar.nxs-calendar.button { color: #00e5ff; }
calendar.nxs-calendar.highlight { color: #00e5ff; }
calendar.nxs-calendar:indeterminate { color: #5a8a9a; }

/* Righe regolazione ora/data/fuso nel popup dell'orologio */
.nxs-dt-row { padding: 2px 2px; }
.nxs-dt-row label { color: #5a8a9a; font-size: 9pt; padding: 0 2px; }
.nxs-dt-row spinbutton, .nxs-dt-row combobox {
  background-color: #0a1a26; color: #c8f5ff;
  border: 1px solid #1a3a52; min-height: 20px;
}
.nxs-dt-row spinbutton entry { background-color: #0a1a26; color: #c8f5ff; }
.nxs-dt-row button.nxs-menu-item { padding: 1px 8px; }

/* Applet monitor risorse (mini-grafici CPU/RAM/Rete) */
.nxs-loadmon { padding: 0 2px; margin: 2px 1px; }
"""

_css_done = False


# Accent del profilo: CSS opzionale generato da nxs_profiles (model.write_accent_css).
ACCENT_CSS_FILE = HOME / ".config" / "nxs" / "accent.css"
# Stile finestre (flat/vetro/telaio): CSS generato da nxs_profiles, sopra l'accent.
WINDOW_STYLE_CSS_FILE = HOME / ".config" / "nxs" / "window-style.css"


def apply_css() -> None:
    global _css_done
    if _css_done:
        return
    prov = Gtk.CssProvider()
    # Difensivo: un errore nel CSS NON deve mai far crashare il pannello/le app
    # (in GTK3 load_from_data SOLLEVA su CSS non valido). Se fallisce, l'app
    # resta funzionante col tema GTK di default.
    try:
        prov.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), prov,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    except Exception:                    # noqa: BLE001
        import sys
        print("[nxs] CSS non applicato (parse error):", sys.exc_info()[1],
              file=sys.stderr)
    # Override accent del profilo attivo (priorita' piu' alta del tema base).
    if ACCENT_CSS_FILE.exists():
        try:
            ap = Gtk.CssProvider()
            ap.load_from_path(str(ACCENT_CSS_FILE))
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(), ap,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        except Exception:                # noqa: BLE001
            pass
    # Stile finestre (flat/vetro/telaio): caricato come UNICO provider tracciato
    # (sopra l'accent), cosi' un cambio stile lo rimuove e rimpiazza in modo
    # pulito (prima il provider d'avvio restava e i cambi non si vedevano).
    apply_window_style_live()
    _css_done = True


_live_style_prov = None


def _ensure_window_style_css() -> None:
    """Se window-style.css non esiste ancora su disco (es. profilo mai
    applicato, oppure primo avvio prima che `nxs-tool apply` scriva i CSS), lo
    generiamo al volo con lo stile scelto (default 'vetro'). Senza questo file
    lo stile finestre semplicemente NON si vedrebbe: e' la causa n.1 del
    sintomo "la grafica sulle finestre non si vede per nulla"."""
    if WINDOW_STYLE_CSS_FILE.exists():
        return
    try:
        from nxs_profiles import model            # import morbido
        model.write_window_style_css()
    except Exception:                              # noqa: BLE001
        pass


def _reset_widgets_kick() -> bool:
    """Forza GTK a ri-applicare lo stile a TUTTI i widget gia' realizzati.
    Necessario perche' il provider viene aggiunto quando la finestra e' gia'
    disegnata: GTK non ristila i widget realizzati finche' non cambia stato
    (es. perdita del focus -> :backdrop). Senza questo, lo stile appare solo
    dopo aver aperto una seconda finestra (sintomo riportato dall'utente).
    Ritorna False per non ripetersi (uso con GLib.idle_add)."""
    scr = Gdk.Screen.get_default()
    if scr is not None:
        try:
            Gtk.StyleContext.reset_widgets(scr)
        except Exception:                # noqa: BLE001
            pass
    return False


def apply_window_style_live() -> None:
    """Ricarica window-style.css a caldo (dopo un cambio di stile), sostituendo
    l'eventuale provider live precedente cosi' la finestra corrente si aggiorna
    subito senza riavvio."""
    global _live_style_prov
    scr = Gdk.Screen.get_default()
    if scr is None:
        return
    if _live_style_prov is not None:
        try:
            Gtk.StyleContext.remove_provider_for_screen(scr, _live_style_prov)
        except Exception:                # noqa: BLE001
            pass
        _live_style_prov = None
    _ensure_window_style_css()
    if not WINDOW_STYLE_CSS_FILE.exists():
        return
    try:
        p = Gtk.CssProvider()
        p.load_from_path(str(WINDOW_STYLE_CSS_FILE))
        Gtk.StyleContext.add_provider_for_screen(
            scr, p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 3)
        _live_style_prov = p
    except Exception:                    # noqa: BLE001
        return
    # Ristila SUBITO i widget gia' realizzati (vedi _reset_widgets_kick): una
    # volta a giro corrente e una a idle (dopo che la finestra e' mostrata).
    _reset_widgets_kick()
    try:
        GLib.idle_add(_reset_widgets_kick)
    except Exception:                    # noqa: BLE001
        pass


def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def run_bg(cmd: list[str]) -> None:
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError as e:
        info_dialog("Comando non trovato", str(e), level="warn")


def run_capture(cmd: list[str], timeout: int = 6) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = res.stdout or ""
        if res.returncode != 0 and res.stderr:
            out += ("\n" if out else "") + res.stderr.strip()
        return out.strip()
    except FileNotFoundError:
        return ""
    except subprocess.TimeoutExpired:
        return "(timeout)"


def info_dialog(title: str, body: str = "", level: str = "info", parent=None) -> None:
    typ = {"info": Gtk.MessageType.INFO, "warn": Gtk.MessageType.WARNING,
           "error": Gtk.MessageType.ERROR}.get(level, Gtk.MessageType.INFO)
    d = Gtk.MessageDialog(transient_for=parent, modal=True, message_type=typ,
                          buttons=Gtk.ButtonsType.OK, text=title)
    if body:
        d.format_secondary_text(body)
    d.run()
    d.destroy()


def panel_window(title: str, width: int = 640, height: int = 460):
    """Crea una finestra stilizzata con header. Ritorna (win, body_box)."""
    apply_css()
    win = Gtk.Window(title=title)
    win.set_default_size(width, height)
    win.set_position(Gtk.WindowPosition.CENTER)

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    win.add(outer)

    header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    header.get_style_context().add_class("nxs-headerbar")
    lab = Gtk.Label(label=title)
    lab.set_xalign(0)
    lab.get_style_context().add_class("title")
    header.pack_start(lab, True, True, 0)
    outer.pack_start(header, False, False, 0)

    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    body.set_margin_top(12)
    body.set_margin_bottom(12)
    body.set_margin_start(14)
    body.set_margin_end(14)
    outer.pack_start(body, True, True, 0)

    return win, body


def icon_button(label: str, icon_name: str, primary: bool = False):
    """Pulsante con icona + testo, coerente col tema Nebula.

    icon_name e' un nome di icona del tema (es. 'window-close',
    'preferences-desktop-keyboard'); se assente nel tema GTK ripiega
    sull'icona 'image-missing' senza rompere il layout.
    """
    btn = Gtk.Button()
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    img = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON)
    box.pack_start(img, False, False, 0)
    box.pack_start(Gtk.Label(label=label), False, False, 0)
    btn.add(box)
    if primary:
        btn.get_style_context().add_class("nxs-primary")
    return btn


def read_file(path) -> str:
    p = Path(path)
    try:
        return p.read_text() if p.exists() else f"(file inesistente: {p})"
    except OSError as e:
        return f"(errore lettura: {e})"
