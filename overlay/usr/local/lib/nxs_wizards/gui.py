"""GUI GTK3 delle procedure guidate.

Coerente col resto di NexusSec (riusa nxs_cc.common: stile Nebula, finestra con
header, pulsanti a icona). Flusso:
  scelta procedura  ->  form (campi + Modalita' + Opzioni)  ->  output dal vivo.

La schermata di scelta elenca gli standard e i personalizzati (con eliminazione)
e offre "Nuovo wizard" per aprire il costruttore.
"""
from __future__ import annotations

import threading

from nxs_cc import common  # imposta gi.require_version("Gtk","3.0") all'import
from gi.repository import Gtk, GLib

from . import recipes, runner


class _Wizard:
    def __init__(self, win, body):
        self.win = win
        self.body = body
        self._thread = None
        self._stop = False
        self._tv = None
        self.buf = None
        self.start_btn = None
        # stato del form corrente
        self._mode_btns = {}
        self._opt_btns = {}
        self._stealth_btn = None
        self._count_lbl = None
        self._cur_wiz = None

    # ---- utilita' layout ----
    def _clear(self):
        for child in self.body.get_children():
            self.body.remove(child)

    def _section(self, text):
        lab = Gtk.Label(label=text)
        lab.set_xalign(0)
        lab.get_style_context().add_class("title")
        self.body.pack_start(lab, False, False, 0)

    # ---- schermata: scelta procedura ----
    def show_chooser(self):
        self._clear()
        intro = Gtk.Label(label="Scegli una procedura guidata:")
        intro.set_xalign(0)
        self.body.pack_start(intro, False, False, 0)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        lst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        sw.add(lst)
        self.body.pack_start(sw, True, True, 0)

        ws = recipes.all_wizards()
        if not ws:
            lst.pack_start(Gtk.Label(label="(nessuna procedura definita)"),
                           False, False, 0)
        for wid, w in ws.items():
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            label = w.get("name", wid)
            if w.get("custom"):
                label += "   (personalizzato)"
            btn = common.icon_button(label, w.get("icon", "system-run-symbolic"))
            btn.connect("clicked", lambda _b, i=wid: self.show_form(i))
            row.pack_start(btn, True, True, 0)
            if w.get("custom"):
                dele = common.icon_button("Elimina", "user-trash-symbolic")
                dele.connect("clicked", lambda _b, i=wid, n=w.get("name", wid):
                             self._delete_custom(i, n))
                row.pack_start(dele, False, False, 0)
            lst.pack_start(row, False, False, 0)

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        newb = common.icon_button("Nuovo wizard personalizzato",
                                  "list-add-symbolic", primary=True)
        newb.connect("clicked", lambda _b: self.show_builder())
        bar.pack_end(newb, False, False, 0)
        self.body.pack_start(bar, False, False, 0)
        self.body.show_all()

    def _delete_custom(self, wid, name):
        dlg = Gtk.MessageDialog(
            transient_for=self.win, modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Eliminare il wizard personalizzato \"{name}\"?")
        resp = dlg.run()
        dlg.destroy()
        if resp == Gtk.ResponseType.YES:
            recipes.delete_custom(wid)
            self.show_chooser()

    def show_builder(self, wid=None):
        # import ritardato: builder usa recipes/common, non gui (niente ciclo)
        from . import builder
        builder.BuilderScreen(self.win, self.body,
                              on_done=self.show_chooser, edit_id=wid).show()

    # ---- schermata: form + output ----
    def show_form(self, wid):
        self._clear()
        self._mode_btns = {}
        self._opt_btns = {}
        w = recipes.get(wid)
        if not w:
            self.show_chooser()
            return
        self._cur_wiz = w

        title = Gtk.Label(label=w.get("name", wid))
        title.set_xalign(0)
        title.get_style_context().add_class("title")
        self.body.pack_start(title, False, False, 0)

        desc = Gtk.Label(label=w.get("description", ""))
        desc.set_xalign(0)
        desc.set_line_wrap(True)
        self.body.pack_start(desc, False, False, 0)

        # --- campi input ---
        entries = {}
        for f in w.get("fields", []):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            lab = Gtk.Label(label=f.get("label", f["key"]))
            lab.set_xalign(0)
            lab.set_size_request(240, -1)
            lab.set_line_wrap(True)
            ent = Gtk.Entry()
            ent.set_hexpand(True)
            if f.get("placeholder"):
                ent.set_placeholder_text(f["placeholder"])
            row.pack_start(lab, False, False, 0)
            row.pack_start(ent, True, True, 0)
            if f.get("type") == "file":
                br = Gtk.Button(label="Sfoglia...")
                br.connect("clicked", lambda _b, e=ent: self._pick_file(e))
                row.pack_start(br, False, False, 0)
            self.body.pack_start(row, False, False, 0)
            entries[f["key"]] = ent

        # --- modalita' (intensita', scelta singola) ---
        modes = w.get("modes") or []
        if modes:
            self._section("Modalita'")
            mbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            default_m = recipes.default_mode(w)
            first = None
            for m in modes:
                lbl = m.get("label", m["id"])
                if m.get("desc"):
                    lbl += "  —  " + m["desc"]
                rb = Gtk.RadioButton.new_with_label_from_widget(first, lbl)
                if first is None:
                    first = rb
                if m["id"] == default_m:
                    rb.set_active(True)
                rb.connect("toggled", lambda _b: self._recount())
                self._mode_btns[m["id"]] = rb
                mbox.pack_start(rb, False, False, 0)
            self.body.pack_start(mbox, False, False, 0)

        # --- opzioni (spunte indipendenti) ---
        options = w.get("options") or []
        if options:
            self._section("Opzioni")
            obox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            for o in options:
                lbl = o.get("label", o["id"])
                if o.get("desc"):
                    lbl += "  —  " + o["desc"]
                cb = Gtk.CheckButton.new_with_label(lbl)
                cb.set_active(bool(o.get("default")))
                cb.connect("toggled", lambda _b: self._recount())
                self._opt_btns[o["id"]] = cb
                obox.pack_start(cb, False, False, 0)
            self.body.pack_start(obox, False, False, 0)

        # --- stealth: mostrato solo se praticabile (>=1 step instradabile via Tor) ---
        if recipes.stealth_applicable(w):
            self._section("Stealth")
            self._stealth_btn = Gtk.CheckButton.new_with_label(
                "Anonimato via Tor dove possibile "
                "(ogni step mostra: via Tor / non anonimizzabile / locale)")
            self._stealth_btn.set_active(recipes.stealth_default(w))
            self._stealth_btn.connect("toggled", lambda _b: self._recount())
            self.body.pack_start(self._stealth_btn, False, False, 0)
        else:
            note = Gtk.Label(
                label="Stealth non applicabile: operazioni locali, nessuno "
                      "step instradabile via Tor.")
            note.set_xalign(0)
            note.set_line_wrap(True)
            note.get_style_context().add_class("nxs-dim")
            self.body.pack_start(note, False, False, 0)

        # --- riga conteggio step ---
        self._count_lbl = Gtk.Label(label="")
        self._count_lbl.set_xalign(0)
        self._count_lbl.get_style_context().add_class("nxs-dim")
        self.body.pack_start(self._count_lbl, False, False, 0)
        self._recount()

        # --- area output (monospace, scrollabile) ---
        self.buf = Gtk.TextBuffer()
        self._tv = Gtk.TextView(buffer=self.buf)
        self._tv.set_editable(False)
        self._tv.set_cursor_visible(False)
        self._tv.set_monospace(True)
        self._tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        sc = Gtk.ScrolledWindow()
        sc.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sc.get_style_context().add_class("nxs-output")
        sc.add(self._tv)
        self.body.pack_start(sc, True, True, 0)

        # --- barra pulsanti ---
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        back = common.icon_button("Indietro", "go-previous-symbolic")
        back.connect("clicked", lambda _b: self.show_chooser())
        self.start_btn = common.icon_button("Avvia",
                                             "media-playback-start-symbolic",
                                             primary=True)
        self.start_btn.connect("clicked",
                               lambda _b: self._start(wid, entries))
        bar.pack_start(back, False, False, 0)
        bar.pack_end(self.start_btn, False, False, 0)
        self.body.pack_start(bar, False, False, 0)
        self.body.show_all()

    def _selected_mode(self):
        for mid, rb in self._mode_btns.items():
            if rb.get_active():
                return mid
        return recipes.default_mode(self._cur_wiz) if self._cur_wiz else None

    def _selected_options(self):
        return [oid for oid, cb in self._opt_btns.items() if cb.get_active()]

    def _selected_stealth(self):
        return bool(self._stealth_btn and self._stealth_btn.get_active())

    def _recount(self):
        if not self._count_lbl or not self._cur_wiz:
            return
        n = recipes.count_active_steps(self._cur_wiz, self._selected_mode(),
                                       self._selected_options(),
                                       self._selected_stealth())
        extra = "  ·  Stealth ON" if self._selected_stealth() else ""
        self._count_lbl.set_text(f"→ verranno eseguiti {n} step{extra}")

    def _pick_file(self, entry):
        d = Gtk.FileChooserDialog(title="Scegli file/immagine", parent=self.win,
                                  action=Gtk.FileChooserAction.OPEN)
        d.add_buttons("Annulla", Gtk.ResponseType.CANCEL,
                      "Apri", Gtk.ResponseType.OK)
        if d.run() == Gtk.ResponseType.OK:
            entry.set_text(d.get_filename() or "")
        d.destroy()

    # ---- esecuzione ----
    def _append(self, line):
        end = self.buf.get_end_iter()
        self.buf.insert(end, line + "\n")
        mark = self.buf.create_mark(None, self.buf.get_end_iter(), False)
        self._tv.scroll_to_mark(mark, 0.0, False, 0, 0)
        return False

    def _start(self, wid, entries):
        if self._thread and self._thread.is_alive():
            return
        values = {k: e.get_text().strip() for k, e in entries.items()}
        mode = self._selected_mode()
        options = self._selected_options()
        stealth = self._selected_stealth()
        self.buf.set_text("")
        self.start_btn.set_sensitive(False)
        self._stop = False

        def emit(line):
            GLib.idle_add(self._append, line)

        def work():
            try:
                runner.run_wizard(wid, values, emit, stop=lambda: self._stop,
                                  mode=mode, options=options, stealth=stealth)
            finally:
                GLib.idle_add(self.start_btn.set_sensitive, True)

        self._thread = threading.Thread(target=work, daemon=True)
        self._thread.start()


def main(wid: str | None = None, start_builder: bool = False) -> int:
    win, body = common.panel_window("Procedure guidate NexusSec", 780, 640)
    win.connect("destroy", Gtk.main_quit)
    app = _Wizard(win, body)
    if start_builder:
        app.show_builder()
    elif wid and recipes.get(wid):
        app.show_form(wid)
    else:
        app.show_chooser()
    win.show_all()
    Gtk.main()
    return 0
