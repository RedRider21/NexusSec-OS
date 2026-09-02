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
    win, body = panel_window("Casi forensi", 860, 700)
    ctx = {"caso": None, "busy": False}

    intro = _lab("Ogni operazione viene registrata da sola nella catena di custodia "
                 "con orario UTC, strumento e hash: il verbale non dipende da cosa "
                 "ti ricordi di annotare. I dischi restano protetti in scrittura "
                 "per tutta l'acquisizione.")
    body.pack_start(intro, False, False, 0)

    # ---- barra del caso corrente ----------------------------------------
    barra = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    barra.set_margin_top(6)
    lbl_caso = _lab("Nessun caso aperto", "nxs-key", wrap=False)
    barra.pack_start(lbl_caso, True, True, 0)
    b_nuovo = icon_button("Nuovo caso", "document-new-symbolic", primary=True)
    b_apri = icon_button("Apri", "document-open-symbolic")
    barra.pack_start(b_nuovo, False, False, 0)
    barra.pack_start(b_apri, False, False, 0)
    body.pack_start(barra, False, False, 0)

    nb = Gtk.Notebook()
    nb.set_margin_top(10)
    body.pack_start(nb, True, True, 0)

    # ================= 1. ACQUISIZIONE =================
    pg1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    pg1.set_margin_top(10); pg1.set_margin_start(6); pg1.set_margin_end(6)
    pg1.pack_start(_lab("Scegli il dispositivo da acquisire. Viene copiato in formato "
                        "E01, che incorpora nell'immagine i dati del caso e gli hash, "
                        "e viene poi riverificato."), False, False, 0)
    store_dev = Gtk.ListStore(str, str, str)          # percorso, dim, descrizione
    tv = Gtk.TreeView(model=store_dev)
    for i, t in enumerate(("Dispositivo", "Dimensione", "Contenuto")):
        r = Gtk.CellRendererText()
        r.set_property("ellipsize", Pango.EllipsizeMode.END)
        tv.append_column(Gtk.TreeViewColumn(t, r, text=i))
    sc = Gtk.ScrolledWindow(); sc.set_size_request(-1, 150); sc.add(tv)
    sc.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    pg1.pack_start(sc, False, False, 0)

    rowd = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    rowd.pack_start(_lab("Descrizione del reperto:", "nxs-key", wrap=False), False, False, 0)
    e_desc = Gtk.Entry(); e_desc.set_placeholder_text("es. disco interno del portatile sequestrato")
    rowd.pack_start(e_desc, True, True, 0)
    pg1.pack_start(rowd, False, False, 0)

    az1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    b_tutto = icon_button("Esegui tutto (acquisisci, verifica, analizza, relazione)",
                          "media-playback-start-symbolic", primary=True)
    b_agg = icon_button("Aggiorna elenco", "view-refresh-symbolic")
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
    pg1.pack_start(_lab("Oppure esegui un singolo passo:", "nxs-key", wrap=False),
                   False, False, 0)

    rowi = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    rowi.pack_start(_lab("Immagine del caso:", "nxs-key", wrap=False), False, False, 0)
    combo_img = Gtk.ComboBoxText()
    rowi.pack_start(combo_img, True, True, 0)
    pg1.pack_start(rowi, False, False, 0)

    passi = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    b_acq = icon_button("1 · Acquisisci", "drive-harddisk-symbolic")
    b_ver = icon_button("2 · Verifica", "security-high-symbolic")
    b_ana = icon_button("3 · Analizza", "system-search-symbolic")
    b_rel2 = icon_button("4 · Relazione", "document-properties-symbolic")
    for b in (b_acq, b_ver, b_ana, b_rel2):
        passi.pack_start(b, True, True, 0)
    pg1.pack_start(passi, False, False, 0)
    nb.append_page(pg1, Gtk.Label(label="Acquisizione"))

    # ================= 2. NOTE =================
    pg2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    pg2.set_margin_top(10); pg2.set_margin_start(6); pg2.set_margin_end(6)
    pg2.pack_start(_lab("Le note finiscono nella catena di custodia con l'orario: "
                        "servono a spiegare le scelte fatte (perche' un disco e' "
                        "stato escluso, dove e' stato reperito, chi era presente)."),
                   False, False, 0)
    tvnote = Gtk.TextView(); tvnote.set_wrap_mode(Gtk.WrapMode.WORD)
    scn = Gtk.ScrolledWindow(); scn.set_size_request(-1, 120); scn.add(tvnote)
    pg2.pack_start(scn, False, False, 0)
    b_nota = icon_button("Aggiungi al verbale", "list-add-symbolic")
    pg2.pack_start(b_nota, False, False, 0)
    pg2.pack_start(_lab("Catena di custodia:", "nxs-key", wrap=False), False, False, 0)
    store_log = Gtk.ListStore(str, str, str)
    tvlog = Gtk.TreeView(model=store_log)
    for i, t in enumerate(("Quando (UTC)", "Azione", "Dettagli")):
        r = Gtk.CellRendererText()
        r.set_property("ellipsize", Pango.EllipsizeMode.END)
        tvlog.append_column(Gtk.TreeViewColumn(t, r, text=i))
    scl = Gtk.ScrolledWindow(); scl.set_size_request(-1, 200); scl.add(tvlog)
    scl.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    pg2.pack_start(scl, True, True, 0)
    nb.append_page(pg2, Gtk.Label(label="Verbale"))

    # ================= 3. RELAZIONE =================
    pg3 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    pg3.set_margin_top(10); pg3.set_margin_start(6); pg3.set_margin_end(6)
    pg3.pack_start(_lab("La relazione raccoglie dati del caso, reperti con i "
                        "rispettivi hash, catena di custodia integrale, partizioni "
                        "e cronologia. E' un file HTML autonomo: si apre ovunque e "
                        "si stampa in PDF dal browser."), False, False, 0)
    az3 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    b_rel = icon_button("Genera relazione", "document-properties-symbolic", primary=True)
    b_apri_rel = icon_button("Apri relazione", "document-open-symbolic")
    b_cart = icon_button("Apri cartella del caso", "folder-open-symbolic")
    for b in (b_rel, b_apri_rel, b_cart):
        az3.pack_start(b, False, False, 0)
    pg3.pack_start(az3, False, False, 0)
    nb.append_page(pg3, Gtk.Label(label="Relazione"))

    # ---- avanzamento -----------------------------------------------------
    prog = Gtk.ProgressBar(); prog.set_show_text(True); prog.set_text("")
    body.pack_start(prog, False, False, 0)
    stato = _lab("")
    body.pack_start(stato, False, False, 0)

    # ---- funzioni --------------------------------------------------------
    def aggiorna_dispositivi(_w=None):
        store_dev.clear()
        if dmodel is None:
            store_dev.append(["(nxs_disks non disponibile)", "", ""])
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
            combo_img.append("", "(nessuna immagine: esegui prima il passo 1)")
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
            lbl_caso.set_text("Nessun caso aperto")
            store_log.clear()
            return
        lbl_caso.set_text("Caso: %s   ·   operatore: %s   ·   %s"
                          % (c.meta.get("nome", "-"), c.meta.get("operatore", "-"), c.dir))
        store_log.clear()
        for r in c.righe_registro():
            store_log.append([r[0] if len(r) > 0 else "",
                              r[1] if len(r) > 1 else "",
                              r[2] if len(r) > 2 else ""])

    def serve_caso():
        if ctx["caso"] is None:
            info_dialog("Nessun caso aperto",
                        "Crea o apri un caso prima di procedere: senza caso non "
                        "esiste una catena di custodia dove registrare le operazioni.",
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
                prog.set_text("Completato" if ok else "Interrotto")
                stato.set_text(("OK — %s" if ok else "Errore: %s") % msg)
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
        d = Gtk.Dialog(title="Nuovo caso", transient_for=win, modal=True)
        d.add_buttons("Annulla", Gtk.ResponseType.CANCEL, "Crea", Gtk.ResponseType.OK)
        box = d.get_content_area()
        box.set_spacing(6); box.set_margin_top(10); box.set_margin_bottom(10)
        box.set_margin_start(12); box.set_margin_end(12)
        campi = {}
        for chiave, etichetta, segnaposto in (
                ("nome", "Denominazione", "es. Accertamento portatile Rossi"),
                ("operatore", "Operatore", "nome di chi esegue"),
                ("riferimento", "Riferimento", "numero di pratica o fascicolo")):
            box.pack_start(_lab(etichetta, "nxs-key", wrap=False), False, False, 0)
            e = Gtk.Entry(); e.set_placeholder_text(segnaposto)
            box.pack_start(e, False, False, 0)
            campi[chiave] = e
        box.pack_start(_lab("Note iniziali", "nxs-key", wrap=False), False, False, 0)
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
                info_dialog("Dati mancanti",
                            "Denominazione e operatore sono obbligatori: senza, la "
                            "relazione non e' attribuibile a nessuno.", "warning", win)
                return
            os.makedirs(model.BASE_DEFAULT, exist_ok=True)
            ctx["caso"] = model.Caso.crea(model.BASE_DEFAULT, nome, oper,
                                          campi["riferimento"].get_text().strip(), note)
            aggiorna_caso()
            stato.set_text("Caso creato in %s" % ctx["caso"].dir)
        else:
            d.destroy()

    def on_apri(_w):
        casi = model.Caso.elenco()
        if not casi:
            info_dialog("Nessun caso", "Non ci sono casi in %s." % model.BASE_DEFAULT,
                        "info", win)
            return
        d = Gtk.Dialog(title="Apri caso", transient_for=win, modal=True)
        d.add_buttons("Annulla", Gtk.ResponseType.CANCEL, "Apri", Gtk.ResponseType.OK)
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
            stato.set_text("Caso aperto")
        d.destroy()

    # --- sequenza completa ------------------------------------------------
    def on_tutto(_w):
        if not serve_caso():
            return
        m, it = tv.get_selection().get_selected()
        if it is None:
            info_dialog("Nessun dispositivo",
                        "Seleziona il dispositivo da acquisire.", "warning", win)
            return
        dev = m[it][0]
        desc = e_desc.get_text().strip()
        c = ctx["caso"]

        d = Gtk.MessageDialog(transient_for=win, modal=True,
                              message_type=Gtk.MessageType.QUESTION,
                              buttons=Gtk.ButtonsType.OK_CANCEL,
                              text="Avviare l'acquisizione di %s?" % dev)
        d.format_secondary_text(
            "Verranno eseguiti in sequenza: protezione in scrittura, copia in "
            "formato E01, verifica degli hash, analisi (partizioni e cronologia) "
            "e generazione della relazione.\n\nSu un disco di grandi dimensioni "
            "l'operazione puo' durare ore. La finestra resta utilizzabile.")
        risposta = d.run(); d.destroy()
        if risposta != Gtk.ResponseType.OK:
            return

        def sequenza(avanza):
            avanza("Acquisizione in corso...")
            ok, img = c.acquisisci(dev, desc, avanza)
            if not ok:
                return (False, img)
            avanza("Verifica degli hash...")
            ok_v, _ = c.verifica(img, avanza)
            avanza("Analisi: partizioni e cronologia...")
            c.analizza(img, avanza)
            avanza("Generazione della relazione...")
            report.genera(c)
            return (True, "acquisizione %s, verifica %s, relazione pronta"
                    % (os.path.basename(img), "superata" if ok_v else "NON superata"))
        lavora(sequenza, "Sequenza completa")

    def _dev_scelto():
        m, it = tv.get_selection().get_selected()
        if it is None:
            info_dialog("Nessun dispositivo",
                        "Seleziona il dispositivo nell'elenco qui sopra.", "warning", win)
            return None
        return m[it][0]

    def _img_scelta():
        p = combo_img.get_active_id()
        if not p:
            info_dialog("Nessuna immagine",
                        "Questo caso non ha ancora immagini acquisite. Esegui prima "
                        "il passo 1, oppure apri un caso che ne contenga.", "warning", win)
        return p

    def on_acq(_w):
        if not serve_caso():
            return
        dev = _dev_scelto()
        if not dev:
            return
        desc = e_desc.get_text().strip()
        c = ctx["caso"]
        lavora(lambda a: c.acquisisci(dev, desc, a), "Acquisizione")

    def on_ver(_w):
        if not serve_caso():
            return
        img = _img_scelta()
        if not img:
            return
        c = ctx["caso"]
        lavora(lambda a: c.verifica(img, a), "Verifica")

    def on_ana(_w):
        if not serve_caso():
            return
        img = _img_scelta()
        if not img:
            return
        c = ctx["caso"]
        lavora(lambda a: c.analizza(img, a), "Analisi")

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
        stato.set_text("Nota messa a verbale")

    def on_rel(_w):
        if not serve_caso():
            return
        lavora(lambda a: (True, report.genera(ctx["caso"])), "Relazione")

    def on_apri_rel(_w):
        if not serve_caso():
            return
        p = os.path.join(ctx["caso"].dir, "relazione.html")
        if not os.path.isfile(p):
            info_dialog("Relazione assente", "Generala prima.", "warning", win)
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
