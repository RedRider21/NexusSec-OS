# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""Spotlight dell'assistente IA: finestrella rapida richiamabile da hotkey
(Super+A). Scrivi una domanda, ottieni la risposta con i comandi da copiare.
La IA resta un consulente (Fase 1): non esegue nulla.

Threading: la chiamata al backend gira in un thread; la UI si aggiorna via
GLib.idle_add (mai bloccare il main loop GTK)."""
from __future__ import annotations

import sys
import threading

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib  # noqa: E402

sys.path.insert(0, "/usr/local/lib")
from nxs_ai import agent, backend, config  # noqa: E402

try:
    from nxs_i18n import t as _t
except Exception:                       # noqa: BLE001
    def _t(chiave, **kw):               # ripiego: mostra la chiave
        return chiave

try:
    from nxs_cc.common import apply_css       # stile coerente col resto
except Exception:                             # noqa: BLE001
    def apply_css():
        return


class Spotlight(Gtk.Window):
    def __init__(self):
        super().__init__(title="Assistente IA")
        self.set_default_size(620, 420)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_keep_above(True)
        self.history: list[dict] = []

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(12)
        self.add(box)

        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text(_t("ai.spot_ph"))
        self.entry.connect("activate", self._on_send)
        box.pack_start(self.entry, False, False, 0)

        self.status = Gtk.Label(xalign=0)
        self.status.get_style_context().add_class("nxs-val")
        box.pack_start(self.status, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        self.view = Gtk.TextView()
        self.view.set_editable(False)
        self.view.set_cursor_visible(False)
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.view.set_left_margin(8); self.view.set_right_margin(8)
        self.view.set_top_margin(6)
        self.buf = self.view.get_buffer()
        scroll.add(self.view)
        box.pack_start(scroll, True, True, 0)

        self.connect("key-press-event", self._on_key)

        be = config.load().get("backend", "off")
        if be == "off":
            self._set_status("Assistente IA disattivato — configuralo nel Centro "
                             "di Controllo → Assistente IA.")
            self.entry.set_sensitive(False)

    def _set_status(self, text):
        self.status.set_text(text)

    def _on_key(self, _w, ev):
        if ev.keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
        return False

    def _on_send(self, _entry):
        q = self.entry.get_text().strip()
        if not q:
            return
        self.entry.set_sensitive(False)
        self._set_status("Sto pensando…")
        self.buf.set_text("")
        threading.Thread(target=self._ask, args=(q,), daemon=True).start()

    def _ask(self, q):
        try:
            reply = agent.ask(q, self.history)
            self.history += [{"role": "user", "content": q},
                             {"role": "assistant", "content": reply}]
            self.history = self.history[-12:]
            GLib.idle_add(self._show, reply, None)
        except backend.AIError as e:
            GLib.idle_add(self._show, None, str(e))
        except Exception as e:                 # noqa: BLE001
            GLib.idle_add(self._show, None, f"Errore: {e}")

    def _show(self, reply, err):
        if err:
            self._set_status("⚠ " + err)
        else:
            self._set_status("Risposta (i comandi mostrati vanno valutati prima "
                             "di eseguirli):")
            self.buf.set_text(reply or "")
        self.entry.set_sensitive(True)
        self.entry.grab_focus()
        return False


def main():
    apply_css()
    win = Spotlight()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    win.entry.grab_focus()
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
