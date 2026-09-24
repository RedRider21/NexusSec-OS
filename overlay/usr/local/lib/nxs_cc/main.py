# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
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

from nxs_cc.common import (apply_css, info_dialog, install_screens_refresh_monitor,
                           center_toplevel_windows)
from nxs_cc import views

try:
    from nxs_i18n import t as _t          # traduzioni (it/en/fr/es/de)
except Exception:                         # noqa: BLE001
    def _t(key, **kw):                    # fallback: non rompe mai la UI
        return key


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
                info_dialog(_t("v.error"), "%s: %s" % (type(e).__name__, e),
                            level="error")
            except Exception:
                pass
        return None
    return wrapper

# NB: NIENTE stringhe tradotte a livello di modulo. Il demone "caldo"
# (nxs_cc.launcherd) importa questo modulo UNA volta: una costante legata qui
# resterebbe nella lingua del boot. Le stringhe si risolvono con _t() al momento
# di costruire la finestra (vedi build_window), cosi' seguono la lingua attiva.

# Viste apribili direttamente da riga di comando (usate dal menu Openbox
# per saltare al pannello giusto senza passare da un terminale):
#   nxs-control-center pacchetti
def _apri_casi(_btn=None):
    """Apre la gestione dei casi forensi (import pigro, come per i dischi)."""
    from nxs_case.view import open_case
    return open_case()


def _apri_dischi(_btn=None):
    """Apre il gestore dischi. Import pigro: nxs_disks vive in un modulo suo
    (riusabile in Vesper) e il Centro di Controllo deve partire anche senza."""
    from nxs_disks.view import open_disks
    return open_disks()


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
    "aspetto-coordinato": views.open_appearance,
    "appearance": views.open_appearance,
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
    "sicurezza": views.open_security,
    "security": views.open_security,
    "firewall": views.open_firewall,
    "utenti": views.open_users,
    "users": views.open_users,
    "schermi": views.open_screens,
    "screens": views.open_screens,
    "dischi": _apri_dischi,
    "disks": _apri_dischi,
    "casi": _apri_casi,
    "case": _apri_casi,
    "mouse": views.open_mouse,
    "touchpad": views.open_mouse,
    "ia": views.open_ai,
    "ai": views.open_ai,
    "assistente": views.open_ai,
    "lingua": views.open_language,
    "language": views.open_language,
}


