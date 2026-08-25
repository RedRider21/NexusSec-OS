"""Centro di Controllo NexusSec OS.

Stile MATE Control Center: finestra unica con sezioni e tiles. Ogni tile
apre una vera interfaccia grafica nativa (vedi nxs_cc/views.py), non un
terminale ne un dump testuale.
"""
from __future__ import annotations

import subprocess
import sys
import traceback

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from nxs_cc.common import apply_css, info_dialog
from nxs_cc import views


def launch(view: str):
    """Apre una vista come PROCESSO separato (nxs-control-center <view>).

    Cosi' la finestra principale resta una sola toplevel (su Xfbdev aprire
    piu' toplevel nello stesso processo si e' rivelato instabile) e un
    eventuale crash della vista non porta giu' il Centro di Controllo.
    """
    def handler(_btn=None):
        try:
            subprocess.Popen(["nxs-control-center", view])
        except Exception:                # noqa: BLE001
            traceback.print_exc()
            # fallback in-process se il launcher non e' nel PATH
            fn = VIEW_MAP.get(view)
            if fn:
                fn()
    return handler


def launch_app(argv):
    """Handler che avvia un'applicazione esterna (processo separato)."""
    def handler(_btn=None):
        try:
            subprocess.Popen(argv)
        except Exception:                # noqa: BLE001
            traceback.print_exc()
    return handler


def safe(handler):
    """Avvolge un handler di tile: un'eccezione mostra un dialog e viene
    loggata (su /tmp/nxs-cc.log via stderr) invece di chiudere tutto.
    Logga inizio/fine dell'handler con flush, cosi' un crash NATIVO (che
    salta il try/except) lascia comunque traccia nel log."""
    name = getattr(handler, "__name__", str(handler))
    def wrapper(*args, **kwargs):
        print("[cc] >>> apertura: %s" % name, flush=True)
        try:
            r = handler(*args, **kwargs)
            print("[cc] <<< completato: %s" % name, flush=True)
            return r
        except Exception as e:           # noqa: BLE001
            traceback.print_exc()
            try:
                info_dialog("Errore", "%s: %s" % (type(e).__name__, e),
                            level="error")
            except Exception:
                pass
        return None
    return wrapper

APP_TITLE = "NexusSec // Centro di Controllo"

# Viste apribili direttamente da riga di comando (usate dal menu Openbox
# per saltare al pannello giusto senza passare da un terminale):
#   nxs-control-center pacchetti
VIEW_MAP = {
    "sysinfo": views.open_sysinfo,
    "monitor": views.open_monitor,
    "rete": views.open_network,
    "network": views.open_network,
    "pacchetti": views.open_packages,
    "packages": views.open_packages,
    "log": views.open_logs,
    "logs": views.open_logs,
    "hotkey": views.open_hotkeys,
    "barra": views.open_statusbar,
    "pannello": views.open_statusbar,
    "statusbar": views.open_statusbar,
    "panel": views.open_statusbar,
    "temi-finestre": views.open_openbox_theme,
    "openbox-theme": views.open_openbox_theme,
    "menu": views.open_menu_editor,
    "tema-gtk": views.open_gtk_theme,
    "tastiera": views.open_keyboard,
    "sfondo": views.open_wallpaper,
    "salvaschermo": views.open_screensaver,
    "screensaver": views.open_screensaver,
    "autostart": views.open_autostart,
    "bluetooth": views.open_bluetooth,
    "stile-finestre": views.open_window_style,
    "window-style": views.open_window_style,
}


class Tile(Gtk.Button):
    def __init__(self, icon_name: str, label: str, tooltip: str, handler):
        super().__init__()
        self.set_relief(Gtk.ReliefStyle.NONE)
        self.get_style_context().add_class("nxs-tile")
        self.set_tooltip_text(tooltip)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        img = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.DIALOG)
        img.set_pixel_size(36)
        lbl = Gtk.Label(label=label)
        lbl.set_justify(Gtk.Justification.CENTER)
        lbl.set_line_wrap(True)
        lbl.set_max_width_chars(14)
        box.pack_start(img, False, False, 0)
        box.pack_start(lbl, False, False, 0)
        self.add(box)
        self.connect("clicked", safe(handler))


def section(title: str, tiles: list[Tile]) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    lab = Gtk.Label(label=title)
    lab.set_xalign(0)
    lab.get_style_context().add_class("nxs-section")
    box.pack_start(lab, False, False, 0)
    flow = Gtk.FlowBox()
    flow.set_selection_mode(Gtk.SelectionMode.NONE)
    flow.set_max_children_per_line(8)
    flow.set_min_children_per_line(1)
    flow.set_homogeneous(True)
    flow.set_column_spacing(10)
    flow.set_row_spacing(10)
    for t in tiles:
        flow.add(t)
    box.pack_start(flow, False, False, 0)
    return box


