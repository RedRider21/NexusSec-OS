# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""Funzioni "da Firefox" della finestra del browser (ereditate da Browser).

Scorciatoie da tastiera, riapri scheda chiusa, stampa / salva come PDF, salva
pagina, sorgente della pagina, silenzia scheda, riordino delle schede
trascinandole, ripristino della sessione, menu contestuale della pagina,
aggancio di cronologia / traduzione / sicurezza agli eventi delle schede.
"""
import json
import os
import re
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, Gdk, Gio, GLib, WebKit2  # noqa: E402

from nxs_browser.config import config
from nxs_browser import security

try:
    from nxs_i18n import t as _t
except Exception:                # noqa: BLE001
    def _t(key, **kw):
        return key

SESSIONE = Path.home() / ".nxs-browser" / "session.json"
MAX_CHIUSE = 25
_TAB_TARGET = [Gtk.TargetEntry.new("nxs-tab", Gtk.TargetFlags.SAME_APP, 0)]


class FunzioniExtra:
    # ------------------------------------------------------------ scorciatoie
    def _scorciatoie(self, accel):
        C = Gdk.ModifierType.CONTROL_MASK
        S = Gdk.ModifierType.SHIFT_MASK
        A = Gdk.ModifierType.MOD1_MASK

        def k(tasto, mod, azione):
            accel.connect(tasto, mod, Gtk.AccelFlags.VISIBLE,
                          lambda *_: (azione(), True)[1])
        k(Gdk.KEY_t, C, lambda: self.new_tab())
        k(Gdk.KEY_w, C, lambda: self.close_tab(self.current_view()))
        k(Gdk.KEY_F4, C, lambda: self.close_tab(self.current_view()))
        k(Gdk.KEY_t, C | S, self.riapri_chiusa)
        k(Gdk.KEY_T, C | S, self.riapri_chiusa)
        k(Gdk.KEY_l, C, self._focus_url)
        k(Gdk.KEY_F6, 0, self._focus_url)
        k(Gdk.KEY_r, C, self.refresh)
        k(Gdk.KEY_F5, 0, self.refresh)
        k(Gdk.KEY_r, C | S, self._ricarica_forzata)
        k(Gdk.KEY_R, C | S, self._ricarica_forzata)
        k(Gdk.KEY_Left, A, self.navigate_back)
        k(Gdk.KEY_Right, A, self.navigate_forward)
        k(Gdk.KEY_Home, A, self.navigate_home)
        k(Gdk.KEY_Tab, C, lambda: self._scheda_vicina(+1))
        k(Gdk.KEY_ISO_Left_Tab, C | S, lambda: self._scheda_vicina(-1))
        k(Gdk.KEY_Page_Down, C, lambda: self._scheda_vicina(+1))
        k(Gdk.KEY_Page_Up, C, lambda: self._scheda_vicina(-1))
        for t in (Gdk.KEY_plus, Gdk.KEY_equal, Gdk.KEY_KP_Add):
            k(t, C, self.zoom_in)
        for t in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
            k(t, C, self.zoom_out)
        k(Gdk.KEY_0, C, self.reset_zoom)
        k(Gdk.KEY_d, C, self.add_bookmark)
        k(Gdk.KEY_f, C, self.trova.apri)
        k(Gdk.KEY_F3, 0, self.trova.successivo)
        k(Gdk.KEY_F3, S, self.trova.precedente)
        k(Gdk.KEY_h, C, self.apri_cronologia)
        k(Gdk.KEY_j, C, self.downloads.mostra)
        k(Gdk.KEY_p, C, self.stampa)
        k(Gdk.KEY_s, C, self.salva_pagina)
        k(Gdk.KEY_u, C, self.sorgente)

    def _focus_url(self):
        self.url_bar.grab_focus()
        self.url_bar.select_region(0, -1)

    def _ricarica_forzata(self):
        v = self.current_view()
        if v:
            v.reload_bypass_cache()

    def _scheda_vicina(self, passo):
        figli = self.tab_box.get_children()
        if not figli:
            return
        cur = self._tabs.get(self.current_view())
        i = figli.index(cur) if cur in figli else 0
        ev = figli[(i + passo) % len(figli)]
        for v, e in self._tabs.items():
            if e is ev:
                self._set_active_tab(v)
                return

    # ----------------------------------------------------- aggancio schede
    def _aggancia_scheda(self, view, stealth):
        security.blocca_popup(view)
        self.solo_https.aggancia(view)
        self.antitrack.applica(view)
        view.connect("load-changed", self._caricamento)
        view.connect("notify::is-playing-audio", self._audio)
        view.connect("context-menu", self._menu_contestuale)

    def _caricamento(self, view, evento):
        if evento == WebKit2.LoadEvent.COMMITTED:
            self._aggiorna_lucchetto(view)
        elif evento == WebKit2.LoadEvent.FINISHED:
            self._aggiorna_lucchetto(view)
            if not self._view_mode.get(view):          # anonima: niente cronologia
                self.cronologia.registra(view.get_uri() or "", view.get_title() or "")
            self.traduttore.pagina_caricata(view)
            self._salva_sessione()

    def _aggiorna_lucchetto(self, view):
        if view is not self.current_view():
            return
        try:
            self.url_bar.set_icon_from_icon_name(
                Gtk.EntryIconPosition.PRIMARY, security.icona(view))
            self.url_bar.set_icon_tooltip_text(
                Gtk.EntryIconPosition.PRIMARY, _t("br.site.tip"))
        except Exception:            # noqa: BLE001
            pass

    def _lucchetto_premuto(self, _entry, pos, _ev):
        if pos == Gtk.EntryIconPosition.PRIMARY:
            security.info_sito(self, self.url_bar)

    def _scheda_attivata(self, view):
        """Da _set_active_tab: allinea lucchetto, traduzione e ricerca."""
        self._aggiorna_lucchetto(view)
        self.traduttore.aggiorna(view)
        self.trova.scheda_cambiata()

    # ----------------------------------------------------------- audio
    def _pulsante_audio(self, view):
        b = Gtk.Button()
        b.set_relief(Gtk.ReliefStyle.NONE)
        b.set_image(Gtk.Image.new_from_icon_name("audio-volume-high-symbolic",
                                                 Gtk.IconSize.MENU))
        b.set_tooltip_text(_t("br.mute"))
        b.set_no_show_all(True)
        b.connect("clicked", lambda _w: self._silenzia(view))
        return b

    def _audio(self, view, _p=None):
        b = getattr(view, "_nxs_audio", None)
        if b is None:
            return
        muto = view.get_is_muted()
        if view.is_playing_audio() or muto:
            b.set_image(Gtk.Image.new_from_icon_name(
                "audio-volume-muted-symbolic" if muto else "audio-volume-high-symbolic",
                Gtk.IconSize.MENU))
            b.set_tooltip_text(_t("br.unmute") if muto else _t("br.mute"))
            b.show()
        else:
            b.hide()

    def _silenzia(self, view):
        view.set_is_muted(not view.get_is_muted())
        self._audio(view)

    # --------------------------------------------------- riordino schede
    def _trascinabile(self, ev, view):
        ev.drag_source_set(Gdk.ModifierType.BUTTON1_MASK, _TAB_TARGET, Gdk.DragAction.MOVE)
        ev.drag_dest_set(Gtk.DestDefaults.ALL, _TAB_TARGET, Gdk.DragAction.MOVE)
        ev.connect("drag-data-get", lambda _w, _c, data, _i, _t2:
                   data.set(data.get_target(), 8, str(id(view)).encode()))
        ev.connect("drag-data-received", self._scheda_rilasciata)

    def _scheda_rilasciata(self, dest, _ctx, _x, _y, data, _info, _tempo):
        try:
            ident = int(bytes(data.get_data()).decode())
        except (ValueError, TypeError):
            return
        for v, e in self._tabs.items():
            if id(v) == ident and e is not dest:
                figli = self.tab_box.get_children()
                self.tab_box.reorder_child(e, figli.index(dest))
                self._salva_sessione()
                return

    # ---------------------------------------------- schede chiuse, sessione
    def _ricorda_chiusa(self, view):
        uri = view.get_uri() or ""
        if uri and not uri.startswith("about:"):
            if not hasattr(self, "_chiuse"):
                self._chiuse = []
            self._chiuse.append((uri, bool(self._view_mode.get(view))))
            del self._chiuse[:-MAX_CHIUSE]

    def riapri_chiusa(self):
        if getattr(self, "_chiuse", None):
            uri, anon = self._chiuse.pop()
            self.new_tab(uri, stealth=anon)

    def _salva_sessione(self):
        """Solo schede NORMALI e solo se il ripristino e' attivo: quelle
        anonime non lasciano tracce, neanche qui."""
        if not config.get("restore_session", False):
            return
        uris = []
        for ev in self.tab_box.get_children():
            for v, e in self._tabs.items():
                if e is ev and not self._view_mode.get(v):
                    u = v.get_uri() or ""
                    if u and not u.startswith(("about:", "data:")):
                        uris.append(u)
        try:
            SESSIONE.write_text(json.dumps(uris))
        except OSError:
            pass

    def schede_da_ripristinare(self):
        if not config.get("restore_session", False):
            return []
        try:
            return [u for u in json.loads(SESSIONE.read_text()) if isinstance(u, str)]
        except (OSError, ValueError):
            return []

    # ------------------------------------------------ stampa, salva, sorgente
    def stampa(self):
        v = self.current_view()
        if v:
            WebKit2.PrintOperation.new(v).run_dialog(self)

    def salva_pagina(self):
        v = self.current_view()
        if v is None:
            return
        from nxs_browser.downloads import cartella_download
        dlg = Gtk.FileChooserDialog(title=_t("br.save_page"), transient_for=self,
                                    action=Gtk.FileChooserAction.SAVE)
        dlg.add_buttons(_t("v.cancel"), Gtk.ResponseType.CANCEL,
                        _t("br.dl.save"), Gtk.ResponseType.ACCEPT)
        dlg.set_do_overwrite_confirmation(True)
        try:
            dlg.set_current_folder(cartella_download())
        except Exception:            # noqa: BLE001
            pass
        nome = re.sub(r'[\\/:*?"<>|]+', " ", v.get_title() or "pagina").strip()[:80]
        dlg.set_current_name((nome or "pagina") + ".mhtml")
        r = dlg.run()
        dest = dlg.get_filename() if r == Gtk.ResponseType.ACCEPT else None
        dlg.destroy()
        if not dest:
            return

        def fatto(view, res):
            try:
                view.save_to_file_finish(res)
                self._notify(_t("br.dl.done"), _t("br.dl.done_body") % (
                    os.path.basename(dest), os.path.dirname(dest)), "document-save")
            except Exception as e:   # noqa: BLE001
                self._notify(_t("br.dl.failed"), str(e), "dialog-error")
        v.save_to_file(Gio.File.new_for_path(dest), WebKit2.SaveMode.MHTML, None, fatto)

    def sorgente(self):
        v = self.current_view()
        if v is None or v.get_main_resource() is None:
            return
        uri = v.get_uri() or ""
        anon = bool(self._view_mode.get(v))

        def dati(res_obj, res):
            try:
                b = res_obj.get_data_finish(res)
            except Exception:        # noqa: BLE001
                return
            nuova = self.new_tab(None, stealth=anon)
            nuova.load_bytes(GLib.Bytes.new(b), "text/plain", "utf-8", None)
            voce = self._tab_labels.get(nuova)
            if voce:
                voce[2].set_text(_t("br.source_of") % (uri.split("//")[-1][:30]))
        v.get_main_resource().get_data(None, dati)

    def apri_cronologia(self):
        from nxs_browser.history import apri_finestra
        apri_finestra(self, self.cronologia)

    # ------------------------------------------------ menu contestuale pagina
    def _azione(self, nome, cb):
        a = Gio.SimpleAction.new(nome, None)
        a.connect("activate", lambda *_: cb())
        return a

    def _menu_contestuale(self, view, menu, _ev, hit):
        """Menu del tasto destro della pagina: le voci di WebKit (tradotte dai
        pacchetti -lang) piu' le nostre, come Firefox/Chrome."""
        menu.append(WebKit2.ContextMenuItem.new_separator())
        if hit.context_is_link():
            link = hit.get_link_uri()
            menu.append(WebKit2.ContextMenuItem.new_from_gaction(
                self._azione("nxs-link-anon", lambda: self.new_tab(link, stealth=True)),
                _t("br.ctx.link_anon"), None))
        if not hit.context_is_editable():
            menu.append(WebKit2.ContextMenuItem.new_from_gaction(
                self._azione("nxs-tr", lambda: self.traduttore.traduci(view)),
                _t("br.ctx.translate"), None))
            menu.append(WebKit2.ContextMenuItem.new_from_gaction(
                self._azione("nxs-save", self.salva_pagina), _t("br.save_page"), None))
            menu.append(WebKit2.ContextMenuItem.new_from_gaction(
                self._azione("nxs-print", self.stampa), _t("br.print"), None))
            menu.append(WebKit2.ContextMenuItem.new_from_gaction(
                self._azione("nxs-src", self.sorgente), _t("br.source"), None))
        return False
