# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""Download di NexusSec Browser: destinazione, avanzamento, pannello.

Come in Firefox:
  - il pulsante Download compare nella barra al primo download e, mentre si
    scarica, mostra la percentuale complessiva;
  - all'avvio di un download il pannello si apre da solo: per ogni file nome,
    barra di avanzamento, "3,2 MB di 10 MB - 1,2 MB/s", Annulla durante,
    Apri / Mostra nella cartella a fine;
  - la destinazione segue le Impostazioni: cartella scelta (predefinita la
    cartella Download dell'utente) oppure "chiedi ogni volta dove salvare".

API WebKit2GTK 4.1: set_destination() vuole un URI (in 6.0 e' un percorso).
"""
import os
import subprocess
import time
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, GLib, Gio, WebKit2  # noqa: E402

from nxs_browser.config import config

try:
    from nxs_i18n import t as _t
except Exception:                # noqa: BLE001
    def _t(key, **kw):
        return key


def cartella_predefinita() -> str:
    """Cartella Download dell'utente (XDG), con ripiego su ~/Downloads."""
    d = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
    return d or str(Path.home() / "Downloads")


def cartella_download() -> str:
    d = (config.get("download_dir", "") or "").strip()
    return os.path.expanduser(d) if d else cartella_predefinita()


def _peso(n) -> str:
    """Byte in forma leggibile, con la virgola decimale all'italiana/europea."""
    n = float(n or 0)
    for unita in ("B", "KB", "MB", "GB"):
        if n < 1024 or unita == "GB":
            s = ("%d %s" % (n, unita)) if unita == "B" else ("%.1f %s" % (n, unita))
            return s.replace(".", ",")
        n /= 1024.0
    return "%d B" % n


def _unico(cartella: str, nome: str) -> str:
    """Percorso libero: "file.zip" -> "file (1).zip" se esiste gia'."""
    nome = os.path.basename(nome or "") or "download"
    p = os.path.join(cartella, nome)
    if not os.path.exists(p):
        return p
    base, ext = os.path.splitext(nome)
    if base.endswith(".tar"):                         # file.tar.gz
        base, ext = base[:-4], ".tar" + ext
    i = 1
    while True:
        p = os.path.join(cartella, "%s (%d)%s" % (base, i, ext))
        if not os.path.exists(p):
            return p
        i += 1


def _apri(percorso: str) -> None:
    try:
        Gio.AppInfo.launch_default_for_uri(GLib.filename_to_uri(percorso, None), None)
        return
    except Exception:            # noqa: BLE001
        pass
    for cmd in ("xdg-open", "pcmanfm"):
        try:
            subprocess.Popen([cmd, percorso], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
            return
        except OSError:
            continue


class _Voce:
    """Un download nel pannello (riga + stato)."""

    def __init__(self, gestore, download):
        self.g = gestore
        self.d = download
        self.percorso = ""
        self.stato = "attivo"          # attivo | fatto | errore | annullato
        self.t0 = time.monotonic()
        self._camp = (self.t0, 0)      # (istante, byte) per la velocita'
        self.velocita = 0.0

        self.riga = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.riga.get_style_context().add_class("nxs-dl-row")
        testa = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.icona = Gtk.Image.new_from_icon_name("folder-download-symbolic",
                                                  Gtk.IconSize.LARGE_TOOLBAR)
        testa.pack_start(self.icona, False, False, 0)
        testi = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        self.nome = Gtk.Label(label="…")
        self.nome.set_xalign(0)
        self.nome.set_ellipsize(3)                      # Pango.EllipsizeMode.END
        self.nome.set_max_width_chars(34)
        self.nome.get_style_context().add_class("nxs-dl-name")
        self.info = Gtk.Label(label=_t("br.dl.starting"))
        self.info.set_xalign(0)
        self.info.get_style_context().add_class("nxs-dl-info")
        testi.pack_start(self.nome, False, False, 0)
        testi.pack_start(self.info, False, False, 0)
        testa.pack_start(testi, True, True, 0)
        self.azioni = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        testa.pack_end(self.azioni, False, False, 0)
        self.riga.pack_start(testa, False, False, 0)
        self.barra = Gtk.ProgressBar()
        self.barra.get_style_context().add_class("nxs-dl-bar")
        self.riga.pack_start(self.barra, False, False, 0)
        self._azioni_attive()

        download.connect("decide-destination", self._decidi)
        download.connect("created-destination", self._creata)
        download.connect("finished", self._finito)
        download.connect("failed", self._fallito)

    # --- pulsanti -----------------------------------------------------------
    def _bottone(self, icona, tip, cb):
        b = Gtk.Button()
        b.add(Gtk.Image.new_from_icon_name(icona, Gtk.IconSize.MENU))
        b.set_relief(Gtk.ReliefStyle.NONE)
        b.set_tooltip_text(tip)
        b.get_style_context().add_class("nxs-dl-act")
        b.connect("clicked", lambda _w: cb())
        return b

    def _svuota_azioni(self):
        for c in self.azioni.get_children():
            self.azioni.remove(c)

    def _azioni_attive(self):
        self._svuota_azioni()
        self.azioni.pack_start(self._bottone("process-stop-symbolic",
                                             _t("br.dl.cancel"), self.d.cancel),
                               False, False, 0)
        self.azioni.show_all()

    def _azioni_finali(self):
        self._svuota_azioni()
        if self.stato == "fatto" and self.percorso:
            apri = Gtk.Button(label=_t("br.dl.open"))
            apri.set_relief(Gtk.ReliefStyle.NONE)
            apri.get_style_context().add_class("nxs-dl-act")
            apri.connect("clicked", lambda _w: _apri(self.percorso))
            self.azioni.pack_start(apri, False, False, 0)
            self.azioni.pack_start(self._bottone(
                "folder-open-symbolic", _t("br.dl.show_folder"),
                lambda: _apri(os.path.dirname(self.percorso))), False, False, 0)
        self.azioni.pack_start(self._bottone(
            "edit-clear-symbolic", _t("br.dl.remove_row"),
            lambda: self.g.togli(self)), False, False, 0)
        self.azioni.show_all()

    # --- destinazione ----------------------------------------------------------
    def _decidi(self, download, suggerito):
        cartella = cartella_download()
        if config.get("download_ask", False):
            dlg = Gtk.FileChooserDialog(
                title=_t("br.dl.save_as"), transient_for=self.g.finestra,
                action=Gtk.FileChooserAction.SAVE)
            dlg.add_buttons(_t("v.cancel"), Gtk.ResponseType.CANCEL,
                            _t("br.dl.save"), Gtk.ResponseType.ACCEPT)
            dlg.set_do_overwrite_confirmation(True)
            try:
                dlg.set_current_folder(cartella)
            except Exception:        # noqa: BLE001
                pass
            dlg.set_current_name(os.path.basename(suggerito or "") or "download")
            r = dlg.run()
            dest = dlg.get_filename() if r == Gtk.ResponseType.ACCEPT else None
            dlg.destroy()
            if not dest:
                self.stato = "annullato"
                download.cancel()
                return True
            download.set_allow_overwrite(True)       # confermato nel dialogo
        else:
            try:
                os.makedirs(cartella, exist_ok=True)
            except OSError:
                cartella = cartella_predefinita()
                os.makedirs(cartella, exist_ok=True)
            dest = _unico(cartella, suggerito)
        self.percorso = dest
        self.nome.set_text(os.path.basename(dest))
        download.set_destination(GLib.filename_to_uri(dest, None))
        return True

    def _creata(self, _download, uri):
        try:
            self.percorso = GLib.filename_from_uri(uri)[0]
            self.nome.set_text(os.path.basename(self.percorso))
        except Exception:            # noqa: BLE001
            pass

    # --- avanzamento ---------------------------------------------------------------
    def totale(self):
        try:
            r = self.d.get_response()
            return r.get_content_length() if r else 0
        except Exception:            # noqa: BLE001
            return 0

    def ricevuti(self):
        try:
            return self.d.get_received_data_length()
        except Exception:            # noqa: BLE001
            return 0

    def aggiorna(self):
        if self.stato != "attivo":
            return
        ora, got = time.monotonic(), self.ricevuti()
        t_prec, b_prec = self._camp
        if ora - t_prec >= 0.9:
            inst = (got - b_prec) / (ora - t_prec)
            # media mobile: la velocita' non "balla" a ogni aggiornamento
            self.velocita = inst if not self.velocita else (0.6 * self.velocita + 0.4 * inst)
            self._camp = (ora, got)
        tot = self.totale()
        if tot > 0:
            self.barra.set_fraction(min(1.0, got / float(tot)))
            testo = _t("br.dl.progress") % (_peso(got), _peso(tot))
        else:
            self.barra.pulse()
            testo = _peso(got)
        if self.velocita > 0:
            testo += "  ·  %s/s" % _peso(self.velocita)
            if tot > 0 and got < tot:
                resto = int((tot - got) / self.velocita)
                testo += "  ·  " + (_t("br.dl.eta") % self._durata(resto))
        self.info.set_text(testo)

    @staticmethod
    def _durata(s):
        if s < 60:
            return "%d s" % s
        if s < 3600:
            return "%d min" % ((s + 30) // 60)
        return "%d h %02d min" % (s // 3600, (s % 3600) // 60)

    # --- fine -----------------------------------------------------------------------
    def _finito(self, _download):
        if self.stato != "attivo":           # "finished" arriva anche dopo failed
            self.g.cambiato()
            return
        self.stato = "fatto"
        self.barra.set_fraction(1.0)
        self.barra.hide()
        self.icona.set_from_icon_name("emblem-ok-symbolic", Gtk.IconSize.LARGE_TOOLBAR)
        self.info.set_text(_t("br.dl.done_short") % _peso(self.ricevuti()))
        self._azioni_finali()
        self.g.notifica(_t("br.dl.done"),
                        _t("br.dl.done_body") % (os.path.basename(self.percorso),
                                                 os.path.dirname(self.percorso)),
                        "folder-download")
        self.g.cambiato()

    def _fallito(self, _download, errore):
        annullato = False
        try:
            annullato = errore.matches(WebKit2.DownloadError.quark(),
                                       WebKit2.DownloadError.CANCELLED_BY_USER)
        except Exception:            # noqa: BLE001
            pass
        self.stato = "annullato" if (annullato or self.stato == "annullato") else "errore"
        if self.stato == "annullato" and not self.percorso:
            self.g.togli(self)                 # annullato gia' nel dialogo "Salva"
            return
        self.barra.hide()
        self.icona.set_from_icon_name(
            "process-stop-symbolic" if self.stato == "annullato" else "dialog-error-symbolic",
            Gtk.IconSize.LARGE_TOOLBAR)
        self.info.set_text(_t("br.dl.cancelled") if self.stato == "annullato"
                           else str(getattr(errore, "message", errore)))
        if self.stato == "errore":
            self.g.notifica(_t("br.dl.failed"), str(getattr(errore, "message", errore)),
                            "dialog-error")
        # un file lasciato a meta' non serve a nessuno
        if self.percorso and os.path.isfile(self.percorso):
            try:
                os.remove(self.percorso)
            except OSError:
                pass
        self._azioni_finali()
        self.g.cambiato()


class GestoreDownload:
    """Pulsante nella barra + pannello a comparsa con l'elenco dei download."""

    def __init__(self, finestra, notifica):
        self.finestra = finestra
        self.notifica = notifica
        self.voci = []
        self._timer = None

        self.pulsante = Gtk.Button()
        self.pulsante.set_relief(Gtk.ReliefStyle.NONE)
        self.pulsante.set_tooltip_text(_t("br.dl.title"))
        self.pulsante.get_style_context().add_class("nxs-nav-btn")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        box.pack_start(Gtk.Image.new_from_icon_name("folder-download-symbolic",
                                                    Gtk.IconSize.BUTTON), False, False, 0)
        self.etichetta = Gtk.Label()
        self.etichetta.get_style_context().add_class("nxs-dl-badge")
        box.pack_start(self.etichetta, False, False, 0)
        self.pulsante.add(box)
        self.pulsante.connect("clicked", lambda _w: self.mostra())
        self.pulsante.set_no_show_all(True)          # compare al primo download

        self.pop = Gtk.Popover.new(self.pulsante)
        self.pop.get_style_context().add_class("nxs-dl-pop")
        corpo = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        corpo.set_border_width(10)
        titolo = Gtk.Label(label=_t("br.dl.title"))
        titolo.set_xalign(0)
        titolo.get_style_context().add_class("nxs-dl-title")
        corpo.pack_start(titolo, False, False, 0)
        sc = Gtk.ScrolledWindow()
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc.set_propagate_natural_height(True)
        sc.set_max_content_height(360)
        sc.set_min_content_width(380)
        self.lista = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        sc.add(self.lista)
        corpo.pack_start(sc, True, True, 0)
        piede = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        b_cart = Gtk.Button(label=_t("br.dl.open_folder"))
        b_cart.connect("clicked", lambda _w: _apri(cartella_download()))
        b_pul = Gtk.Button(label=_t("br.dl.clear"))
        b_pul.connect("clicked", lambda _w: self.pulisci())
        piede.pack_start(b_cart, False, False, 0)
        piede.pack_end(b_pul, False, False, 0)
        corpo.pack_start(piede, False, False, 0)
        corpo.show_all()
        self.pop.add(corpo)

    # chiamato dal contesto WebKit
    def nuovo(self, download):
        v = _Voce(self, download)
        self.voci.insert(0, v)
        self.lista.pack_start(v.riga, False, False, 0)
        self.lista.reorder_child(v.riga, 0)
        v.riga.show_all()
        self.pulsante.set_no_show_all(False)
        self.pulsante.show_all()
        if self._timer is None:
            self._timer = GLib.timeout_add(500, self._tick)
        self.cambiato()
        # come Firefox: il pannello si apre da solo quando parte un download
        GLib.idle_add(lambda: (self.mostra(), False)[1])

    def mostra(self):
        if self.voci:
            self.pop.popup()

    def togli(self, voce):
        if voce in self.voci:
            self.voci.remove(voce)
            self.lista.remove(voce.riga)
        self.cambiato()

    def pulisci(self):
        for v in [v for v in self.voci if v.stato != "attivo"]:
            self.togli(v)
        if not self.voci:
            self.pop.popdown()

    def _tick(self):
        for v in self.voci:
            v.aggiorna()
        self.cambiato()
        if not any(v.stato == "attivo" for v in self.voci):
            self._timer = None
            return False
        return True

    def cambiato(self):
        attivi = [v for v in self.voci if v.stato == "attivo"]
        if not attivi:
            self.etichetta.set_text("")
            self.etichetta.hide()
            return
        tot = sum(v.totale() for v in attivi)
        got = sum(v.ricevuti() for v in attivi)
        if tot > 0:
            self.etichetta.set_text("%d%%" % int(100 * got / tot))
        else:
            self.etichetta.set_text(_peso(got))
        self.etichetta.show()
