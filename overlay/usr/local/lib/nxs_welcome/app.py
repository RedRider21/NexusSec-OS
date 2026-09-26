# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""Finestra di benvenuto di NexusSec (stile Linux Mint).

Si apre all'avvio della sessione, PRIMA del selettore del profilo (vedi
autostart: il selettore parte solo dopo la chiusura di questa finestra, cosi'
non la copre). Si puo' disattivare con la spunta "Mostra all'avvio" e si
richiama sempre dal menu.

Pagine: primi passi, licenze e software di terze parti, uso responsabile,
informazioni. Il testo delle licenze e' INFORMATIVO: descrive come stanno le
cose (NexusSec e' AGPL; i programmi dell'arsenale non sono inclusi ma si
scaricano al momento dalle fonti dei loro autori, alle loro condizioni) senza
promettere esoneri che la legge non consente.

    nxs-welcome           apre la finestra
    nxs-welcome --auto    come sopra, ma esce subito se l'utente l'ha disattivata
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib  # noqa: E402

try:
    from nxs_cc.common import apply_css
except Exception:                       # noqa: BLE001
    def apply_css():
        return

try:
    from nxs_i18n import t as _t
except Exception:                       # noqa: BLE001
    def _t(chiave, **kw):               # ripiego: mostra la chiave
        return chiave

CONF_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME")
                        or os.path.expanduser("~/.config"), "nxs")
FLAG_OFF = os.path.join(CONF_DIR, "welcome.off")
DOC_DIR = "/usr/share/doc/nexussec"
SITO = "https://redrider21.github.io/NexusSec-OS/"
MANUALE = SITO + "manuale.html"


def disattivata() -> bool:
    return os.path.exists(FLAG_OFF)


def imposta_avvio(mostra: bool) -> None:
    try:
        if mostra:
            if os.path.exists(FLAG_OFF):
                os.remove(FLAG_OFF)
        else:
            os.makedirs(CONF_DIR, exist_ok=True)
            with open(FLAG_OFF, "w") as f:
                f.write("1\n")
    except OSError:
        pass