class Tile(Gtk.Button):
    def __init__(self, icon_name: str, label: str, tooltip: str, handler):
        super().__init__()
        self.set_relief(Gtk.ReliefStyle.NONE)
        self.get_style_context().add_class("nxs-tile")
        self.set_tooltip_text(tooltip)
        # Come nel mockup: icona in un BADGE arrotondato in alto a sinistra,
        # etichetta sotto allineata a sinistra.
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_halign(Gtk.Align.START)
        box.set_valign(Gtk.Align.START)
        badge = Gtk.Box()
        badge.get_style_context().add_class("nxs-tile-badge")
        badge.set_halign(Gtk.Align.START)
        img = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.LARGE_TOOLBAR)
        img.set_pixel_size(22)
        badge.add(img)
        lbl = Gtk.Label(label=label)
        lbl.set_xalign(0)
        lbl.set_line_wrap(True)
        lbl.set_max_width_chars(16)
        box.pack_start(badge, False, False, 0)
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
    app_title = _t("cc.app_title")
    win = Gtk.Window(title=app_title)
    win.set_default_size(820, 560)
    win.set_position(Gtk.WindowPosition.CENTER)
    win.connect("destroy", Gtk.main_quit)

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    win.add(outer)

    header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    header.get_style_context().add_class("nxs-headerbar")
    title = Gtk.Label(label=app_title); title.set_xalign(0)
    title.get_style_context().add_class("title")
    sub = Gtk.Label(label=_t("cc.subtitle")); sub.set_xalign(0)
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

    body.pack_start(section(_t("cc.sec.profile"), [
        Tile("preferences-system", _t("cc.t.profile"),
             _t("cc.d.profile"),
             launch_app(["nxs-profile"])),
    ]), False, False, 0)

    body.pack_start(section(_t("cc.sec.appearance"), [
        Tile("preferences-desktop-locale", _t("cc.t.language"),
             _t("cc.d.language"), launch("lingua")),
        Tile("preferences-desktop-theme", _t("cc.t.appearance"),
             _t("cc.d.appearance"), launch("aspetto-coordinato")),
        Tile("preferences-desktop-theme", _t("cc.t.gtktheme"),
             _t("cc.d.gtktheme"), launch("tema-gtk")),
        Tile("preferences-desktop-wallpaper", _t("cc.t.wallpaper"),
             _t("cc.d.wallpaper"),
             launch("sfondo")),
        Tile("preferences-desktop-screensaver", _t("cc.t.screensaver"),
             _t("cc.d.screensaver"), launch("salvaschermo")),
        Tile("preferences-system-windows", _t("cc.t.windowstyle"),
             _t("cc.d.windowstyle"), launch("stile-finestre")),
    ]), False, False, 0)

    body.pack_start(section(_t("cc.sec.openbox"), [
        Tile("preferences-system-windows", _t("cc.t.obtheme"),
             _t("cc.d.obtheme"), launch("temi-finestre")),
        Tile("input-mouse", _t("cc.t.menu"),
             _t("cc.d.menu"), launch("menu")),
        Tile("preferences-desktop-display", _t("cc.t.panel"),
             _t("cc.d.panel"), launch("pannello")),
    ]), False, False, 0)

    body.pack_start(section(_t("cc.sec.system"), [
        Tile("computer", _t("cc.t.sysinfo"),
             _t("cc.d.sysinfo"), launch("sysinfo")),
        Tile("utilities-system-monitor", _t("cc.t.monitor"),
             _t("cc.d.monitor"), launch("monitor")),
        Tile("applications-science", _t("cc.t.ai"),
             _t("cc.d.ai"), launch("ia")),
        Tile("system-software-install", _t("cc.t.packages"),
             _t("cc.d.packages"), launch("pacchetti")),
        Tile("utilities-terminal", _t("cc.t.logs"),
             _t("cc.d.logs"), launch("log")),
    ]), False, False, 0)

    body.pack_start(section(_t("cc.sec.hardware"), [
        Tile("input-keyboard", _t("cc.t.keyboard"), _t("cc.d.keyboard"), launch("tastiera")),
        Tile("network-wired", _t("cc.t.network"),
             _t("cc.d.network"), launch("rete")),
        Tile("bluetooth", _t("cc.t.bluetooth"),
             _t("cc.d.bluetooth"),
             launch("bluetooth")),
        Tile("preferences-desktop-display", _t("cc.t.screens"),
             _t("cc.d.screens"),
             launch("schermi")),
        Tile("drive-harddisk", _t("cc.t.disks"),
             _t("cc.d.disks"),
             launch("dischi")),
        Tile("input-mouse", _t("cc.t.mouse"),
             _t("cc.d.mouse"),
             launch("mouse")),
        Tile("nxs-case", _t("cc.t.cases"),
             _t("cc.d.cases"),
             launch("casi")),
    ]), False, False, 0)

    body.pack_start(section(_t("cc.sec.security"), [
        Tile("security-high", _t("cc.t.security"),
             _t("cc.d.security"), launch("sicurezza")),
        Tile("network-firewall", _t("cc.t.firewall"),
             _t("cc.d.firewall"), launch("firewall")),
        Tile("system-users", _t("cc.t.users"),
             _t("cc.d.users"),
             launch("utenti")),
    ]), False, False, 0)

    body.pack_start(section(_t("cc.sec.personal"), [
        Tile("preferences-desktop-keyboard-shortcuts", _t("cc.t.hotkeys"),
             _t("cc.d.hotkeys"), launch("hotkey")),
        Tile("system-run", _t("cc.t.autostart"),
             _t("cc.d.autostart"), launch("autostart")),
    ]), False, False, 0)

    footer = Gtk.Label(label=_t("cc.footer"))
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
        info_dialog(_t("cc.start_error"),
                    _t("cc.start_error_body"), level="error")
        return 1
    # Dopo un cambio schermi (nxs-screens) la finestra si ricentra sul monitor
    # attivo da sola, senza chiudere e riaprire.
    install_screens_refresh_monitor(center_toplevel_windows)
    Gtk.main()
    return 0