def build_window() -> Gtk.Window:
    apply_css()
    win = Gtk.Window(title=APP_TITLE)
    win.set_default_size(820, 560)
    win.set_position(Gtk.WindowPosition.CENTER)
    win.connect("destroy", Gtk.main_quit)

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    win.add(outer)

    header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    header.get_style_context().add_class("nxs-headerbar")
    title = Gtk.Label(label=APP_TITLE); title.set_xalign(0)
    title.get_style_context().add_class("title")
    sub = Gtk.Label(label="Strumenti di configurazione del sistema"); sub.set_xalign(0)
    sub.get_style_context().add_class("subtitle")
    header.pack_start(title, False, False, 0)
    header.pack_start(sub, False, False, 0)
    outer.pack_start(header, False, False, 0)

    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    outer.pack_start(sw, True, True, 0)

    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
    body.set_margin_top(12); body.set_margin_bottom(12)
    body.set_margin_start(16); body.set_margin_end(16)
    sw.add(body)

    body.pack_start(section("Profilo operativo", [
        Tile("preferences-system", "Cambia profilo",
             "Pen Testing, Forensics, OSINT, Web: menu e sfondo si adattano",
             launch_app(["nxs-profile"])),
    ]), False, False, 0)

    body.pack_start(section("Aspetto e tema", [
        Tile("preferences-desktop-theme", "Tema GTK e icone",
             "Tema GTK, set di icone e cursori (lxappearance)", launch("tema-gtk")),
        Tile("preferences-desktop-wallpaper", "Sfondo",
             "Scegli l'immagine di sfondo", launch("sfondo")),
        Tile("preferences-desktop-screensaver", "Salvaschermo",
             "Salvaschermo animato: attivazione, tempo e stile", launch("salvaschermo")),
        Tile("preferences-system-windows", "Stile finestre",
             "Aspetto delle finestre: Vetro, Flat o Telaio", launch("stile-finestre")),
    ]), False, False, 0)

    body.pack_start(section("Openbox e pannello", [
        Tile("preferences-system-windows", "Temi finestre",
             "Bordi e decorazioni finestre (+ obconf)", launch("temi-finestre")),
        Tile("input-mouse", "Menu tasto destro",
             "Modifica il menu del click destro (menu.xml)", launch("menu")),
        Tile("preferences-desktop-display", "Pannello",
             "Posizione (alto/basso), avvio, riavvio", launch("pannello")),
    ]), False, False, 0)

    body.pack_start(section("Sistema", [
        Tile("computer", "Info sistema",
             "CPU, RAM, disco, kernel, uptime", launch("sysinfo")),
        Tile("utilities-system-monitor", "Monitor",
             "CPU, RAM, rete e disco in tempo reale", launch("monitor")),
        Tile("system-software-install", "Pacchetti",
             "Cerca e installa pacchetti Alpine (apk)", launch("pacchetti")),
        Tile("utilities-terminal", "Log di sistema",
             "autostart, pannello, Xorg", launch("log")),
    ]), False, False, 0)

    body.pack_start(section("Hardware", [
        Tile("input-keyboard", "Tastiera", "Layout italiano / US", launch("tastiera")),
        Tile("network-wired", "Rete",
             "Interfacce, IP e test di connessione", launch("rete")),
        Tile("bluetooth", "Bluetooth",
             "Accensione, scansione, abbinamento e connessione dispositivi",
             launch("bluetooth")),
    ]), False, False, 0)

    body.pack_start(section("Personale", [
        Tile("preferences-desktop-keyboard-shortcuts", "Tasti rapidi",
             "Elenco scorciatoie da tastiera", launch("hotkey")),
        Tile("system-run", "Autostart",
             "Programmi avviati con la sessione", launch("autostart")),
    ]), False, False, 0)

    footer = Gtk.Label(label="NexusSec OS  -  Centro di Controllo")
    footer.set_xalign(0)
    footer.get_style_context().add_class("nxs-footer")
    outer.pack_start(footer, False, False, 0)

    return win


def run() -> int:
    apply_css()
    args = sys.argv[1:]
    try:
        if args and args[0] in VIEW_MAP:
            # Apre solo la vista richiesta (modalita' standalone da menu).
            VIEW_MAP[args[0]]()
            for w in Gtk.Window.list_toplevels():
                if w.get_visible():
                    w.connect("destroy", Gtk.main_quit)
        else:
            win = build_window()
            win.show_all()
    except Exception:                    # noqa: BLE001
        traceback.print_exc()
        info_dialog("Errore di avvio",
                    "Vedi /tmp/nxs-cc.log per i dettagli.", level="error")
        return 1
    Gtk.main()
    return 0