def _avvia(argv) -> None:
    try:
        subprocess.Popen(argv, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass


def _apri_documento(nome: str) -> None:
    """Apre un documento di /usr/share/doc/nexussec con l'editor di testo (in
    sola lettura di fatto: e' un file di sistema)."""
    p = os.path.join(DOC_DIR, nome)
    for cmd in ("nxs-editor", "xdg-open"):
        if shutil.which(cmd):
            _avvia([cmd, p])
            return


def _testo(markup: str) -> Gtk.Label:
    lab = Gtk.Label()
    lab.set_markup(markup)
    lab.set_xalign(0)
    lab.set_line_wrap(True)
    lab.set_max_width_chars(78)
    lab.set_selectable(False)
    lab.get_style_context().add_class("nxs-val")
    return lab


def _titolo(testo: str) -> Gtk.Label:
    lab = Gtk.Label(label=testo)
    lab.set_xalign(0)
    lab.get_style_context().add_class("nxs-key")
    return lab


def _bottone(testo: str, icona: str, azione) -> Gtk.Button:
    b = Gtk.Button()
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    box.pack_start(Gtk.Image.new_from_icon_name(icona, Gtk.IconSize.BUTTON),
                   False, False, 0)
    box.pack_start(Gtk.Label(label=testo), False, False, 0)
    b.add(box)
    b.connect("clicked", lambda _w: azione())
    return b


def _pagina() -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.set_border_width(18)
    return box


def _riga_bottoni(*bottoni) -> Gtk.FlowBox:
    fb = Gtk.FlowBox()
    fb.set_selection_mode(Gtk.SelectionMode.NONE)
    fb.set_max_children_per_line(3)
    fb.set_column_spacing(8)
    fb.set_row_spacing(8)
    for b in bottoni:
        fb.add(b)
    return fb


class Benvenuto(Gtk.Window):
    def __init__(self):
        super().__init__(title=_t("wel.wtitle"))
        apply_css()
        self.set_default_size(760, 560)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_icon_name("nxs-logo")
        self.connect("destroy", Gtk.main_quit)
        self.connect("key-press-event", self._tasto)
        self._stack = None
        self._lingua = self._lingua_attiva()
        self._costruisci()
        # La lingua si puo' cambiare mentre la finestra e' aperta (anche dal suo
        # pulsante "Lingua"): si controlla ogni secondo e, se cambia, si
        # ricostruisce il contenuto restando sulla stessa scheda.
        GLib.timeout_add_seconds(1, self._controlla_lingua)

    @staticmethod
    def _lingua_attiva():
        try:
            import nxs_i18n
            nxs_i18n._active = None          # rilegge ~/.config/nxs/lang
            nxs_i18n._cache.clear()
            return nxs_i18n.current_lang()
        except Exception:                    # noqa: BLE001
            return ""

    def _controlla_lingua(self):
        ora = self._lingua_attiva()
        if ora and ora != self._lingua:
            self._lingua = ora
            pagina = self._stack.get_visible_child_name() if self._stack else None
            self._costruisci()
            if pagina:
                self._stack.set_visible_child_name(pagina)
        return True                          # continua a controllare

    def _costruisci(self):
        vecchio = self.get_child()
        if vecchio is not None:
            self.remove(vecchio)
            vecchio.destroy()
        self.set_title(_t("wel.wtitle"))
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(outer)

        # --- intestazione -------------------------------------------------
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        head.get_style_context().add_class("nxs-headerbar")
        logo = Gtk.Image.new_from_icon_name("nxs-logo", Gtk.IconSize.DIALOG)
        logo.set_pixel_size(56)
        head.pack_start(logo, False, False, 0)
        tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        t = Gtk.Label(label=_t("wel.title")); t.set_xalign(0)
        t.get_style_context().add_class("title")
        s = Gtk.Label(label=_t("wel.subtitle")); s.set_xalign(0)
        s.get_style_context().add_class("subtitle")
        tb.pack_start(t, False, False, 0)
        tb.pack_start(s, False, False, 0)
        head.pack_start(tb, True, True, 0)
        outer.pack_start(head, False, False, 0)

        # --- pagine -------------------------------------------------------
        stack = Gtk.Stack()
        self._stack = stack
        stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        stack.add_titled(self._primi_passi(), "start", _t("wel.tab.start"))
        stack.add_titled(self._licenze(), "licenses", _t("wel.tab.licenses"))
        stack.add_titled(self._uso(), "use", _t("wel.tab.use"))
        stack.add_titled(self._info(), "about", _t("wel.tab.about"))
        sw = Gtk.StackSwitcher()
        sw.set_stack(stack)
        sw.set_halign(Gtk.Align.CENTER)
        sw.set_margin_top(10)
        outer.pack_start(sw, False, False, 0)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(stack)
        outer.pack_start(scroll, True, True, 0)

        # --- piede --------------------------------------------------------
        foot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        foot.get_style_context().add_class("nxs-footer")
        self.chk = Gtk.CheckButton(label=_t("wel.show_at_start"))
        self.chk.set_active(not disattivata())
        self.chk.connect("toggled", lambda w: imposta_avvio(w.get_active()))
        foot.pack_start(self.chk, True, True, 0)
        chiudi = Gtk.Button(label=_t("wel.close"))
        chiudi.get_style_context().add_class("nxs-primary")
        chiudi.connect("clicked", lambda _w: self.destroy())
        foot.pack_end(chiudi, False, False, 0)
        outer.pack_start(foot, False, False, 0)
        outer.show_all()

    def _tasto(self, _w, ev):
        if ev.keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
        return False

    # --- pagine ------------------------------------------------------------
    def _primi_passi(self):
        p = _pagina()
        p.pack_start(_testo(_t("wel.start.intro")), False, False, 0)
        p.pack_start(_titolo(_t("wel.start.how")), False, False, 0)
        p.pack_start(_testo(_t("wel.start.points")), False, False, 0)
        p.pack_start(_riga_bottoni(
            _bottone(_t("wel.btn.profile"), "preferences-system-symbolic",
                     lambda: _avvia(["nxs-profile"])),
            _bottone(_t("wel.btn.cc"), "emblem-system-symbolic",
                     lambda: _avvia(["nxs-control-center"])),
            _bottone(_t("wel.btn.language"), "preferences-desktop-locale-symbolic",
                     lambda: _avvia(["nxs-control-center", "lingua"])),
            _bottone(_t("wel.btn.manual"), "help-browser-symbolic",
                     lambda: _avvia(["nxs-browser", MANUALE])),
        ), False, False, 0)
        return p

    def _licenze(self):
        p = _pagina()
        p.pack_start(_titolo(_t("wel.lic.own_t")), False, False, 0)
        p.pack_start(_testo(_t("wel.lic.own")), False, False, 0)
        p.pack_start(_titolo(_t("wel.lic.third_t")), False, False, 0)
        p.pack_start(_testo(_t("wel.lic.third")), False, False, 0)
        p.pack_start(_titolo(_t("wel.lic.included_t")), False, False, 0)
        p.pack_start(_testo(_t("wel.lic.included")), False, False, 0)
        p.pack_start(_riga_bottoni(
            _bottone(_t("wel.btn.license"), "text-x-generic-symbolic",
                     lambda: _apri_documento("LICENSE")),
            _bottone(_t("wel.btn.thirdparty"), "text-x-generic-symbolic",
                     lambda: _apri_documento("THIRD-PARTY.md")),
            _bottone(_t("wel.btn.commercial"), "text-x-generic-symbolic",
                     lambda: _apri_documento("COMMERCIAL.md")),
            _bottone(_t("wel.btn.trademark"), "text-x-generic-symbolic",
                     lambda: _apri_documento("TRADEMARKS.md")),
        ), False, False, 0)
        return p

    def _uso(self):
        p = _pagina()
        p.pack_start(_titolo(_t("wel.use.t")), False, False, 0)
        p.pack_start(_testo(_t("wel.use.body")), False, False, 0)
        p.pack_start(_titolo(_t("wel.warranty.t")), False, False, 0)
        p.pack_start(_testo(_t("wel.warranty.body")), False, False, 0)
        return p

    def _info(self):
        p = _pagina()
        p.pack_start(_testo(_t("wel.about.body")), False, False, 0)
        p.pack_start(_riga_bottoni(
            _bottone(_t("wel.btn.site"), "web-browser-symbolic",
                     lambda: _avvia(["nxs-browser", SITO])),
            _bottone(_t("wel.btn.manual"), "help-browser-symbolic",
                     lambda: _avvia(["nxs-browser", MANUALE])),
        ), False, False, 0)
        return p


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--auto" in argv and disattivata():
        return 0
    w = Benvenuto()
    w.show_all()
    w.present()
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
