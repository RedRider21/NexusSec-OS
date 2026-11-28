# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""Installatore grafico di NexusSec (2026-11-22).

Procedura guidata in 5 schermate sopra `nxs-install-disco` (che fa il lavoro
vero ed e' collaudato da build-alpine/collaudo-iso.py --solo disco):

  1. benvenuto: cosa succede; controllo che la chiavetta sia una fast-boot
  2. disco: solo i dischi installabili (mai quello di avvio o quelli in uso)
  3. passphrase dei dati (due volte, almeno 8 caratteri)
  4. riepilogo + conferma esplicita della cancellazione
  5. avanzamento (righe "PASSO n/7") con il registro dettagliato; esito

La passphrase passa all'installatore in un file temporaneo leggibile solo
dall'utente, cancellato appena finisce. Tutto l'output va anche in
/tmp/nxs-install-disco.log.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib  # noqa: E402

from nxs_cc.common import panel_window, icon_button  # noqa: E402

try:
    from nxs_i18n import t as _t
except ImportError:                     # pragma: no cover
    def _t(k, **kw):
        return k

INSTALL = "nxs-install-disco"
LOG = "/tmp/nxs-install-disco.log"
PASSI = 7


def _titolo(testo):
    return _lbl("<span size='large' weight='bold'>%s</span>"
                % GLib.markup_escape_text(testo), markup=True)


def _lbl(testo, classe=None, wrap=True, markup=False):
    lab = Gtk.Label()
    if markup:
        lab.set_markup(testo)
    else:
        lab.set_text(testo)
    lab.set_xalign(0)
    lab.set_line_wrap(wrap)
    if classe:
        lab.get_style_context().add_class(classe)
    return lab


class Installatore:
    def __init__(self):
        self.win, body = panel_window(_t("inst.title"), 680, 560)
        self.win.connect("destroy", self._esci)
        self.disco = None
        self.dischi = []
        self.proc = None
        self.passfile = None
        self.userfile = None
        self.lavora = False

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        body.pack_start(self.stack, True, True, 0)

        nav = Gtk.Box(spacing=8)
        self.b_indietro = icon_button(_t("inst.back"), "go-previous")
        self.b_avanti = icon_button(_t("inst.next"), "go-next", primary=True)
        self.b_indietro.connect("clicked", lambda *_: self._vai(-1))
        self.b_avanti.connect("clicked", lambda *_: self._vai(+1))
        nav.pack_end(self.b_avanti, False, False, 0)
        nav.pack_end(self.b_indietro, False, False, 0)
        body.pack_end(nav, False, False, 0)

        self.pagine = ["benvenuto", "disco", "pass", "utente", "riepilogo", "lavoro"]
        self._p_benvenuto()
        self._p_disco()
        self._p_pass()
        self._p_utente()
        self._p_riepilogo()
        self._p_lavoro()
        self.i = 0
        self._mostra()
        self.win.show_all()
        self._mostra()
        threading.Thread(target=self._controlla, daemon=True).start()

    # ------------------------------------------------------------ pagine
    def _p_benvenuto(self):
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        b.pack_start(_titolo(_t("inst.welcome_h")), False, False, 0)
        b.pack_start(_lbl(_t("inst.welcome_body")), False, False, 0)
        for k in ("inst.pt_sys", "inst.pt_data", "inst.pt_offline", "inst.pt_erase"):
            b.pack_start(_lbl("•  " + _t(k)), False, False, 0)
        self.stato_media = _lbl(_t("inst.checking"))
        b.pack_start(self.stato_media, False, False, 8)
        self.stack.add_named(b, "benvenuto")

    def _p_disco(self):
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        b.pack_start(_titolo(_t("inst.disk_h")), False, False, 0)
        b.pack_start(_lbl(_t("inst.disk_body")), False, False, 0)
        self.box_dischi = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        b.pack_start(self.box_dischi, False, False, 0)
        agg = icon_button(_t("inst.refresh"), "view-refresh")
        agg.connect("clicked", lambda *_: self._carica_dischi())
        r = Gtk.Box()
        r.pack_start(agg, False, False, 0)
        b.pack_start(r, False, False, 0)
        self.stack.add_named(b, "disco")

    def _p_pass(self):
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        b.pack_start(_titolo(_t("inst.pass_h")), False, False, 0)
        b.pack_start(_lbl(_t("inst.pass_body")), False, False, 0)
        g = Gtk.Grid(column_spacing=10, row_spacing=8)
        self.e1, self.e2 = Gtk.Entry(), Gtk.Entry()
        for n, (e, k) in enumerate(((self.e1, "inst.pass1"), (self.e2, "inst.pass2"))):
            e.set_visibility(False)
            e.set_hexpand(True)
            e.connect("changed", lambda *_: self._verifica_pass())
            g.attach(_lbl(_t(k), wrap=False), 0, n, 1, 1)
            g.attach(e, 1, n, 1, 1)
        mostra = Gtk.CheckButton(label=_t("inst.show"))
        mostra.connect("toggled", lambda c: [x.set_visibility(c.get_active())
                                             for x in (self.e1, self.e2)])
        g.attach(mostra, 1, 2, 1, 1)
        self.e1.connect("activate", lambda *_: self.e2.grab_focus())
        self.e2.connect("activate", lambda *_: self._pass_ok() and self._vai(+1))
        b.pack_start(g, False, False, 0)
        self.pass_stato = _lbl("")
        b.pack_start(self.pass_stato, False, False, 0)
        b.pack_start(_lbl(_t("inst.pass_warn")), False, False, 6)
        self.stack.add_named(b, "pass")

    def _p_utente(self):
        # password dell'utente 'nexus' sul sistema installato: accesso, console
        # (Ctrl+Alt+F2) e blocco schermo. Di serie e' la stessa passphrase dei
        # dati: una sola parola da ricordare.
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        b.pack_start(_titolo(_t("inst.user_h")), False, False, 0)
        b.pack_start(_lbl(_t("inst.user_body")), False, False, 0)
        self.u_stessa = Gtk.CheckButton(label=_t("inst.user_same"))
        self.u_stessa.set_active(True)
        b.pack_start(self.u_stessa, False, False, 0)
        g = Gtk.Grid(column_spacing=10, row_spacing=8)
        self.u1, self.u2 = Gtk.Entry(), Gtk.Entry()
        for n, (e, k) in enumerate(((self.u1, "inst.user1"), (self.u2, "inst.user2"))):
            e.set_visibility(False)
            e.set_hexpand(True)
            e.connect("changed", lambda *_: self._verifica_utente())
            g.attach(_lbl(_t(k), wrap=False), 0, n, 1, 1)
            g.attach(e, 1, n, 1, 1)
        mostra = Gtk.CheckButton(label=_t("inst.show"))
        mostra.connect("toggled", lambda c: [x.set_visibility(c.get_active())
                                             for x in (self.u1, self.u2)])
        g.attach(mostra, 1, 2, 1, 1)
        self.u1.connect("activate", lambda *_: self.u2.grab_focus())
        self.u2.connect("activate", lambda *_: self._utente_ok() and self._vai(+1))
        self.u_griglia = g
        b.pack_start(g, False, False, 0)
        self.u_stato = _lbl("")
        b.pack_start(self.u_stato, False, False, 0)
        self.u_stessa.connect("toggled", lambda *_: self._verifica_utente())
        self.stack.add_named(b, "utente")

    def _p_riepilogo(self):
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        b.pack_start(_titolo(_t("inst.sum_h")), False, False, 0)
        self.riep = _lbl("", markup=True)
        b.pack_start(self.riep, False, False, 0)
        self.capito = Gtk.CheckButton()
        self.capito_lbl = _lbl("")
        self.capito.add(self.capito_lbl)
        self.capito.connect("toggled", lambda *_: self._aggiorna_nav())
        b.pack_start(self.capito, False, False, 8)
        self.stack.add_named(b, "riepilogo")

    def _p_lavoro(self):
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.l_titolo = _titolo(_t("inst.work_h"))
        b.pack_start(self.l_titolo, False, False, 0)
        self.barra = Gtk.ProgressBar()
        self.barra.set_show_text(True)
        b.pack_start(self.barra, False, False, 0)
        self.l_passo = _lbl("")
        b.pack_start(self.l_passo, False, False, 0)
        exp = Gtk.Expander(label=_t("inst.details"))
        sw = Gtk.ScrolledWindow()
        sw.set_min_content_height(200)
        self.tv = Gtk.TextView(editable=False, monospace=True, cursor_visible=False)
        self.tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        sw.add(self.tv)
        exp.add(sw)
        self.exp = exp
        b.pack_start(exp, True, True, 0)
        self.fine = Gtk.Box(spacing=8)
        b.pack_start(self.fine, False, False, 0)
        self.stack.add_named(b, "lavoro")

    # ------------------------------------------------------------ logica
    def _controlla(self):
        try:
            r = subprocess.run([INSTALL, "--controlla"], capture_output=True,
                               text=True, timeout=30)
            ok, msg = r.returncode == 0, (r.stderr or r.stdout).strip()
        except (OSError, subprocess.TimeoutExpired) as e:
            ok, msg = False, str(e)
        GLib.idle_add(self._esito_controllo, ok, msg)

    def _esito_controllo(self, ok, msg):
        self.media_ok = ok
        if ok:
            self.stato_media.set_markup("<b>✔ %s</b>" % GLib.markup_escape_text(_t("inst.ready")))
        else:
            self.stato_media.set_markup("<b>✘ %s</b>\n%s" % (
                GLib.markup_escape_text(_t("inst.not_ready")),
                GLib.markup_escape_text(msg.replace("ERRORE: ", ""))))
        self._aggiorna_nav()
        return False

    def _carica_dischi(self):
        for c in self.box_dischi.get_children():
            self.box_dischi.remove(c)
        try:
            out = subprocess.run([INSTALL, "--dischi"], capture_output=True,
                                 text=True, timeout=30).stdout
        except (OSError, subprocess.TimeoutExpired):
            out = ""
        self.dischi = [r.split("\t") for r in out.splitlines() if r.count("\t") >= 2]
        if not self.dischi:
            self.box_dischi.pack_start(_lbl(_t("inst.no_disk")), False, False, 0)
            self.disco = None
        else:
            gruppo = None
            for dev, gb, mod in self.dischi:
                rb = Gtk.RadioButton.new_with_label_from_widget(
                    gruppo, "%s   —   %s GB   —   %s" % (dev, gb, mod))
                gruppo = gruppo or rb
                rb.connect("toggled", self._scelto, dev)
                self.box_dischi.pack_start(rb, False, False, 0)
            gruppo.set_active(True)
            self.disco = self.dischi[0][0]
        self.box_dischi.show_all()
        self._aggiorna_nav()

    def _scelto(self, rb, dev):
        if rb.get_active():
            self.disco = dev

    def _verifica_pass(self):
        a, b = self.e1.get_text(), self.e2.get_text()
        if len(a) < 8:
            m = _t("inst.pass_short")
        elif a != b:
            m = _t("inst.pass_diff")
        else:
            m = "✔ " + _t("inst.pass_ok")
        self.pass_stato.set_text(m if a or b else "")
        self._aggiorna_nav()

    def _verifica_utente(self):
        stessa = self.u_stessa.get_active()
        self.u_griglia.set_sensitive(not stessa)
        a, b = self.u1.get_text(), self.u2.get_text()
        if stessa or not (a or b):
            m = ""
        elif len(a) < 6:
            m = _t("inst.user_short")
        elif a != b:
            m = _t("inst.pass_diff")
        else:
            m = "✔ " + _t("inst.pass_ok")
        self.u_stato.set_text(m)
        self._aggiorna_nav()

    def _utente_ok(self):
        if self.u_stessa.get_active():
            return True
        a = self.u1.get_text()
        return len(a) >= 6 and a == self.u2.get_text()

    def _pass_ok(self):
        a = self.e1.get_text()
        return len(a) >= 8 and a == self.e2.get_text()

    def _vai(self, d):
        nome = self.pagine[self.i]
        if d > 0 and nome == "riepilogo":
            self.i += 1
            self._mostra()
            self._avvia()
            return
        if d > 0 and nome == "lavoro":
            self.win.destroy()
            return
        self.i = max(0, min(len(self.pagine) - 1, self.i + d))
        if self.pagine[self.i] == "disco":
            self._carica_dischi()
        if self.pagine[self.i] == "riepilogo":
            mod = next((x[2] for x in self.dischi if x[0] == self.disco), "")
            gb = next((x[1] for x in self.dischi if x[0] == self.disco), "")
            self.riep.set_markup(_t("inst.sum_body", disk=GLib.markup_escape_text(self.disco),
                                    gb=gb, model=GLib.markup_escape_text(mod)))
            self.capito_lbl.set_text(_t("inst.sum_confirm", disk=self.disco))
            self.capito.set_active(False)
        self._mostra()
        if self.pagine[self.i] == "pass":
            self.e1.grab_focus()
        if self.pagine[self.i] == "utente":
            self._verifica_utente()

    def _mostra(self):
        self.stack.set_visible_child_name(self.pagine[self.i])
        self._aggiorna_nav()

    def _aggiorna_nav(self):
        nome = self.pagine[self.i]
        ok = {"benvenuto": getattr(self, "media_ok", False),
              "disco": bool(self.disco),
              "pass": self._pass_ok(),
              "utente": self._utente_ok(),
              "riepilogo": self.capito.get_active(),
              "lavoro": not self.lavora}.get(nome, True)
        self.b_avanti.set_sensitive(ok)
        self.b_indietro.set_sensitive(self.i > 0 and nome != "lavoro")
        lab = self.b_avanti.get_child().get_children()[1]
        lab.set_text({"riepilogo": _t("inst.install"),
                      "lavoro": _t("inst.close")}.get(nome, _t("inst.next")))
        if nome == "riepilogo":
            self.b_avanti.get_style_context().add_class("destructive-action")
        else:
            self.b_avanti.get_style_context().remove_class("destructive-action")

    # ------------------------------------------------------------ lavoro
    def _avvia(self):
        self.lavora = True
        self._aggiorna_nav()
        fd, self.passfile = tempfile.mkstemp(prefix="nxs-pp-")
        os.write(fd, self.e1.get_text().encode())
        os.close(fd)
        os.chmod(self.passfile, 0o600)
        upw = self.e1.get_text() if self.u_stessa.get_active() else self.u1.get_text()
        fd, self.userfile = tempfile.mkstemp(prefix="nxs-up-")
        os.write(fd, upw.encode())
        os.close(fd)
        os.chmod(self.userfile, 0o600)
        for e in (self.e1, self.e2, self.u1, self.u2):
            e.set_text("")
        cmd = ["doas", "-n", INSTALL, "--disco", self.disco, "--passfile",
               self.passfile, "--utentefile", self.userfile, "--si"]
        threading.Thread(target=self._esegui, args=(cmd,), daemon=True).start()

    def _esegui(self, cmd):
        rc = 1
        try:
            with open(LOG, "w") as log:
                self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                             stderr=subprocess.STDOUT, text=True, bufsize=1)
                for riga in self.proc.stdout:
                    log.write(riga)
                    log.flush()
                    GLib.idle_add(self._riga, riga.rstrip("\n"))
                rc = self.proc.wait()
        except OSError as e:
            GLib.idle_add(self._riga, "ERRORE: %s" % e)
        finally:
            for f in (self.passfile, self.userfile):
                try:
                    os.remove(f)
                except (OSError, TypeError):
                    pass
        GLib.idle_add(self._finito, rc == 0)

    def _riga(self, riga):
        buf = self.tv.get_buffer()
        buf.insert(buf.get_end_iter(), riga + "\n")
        self.tv.scroll_to_iter(buf.get_end_iter(), 0, False, 0, 0)
        if riga.startswith("PASSO "):
            try:
                n = int(riga.split()[1].split("/")[0])
            except (IndexError, ValueError):
                n = 0
            testo = riga.split(" ", 2)[2] if riga.count(" ") >= 2 else ""
            self.barra.set_fraction(min(1.0, (n - 1) / float(PASSI - 1)))
            self.barra.set_text("%d / %d" % (n, PASSI))
            self.l_passo.set_text(self._nome_passo(n, testo))
        elif riga.startswith("ERRORE"):
            self.l_passo.set_text(riga)
        return False

    @staticmethod
    def _nome_passo(n, testo):
        k = "inst.step%d" % n
        s = _t(k)
        return testo if s == k else s

    def _finito(self, ok):
        self.lavora = False
        if ok:
            self.barra.set_fraction(1.0)
            self.l_titolo.set_markup("<span size='large' weight='bold'>✔ %s</span>"
                                     % GLib.markup_escape_text(_t("inst.done_h")))
            self.l_passo.set_text(_t("inst.done_body"))
            spegni = icon_button(_t("inst.poweroff"), "system-shutdown", primary=True)
            spegni.connect("clicked", lambda *_: subprocess.Popen(["doas", "-n", "poweroff"]))
            self.fine.pack_start(spegni, False, False, 0)
        else:
            self.l_titolo.set_markup("<span size='large' weight='bold'>✘ %s</span>"
                                     % GLib.markup_escape_text(_t("inst.fail_h")))
            self.exp.set_expanded(True)
            self.l_passo.set_text(_t("inst.fail_body", log=LOG))
        self.fine.show_all()
        self._aggiorna_nav()
        return False

    def _esci(self, *_):
        if self.lavora:
            return
        Gtk.main_quit()


def main():
    app = Installatore()
    app.win.connect("delete-event", lambda *_: app.lavora)   # non chiudere a meta'
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
