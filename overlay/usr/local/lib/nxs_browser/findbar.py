# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""Trova nella pagina (Ctrl+F), come la barra di ricerca di Firefox.

Barra in fondo alla finestra: campo di ricerca, precedente/successivo
(anche Invio / Maiusc+Invio, F3 / Maiusc+F3), "Maiuscole/minuscole",
numero di risultati; Esc la chiude. Usa il FindController di WebKit della
scheda attiva: cambiando scheda la ricerca riparte su quella nuova.
"""
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, Gdk, WebKit2  # noqa: E402

try:
    from nxs_i18n import t as _t
except Exception:                # noqa: BLE001
    def _t(key, **kw):
        return key

MAX_RISULTATI = 1000


class BarraTrova(Gtk.Revealer):
    def __init__(self, browser):
        super().__init__()
        self.browser = browser
        self._fc = None                    # FindController agganciato
        self._handler = []
        self.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)
        barra = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        barra.get_style_context().add_class("nxs-findbar")
        self.campo = Gtk.SearchEntry()
        self.campo.set_placeholder_text(_t("br.find.ph"))
        self.campo.set_width_chars(28)
        self.campo.connect("search-changed", lambda _e: self.cerca())
        self.campo.connect("activate", lambda _e: self.successivo())
        self.campo.connect("key-press-event", self._tasto)
        barra.pack_start(self.campo, False, False, 0)
        for icona, tip, cb in (("go-up-symbolic", _t("br.find.prev"), self.precedente),
                               ("go-down-symbolic", _t("br.find.next"), self.successivo)):
            b = Gtk.Button()
            b.add(Gtk.Image.new_from_icon_name(icona, Gtk.IconSize.MENU))
            b.set_relief(Gtk.ReliefStyle.NONE)
            b.set_tooltip_text(tip)
            b.get_style_context().add_class("nxs-nav-btn")
            b.connect("clicked", lambda _w, c=cb: c())
            barra.pack_start(b, False, False, 0)
        self.maiusc = Gtk.CheckButton(label=_t("br.find.case"))
        self.maiusc.connect("toggled", lambda _w: self.cerca())
        barra.pack_start(self.maiusc, False, False, 6)
        self.esito = Gtk.Label()
        self.esito.get_style_context().add_class("nxs-find-info")
        barra.pack_start(self.esito, False, False, 6)
        chiudi = Gtk.Button()
        chiudi.add(Gtk.Image.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU))
        chiudi.set_relief(Gtk.ReliefStyle.NONE)
        chiudi.set_tooltip_text(_t("br.find.close"))
        chiudi.get_style_context().add_class("nxs-nav-btn")
        chiudi.connect("clicked", lambda _w: self.chiudi())
        barra.pack_end(chiudi, False, False, 0)
        self.add(barra)

    # --- apertura/chiusura -----------------------------------------------------
    def apri(self):
        self.set_reveal_child(True)
        self.campo.grab_focus()
        self.campo.select_region(0, -1)
        if self.campo.get_text():
            self.cerca()

    def chiudi(self):
        if self._fc is not None:
            self._fc.search_finish()
        self.set_reveal_child(False)
        v = self.browser.current_view()
        if v is not None:
            v.grab_focus()

    def aperta(self):
        return self.get_reveal_child()

    def _tasto(self, _w, ev):
        if ev.keyval == Gdk.KEY_Escape:
            self.chiudi()
            return True
        if ev.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and \
                ev.state & Gdk.ModifierType.SHIFT_MASK:
            self.precedente()
            return True
        return False

    # --- ricerca ------------------------------------------------------------------------
    def _controller(self):
        v = self.browser.current_view()
        if v is None:
            return None
        fc = v.get_find_controller()
        if fc is not self._fc:
            if self._fc is not None:
                for h in self._handler:
                    try:
                        self._fc.disconnect(h)
                    except Exception:    # noqa: BLE001
                        pass
                self._fc.search_finish()
            self._fc = fc
            self._handler = [
                fc.connect("counted-matches", self._contati),
                fc.connect("failed-to-find-text", self._non_trovato),
            ]
        return fc

    def _opzioni(self):
        o = WebKit2.FindOptions.WRAP_AROUND
        if not self.maiusc.get_active():
            o |= WebKit2.FindOptions.CASE_INSENSITIVE
        return o

    def cerca(self):
        fc = self._controller()
        testo = self.campo.get_text()
        if fc is None:
            return
        if not testo:
            fc.search_finish()
            self.esito.set_text("")
            self.campo.get_style_context().remove_class("nxs-find-none")
            return
        self.campo.get_style_context().remove_class("nxs-find-none")
        fc.count_matches(testo, self._opzioni(), MAX_RISULTATI)
        fc.search(testo, self._opzioni(), MAX_RISULTATI)

    def successivo(self):
        fc = self._controller()
        if fc is not None and self.campo.get_text():
            if fc.get_search_text() != self.campo.get_text():
                self.cerca()
            else:
                fc.search_next()

    def precedente(self):
        fc = self._controller()
        if fc is not None and self.campo.get_text():
            if fc.get_search_text() != self.campo.get_text():
                self.cerca()
            else:
                fc.search_previous()

    def _contati(self, _fc, n):
        if n == 0:
            self._non_trovato(_fc)
            return
        self.campo.get_style_context().remove_class("nxs-find-none")
        self.esito.set_text((_t("br.find.one") if n == 1 else _t("br.find.many") % n)
                            if n < MAX_RISULTATI else _t("br.find.lots") % MAX_RISULTATI)

    def _non_trovato(self, _fc):
        self.esito.set_text(_t("br.find.none"))
        self.campo.get_style_context().add_class("nxs-find-none")

    def scheda_cambiata(self):
        """Nuova scheda attiva: se la barra e' aperta, cerca anche li'."""
        if self.aperta() and self.campo.get_text():
            self.cerca()
