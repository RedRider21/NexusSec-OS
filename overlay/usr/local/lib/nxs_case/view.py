# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""Casi forensi - interfaccia GTK3.

Riusa lo stile del Centro di Controllo (nxs_cc.common) e l'elenco dischi di
nxs_disks: nessuna duplicazione.

L'interfaccia e' costruita attorno a UNA sequenza, perche' in un accertamento
l'ordine non e' facoltativo: proteggi il reperto, acquisisci, verifica,
analizza, verbalizza. Il pulsante "Esegui tutto" fa esattamente questa sequenza
senza scorciatoie; le schede servono a rifare un singolo passo o a rileggerlo.
"""
from __future__ import annotations

import os
import threading
import webbrowser

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Pango  # noqa: E402

from nxs_cc.common import panel_window, icon_button, info_dialog, have, run_bg
from nxs_case import model, report

try:
    from nxs_i18n import t as _t
except Exception:                # noqa: BLE001
    def _t(key, **kw):           # fallback: non rompe mai la UI
        return key

try:
    from nxs_disks import model as dmodel
except ImportError:                          # noqa: BLE001
    dmodel = None


def _lab(testo, classe="nxs-val", wrap=True):
    l = Gtk.Label(label=testo)
    l.set_xalign(0)
    l.set_line_wrap(wrap)
    l.get_style_context().add_class(classe)
    return l


def open_case(_btn=None):
    win, body = panel_window(_t("cs.title"), 860, 700)
    ctx = {"caso": None, "busy": False}

    intro = _lab(_t("cs.intro"))
    body.pack_start(intro, False, False, 0)

    # ---- barra del caso corrente ----------------------------------------
    barra = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    barra.set_margin_top(6)
    lbl_caso = _lab(_t("cs.no_case"), "nxs-key", wrap=False)
    barra.pack_start(lbl_caso, True, True, 0)
    b_nuovo = icon_button(_t("cs.new_case"), "document-new-symbolic", primary=True)
    b_apri = icon_button(_t("cs.open"), "document-open-symbolic")
    barra.pack_start(b_nuovo, False, False, 0)
    barra.pack_start(b_apri, False, False, 0)
    body.pack_start(barra, False, False, 0)

    nb = Gtk.Notebook()
    nb.set_margin_top(10)
    body.pack_start(nb, True, True, 0)

    # ================= 1. ACQUISIZIONE =================
    pg1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    pg1.set_margin_top(10); pg1.set_margin_start(6); pg1.set_margin_end(6)
    pg1.pack_start(_lab(_t("cs.acq_intro")), False, False, 0)
    store_dev = Gtk.ListStore(str, str, str)          # percorso, dim, descrizione
    tv = Gtk.TreeView(model=store_dev)
    for i, t in enumerate((_t("dk.col_device"), _t("dk.col_size"), _t("cs.col_content"))):
        r = Gtk.CellRendererText()
        r.set_property("ellipsize", Pango.EllipsizeMode.END)
        tv.append_column(Gtk.TreeViewColumn(t, r, text=i))
    sc = Gtk.ScrolledWindow(); sc.set_size_request(-1, 150); sc.add(tv)
    sc.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    pg1.pack_start(sc, False, False, 0)

    rowd = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    rowd.pack_start(_lab(_t("cs.exhibit_desc"), "nxs-key", wrap=False), False, False, 0)
    e_desc = Gtk.Entry(); e_desc.set_placeholder_text(_t("cs.exhibit_ph"))
    rowd.pack_start(e_desc, True, True, 0)
    pg1.pack_start(rowd, False, False, 0)

    az1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    b_tutto = icon_button(_t("cs.run_all"),
                          "media-playback-start-symbolic", primary=True)
    b_agg = icon_button(_t("cs.refresh_list"), "view-refresh-symbolic")
    az1.pack_start(b_tutto, True, True, 0)
    az1.pack_start(b_agg, False, False, 0)
    pg1.pack_start(az1, False, False, 0)

    # --- oppure un passo per volta -------------------------------------
    # Stessa sequenza, ma ogni passo ha il suo pulsante: serve quando un
    # reperto e' gia' stato acquisito altrove, quando si vuole rifare solo la
    # verifica, o quando l'analisi va ripetuta su un'immagine diversa.
    sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
    sep.set_margin_top(8)
    pg1.pack_start(sep, False, False, 0)
    pg1.pack_start(_lab(_t("cs.single_step"), "nxs-key", wrap=False),
                   False, False, 0)

    rowi = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    rowi.pack_start(_lab(_t("cs.case_image"), "nxs-key", wrap=False), False, False, 0)
    combo_img = Gtk.ComboBoxText()
    rowi.pack_start(combo_img, True, True, 0)
    pg1.pack_start(rowi, False, False, 0)

    passi = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    b_acq = icon_button(_t("cs.step1"), "drive-harddisk-symbolic")
    b_ver = icon_button(_t("cs.step2"), "security-high-symbolic")
    b_ana = icon_button(_t("cs.step3"), "system-search-symbolic")
    b_rel2 = icon_button(_t("cs.step4"), "document-properties-symbolic")
    for b in (b_acq, b_ver, b_ana, b_rel2):
        passi.pack_start(b, True, True, 0)
    pg1.pack_start(passi, False, False, 0)
    nb.append_page(pg1, Gtk.Label(label=_t("cs.tab_acq")))

    # ================= 2. NOTE =================
    pg2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    pg2.set_margin_top(10); pg2.set_margin_start(6); pg2.set_margin_end(6)
    pg2.pack_start(_lab(_t("cs.notes_intro")),
                   False, False, 0)
    tvnote = Gtk.TextView(); tvnote.set_wrap_mode(Gtk.WrapMode.WORD)
    scn = Gtk.ScrolledWindow(); scn.set_size_request(-1, 120); scn.add(tvnote)
    pg2.pack_start(scn, False, False, 0)
    b_nota = icon_button(_t("cs.add_note"), "list-add-symbolic")
    pg2.pack_start(b_nota, False, False, 0)
    pg2.pack_start(_lab(_t("cs.custody"), "nxs-key", wrap=False), False, False, 0)
    store_log = Gtk.ListStore(str, str, str)
    tvlog = Gtk.TreeView(model=store_log)
    for i, t in enumerate((_t("cs.col_when"), _t("cs.col_action"), _t("cs.col_details"))):
        r = Gtk.CellRendererText()
        r.set_property("ellipsize", Pango.EllipsizeMode.END)
        tvlog.append_column(Gtk.TreeViewColumn(t, r, text=i))
    scl = Gtk.ScrolledWindow(); scl.set_size_request(-1, 200); scl.add(tvlog)
    scl.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    pg2.pack_start(scl, True, True, 0)
    nb.append_page(pg2, Gtk.Label(label=_t("cs.tab_record")))

    # ================= 3. RELAZIONE =================
    pg3 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    pg3.set_margin_top(10); pg3.set_margin_start(6); pg3.set_margin_end(6)
    pg3.pack_start(_lab(_t("cs.report_intro")), False, False, 0)
    az3 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    b_rel = icon_button(_t("cs.gen_report"), "document-properties-symbolic", primary=True)
    b_apri_rel = icon_button(_t("cs.open_report"), "document-open-symbolic")
    b_cart = icon_button(_t("cs.open_folder"), "folder-open-symbolic")
    for b in (b_rel, b_apri_rel, b_cart):
        az3.pack_start(b, False, False, 0)
    pg3.pack_start(az3, False, False, 0)
    nb.append_page(pg3, Gtk.Label(label=_t("cs.tab_report")))

    # ---- avanzamento -----------------------------------------------------
    prog = Gtk.ProgressBar(); prog.set_show_text(True); prog.set_text("")
    body.pack_start(prog, False, False, 0)
    stato = _lab("")
    body.pack_start(stato, False, False, 0)

    # ---- funzioni --------------------------------------------------------
    def aggiorna_dispositivi(_w=None):
        store_dev.clear()
        if dmodel is None:
            store_dev.append([_t("cs.no_disks"), "", ""])
            return
        for n in dmodel.flatten(dmodel.list_devices()):
            if n.type not in ("disk", "part") or n.name.startswith("zram"):
                continue
            store_dev.append([n.path, dmodel.human(n.size), n.descrizione])

    def _riempi_immagini(c):
        """Riempie l'elenco delle immagini del caso APERTO.

        Va svuotato SEMPRE, anche quando non c'e' un caso: altrimenti restano
        elencate le immagini del caso precedente e si potrebbe lavorare sul
        reperto sbagliato - in un contesto forense e' un errore grave.
        Quando non ce ne sono, la voce segnaposto lo dice esplicitamente
        invece di lasciare un menu vuoto e muto.
        """
        combo_img.remove_all()
        trovate = 0
        if c is not None:
            imgdir = os.path.join(c.dir, "immagini")
            if os.path.isdir(imgdir):
                for f in sorted(os.listdir(imgdir)):
                    if f.endswith(".E01"):
                        combo_img.append(os.path.join(imgdir, f), f)
                        trovate += 1
        if trovate == 0:
            combo_img.append("", _t("cs.no_image_combo"))
        combo_img.set_active(0)
        # i passi 2 e 3 lavorano su un'immagine: senza, restano spenti, cosi'
        # si vede subito che non sono disponibili invece di scoprirlo dopo.
        for b in (b_ver, b_ana):
            b.set_sensitive(trovate > 0 and not ctx["busy"])
        return trovate

    def aggiorna_caso():
        c = ctx["caso"]
        _riempi_immagini(c)
        if c is None:
            lbl_caso.set_text(_t("cs.no_case"))
            store_log.clear()
            return
        lbl_caso.set_text(_t("cs.case_bar")
                          % (c.meta.get("nome", "-"), c.meta.get("operatore", "-"), c.dir))
        store_log.clear()
        for r in c.righe_registro():
            store_log.append([r[0] if len(r) > 0 else "",
                              r[1] if len(r) > 1 else "",
                              r[2] if len(r) > 2 else ""])

    def serve_caso():
        if ctx["caso"] is None:
            info_dialog(_t("cs.no_case"),
                        _t("cs.no_case_body"),
                        "warning", win)
            return False
        return True

    def lavora(fn, titolo):
        """Esegue un'operazione lunga senza bloccare la finestra."""
        if ctx["busy"]:
            return
        ctx["busy"] = True
        prog.set_fraction(0.0); prog.set_text(titolo)
        for b in (b_tutto, b_rel, b_nuovo, b_apri, b_acq, b_ver, b_ana, b_rel2):
            b.set_sensitive(False)

        def avanza(testo):
            def _u():
                prog.set_text(testo[:90]); prog.pulse()
                return False
            GLib.idle_add(_u)

        def worker():
            try:
                ok, msg = fn(avanza)
            except Exception as e:           # noqa: BLE001
                ok, msg = False, str(e)
            def fine():
                ctx["busy"] = False
                prog.set_fraction(1.0 if ok else 0.0)
                prog.set_text(_t("cs.done") if ok else _t("cs.interrupted"))
                stato.set_text((_t("cs.ok_msg") if ok else _t("dk.err_msg")) % msg)
                for b in (b_tutto, b_rel, b_nuovo, b_apri, b_acq, b_rel2):
                    b.set_sensitive(True)
                # b_ver/b_ana li riaccende aggiorna_caso, ma solo se ora c'e'
                # davvero un'immagine su cui lavorare.
                aggiorna_caso()
                return False
            GLib.idle_add(fine)
        threading.Thread(target=worker, daemon=True).start()

    # --- nuovo caso -------------------------------------------------------
    def on_nuovo(_w):
        d = Gtk.Dialog(title=_t("cs.new_case"), transient_for=win, modal=True)
        d.add_buttons(_t("v.cancel"), Gtk.ResponseType.CANCEL, _t("v.create"), Gtk.ResponseType.OK)
        box = d.get_content_area()
        box.set_spacing(6); box.set_margin_top(10); box.set_margin_bottom(10)
        box.set_margin_start(12); box.set_margin_end(12)
        campi = {}
        for chiave, etichetta, segnaposto in (
                ("nome", _t("cs.f_name"), _t("cs.ph_name")),
                ("operatore", _t("cs.f_operator"), _t("cs.ph_operator")),
                ("riferimento", _t("cs.f_reference"), _t("cs.ph_reference"))):
            box.pack_start(_lab(etichetta, "nxs-key", wrap=False), False, False, 0)
            e = Gtk.Entry(); e.set_placeholder_text(segnaposto)
            box.pack_start(e, False, False, 0)
            campi[chiave] = e
        box.pack_start(_lab(_t("cs.initial_notes"), "nxs-key", wrap=False), False, False, 0)
        tvn = Gtk.TextView(); tvn.set_wrap_mode(Gtk.WrapMode.WORD)
        scd = Gtk.ScrolledWindow(); scd.set_size_request(-1, 80); scd.add(tvn)
        box.pack_start(scd, True, True, 0)
        d.show_all()
        r = d.run()
        if r == Gtk.ResponseType.OK:
            b = tvn.get_buffer()
            note = b.get_text(b.get_start_iter(), b.get_end_iter(), True)
            nome = campi["nome"].get_text().strip()
            oper = campi["operatore"].get_text().strip()
            d.destroy()
            if not nome or not oper:
                info_dialog(_t("cs.missing_data"),
                            _t("cs.missing_data_body"), "warning", win)
                return
            os.makedirs(model.BASE_DEFAULT, exist_ok=True)
            ctx["caso"] = model.Caso.crea(model.BASE_DEFAULT, nome, oper,
                                          campi["riferimento"].get_text().strip(), note)
            aggiorna_caso()
            stato.set_text(_t("cs.case_created") % ctx["caso"].dir)
        else:
            d.destroy()

    def on_apri(_w):
        casi = model.Caso.elenco()
        if not casi:
            info_dialog(_t("cs.no_cases"), _t("cs.no_cases_body") % model.BASE_DEFAULT,
                        "info", win)
            return
        d = Gtk.Dialog(title=_t("cs.open_case_title"), transient_for=win, modal=True)
        d.add_buttons(_t("v.cancel"), Gtk.ResponseType.CANCEL, _t("cs.open"), Gtk.ResponseType.OK)
        box = d.get_content_area(); box.set_margin_top(10); box.set_margin_start(12)
        box.set_margin_end(12); box.set_margin_bottom(10)
        combo = Gtk.ComboBoxText()
        for c in casi:
            combo.append(c.dir, "%s  (%s)" % (c.meta.get("nome", "?"),
                                              c.meta.get("aperto", "")[:10]))
        combo.set_active(0)
        box.pack_start(combo, False, False, 0)
        d.show_all()
        if d.run() == Gtk.ResponseType.OK and combo.get_active_id():
            ctx["caso"] = model.Caso(combo.get_active_id())
            aggiorna_caso()
            stato.set_text(_t("cs.case_opened"))
        d.destroy()

    # --- sequenza completa ------------------------------------------------
    def on_tutto(_w):
        if not serve_caso():
            return
        m, it = tv.get_selection().get_selected()
        if it is None:
            info_dialog(_t("cs.no_device"),
                        _t("cs.select_device"), "warning", win)
            return
        dev = m[it][0]
        desc = e_desc.get_text().strip()
        c = ctx["caso"]

        d = Gtk.MessageDialog(transient_for=win, modal=True,
                              message_type=Gtk.MessageType.QUESTION,
                              buttons=Gtk.ButtonsType.OK_CANCEL,
                              text=_t("cs.start_acq_q") % dev)
        d.format_secondary_text(_t("cs.start_acq_body"))
        risposta = d.run(); d.destroy()
        if risposta != Gtk.ResponseType.OK:
            return

        def sequenza(avanza):
            avanza(_t("cs.acquiring"))
            ok, img = c.acquisisci(dev, desc, avanza)
            if not ok:
                return (False, img)
            avanza(_t("cs.verifying"))
            ok_v, _ = c.verifica(img, avanza)
            avanza(_t("cs.analyzing"))
            c.analizza(img, avanza)
            avanza(_t("cs.generating"))
            report.genera(c)
            return (True, _t("cs.seq_done")
                    % (os.path.basename(img), _t("cs.passed") if ok_v else _t("cs.not_passed")))
        lavora(sequenza, _t("cs.full_seq"))

    def _dev_scelto():
        m, it = tv.get_selection().get_selected()
        if it is None:
            info_dialog(_t("cs.no_device"),
                        _t("cs.select_device_above"), "warning", win)
            return None
        return m[it][0]

    def _img_scelta():
        p = combo_img.get_active_id()
        if not p:
            info_dialog(_t("cs.no_image"),
                        _t("cs.no_image_body"), "warning", win)
        return p

    def on_acq(_w):
        if not serve_caso():
            return
        dev = _dev_scelto()
        if not dev:
            return
        desc = e_desc.get_text().strip()
        c = ctx["caso"]
        lavora(lambda a: c.acquisisci(dev, desc, a), _t("cs.tab_acq"))

    def on_ver(_w):
        if not serve_caso():
            return
        img = _img_scelta()
        if not img:
            return
        c = ctx["caso"]
        lavora(lambda a: c.verifica(img, a), _t("cs.verify"))

    def on_ana(_w):
        if not serve_caso():
            return
        img = _img_scelta()
        if not img:
            return
        c = ctx["caso"]
        lavora(lambda a: c.analizza(img, a), _t("cs.analysis"))

    def on_nota(_w):
        if not serve_caso():
            return
        b = tvnote.get_buffer()
        t = b.get_text(b.get_start_iter(), b.get_end_iter(), True).strip()
        if not t:
            return
        ctx["caso"].nota(t)
        b.set_text("")
        aggiorna_caso()
        stato.set_text(_t("cs.note_added"))

    def on_rel(_w):
        if not serve_caso():
            return
        lavora(lambda a: (True, report.genera(ctx["caso"])), _t("cs.report"))

    def on_apri_rel(_w):
        if not serve_caso():
            return
        p = os.path.join(ctx["caso"].dir, "relazione.html")
        if not os.path.isfile(p):
            info_dialog(_t("cs.report_missing"), _t("cs.generate_first"), "warning", win)
            return
        if have("nxs-browser"):
            run_bg(["nxs-browser", "file://" + p])
        else:
            webbrowser.open("file://" + p)

    def on_cart(_w):
        if serve_caso():
            run_bg(["pcmanfm", ctx["caso"].dir] if have("pcmanfm")
                   else ["xdg-open", ctx["caso"].dir])

    b_nuovo.connect("clicked", on_nuovo)
    b_apri.connect("clicked", on_apri)
    b_agg.connect("clicked", aggiorna_dispositivi)
    b_tutto.connect("clicked", on_tutto)
    b_acq.connect("clicked", on_acq)
    b_ver.connect("clicked", on_ver)
    b_ana.connect("clicked", on_ana)
    b_rel2.connect("clicked", on_rel)
    b_nota.connect("clicked", on_nota)
    b_rel.connect("clicked", on_rel)
    b_apri_rel.connect("clicked", on_apri_rel)
    b_cart.connect("clicked", on_cart)

    aggiorna_dispositivi()
    aggiorna_caso()
    win.show_all()
    return win


def main():
    w = open_case()
    w.connect("destroy", Gtk.main_quit)
    Gtk.main()


if __name__ == "__main__":
    main()
