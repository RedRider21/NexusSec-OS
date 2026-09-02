"""Gestore dischi di NexusSec - interfaccia GTK3.

Riusa lo stile del Centro di Controllo (nxs_cc.common) per restare coerente col
resto del desktop e col colore del profilo attivo.

La GUI e' volutamente sottile: tutta la logica sta in model.py (enumerazione) e
mount.py (montaggio). Cosi' il giorno in cui il file manager Python di Vesper
avra' la sua barra "Dispositivi" bastera' importare model.py, senza portarsi
dietro nulla di questa finestra.

Impostazione FORENSIC: il pulsante grande e' "Monta sola lettura". Il montaggio
in scrittura c'e', ma chiede conferma e lo dice chiaramente.
"""
from __future__ import annotations

import threading

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Pango  # noqa: E402

from nxs_cc.common import panel_window, icon_button, have, run_bg
from nxs_disks import model, mount


def _riga_dettaglio(griglia, r, etichetta, valore):
    k = Gtk.Label(label=etichetta)
    k.set_xalign(0)
    k.get_style_context().add_class("nxs-key")
    v = Gtk.Label(label=valore or "-")
    v.set_xalign(0)
    v.set_selectable(True)
    v.set_ellipsize(Pango.EllipsizeMode.END)
    v.get_style_context().add_class("nxs-val")
    griglia.attach(k, 0, r, 1, 1)
    griglia.attach(v, 1, r, 1, 1)
    return v


def open_disks(_btn=None):
    win, body = panel_window("Dischi", 760, 620)

    intro = Gtk.Label(
        label="I dischi si vedono sempre, ma NON vengono mai montati da soli: "
              "NexusSec e' anche una distro forensic. Il montaggio e' sempre "
              "una tua scelta esplicita e avviene in SOLA LETTURA, salvo tu "
              "chieda diversamente.")
    intro.set_xalign(0)
    intro.set_line_wrap(True)
    intro.get_style_context().add_class("nxs-val")
    body.pack_start(intro, False, False, 0)

    # --- elenco ad albero: disco -> partizioni --------------------------
    # colonne: percorso(nascosto), dispositivo, dimensione, filesystem,
    #          etichetta, montato
    store = Gtk.TreeStore(str, str, str, str, str, str)
    tree = Gtk.TreeView(model=store)
    tree.set_headers_visible(True)
    for i, (titolo, col) in enumerate(
            (("Dispositivo", 1), ("Dimensione", 2), ("Filesystem", 3),
             ("Etichetta", 4), ("Montato in", 5))):
        rend = Gtk.CellRendererText()
        rend.set_property("ellipsize", Pango.EllipsizeMode.END)
        c = Gtk.TreeViewColumn(titolo, rend, text=col)
        c.set_resizable(True)
        if col == 1:
            c.set_min_width(150)
        tree.append_column(c)

    sc = Gtk.ScrolledWindow()
    sc.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    sc.set_size_request(-1, 240)
    sc.add(tree)
    body.pack_start(sc, True, True, 0)

    stato = Gtk.Label(label="")
    stato.set_xalign(0)
    stato.set_line_wrap(True)
    stato.get_style_context().add_class("nxs-val")

    # --- dettaglio del selezionato --------------------------------------
    det = Gtk.Grid(column_spacing=12, row_spacing=4)
    det.set_margin_top(8)
    body.pack_start(det, False, False, 0)
    v_perc = _riga_dettaglio(det, 0, "Percorso", "-")
    v_tipo = _riga_dettaglio(det, 1, "Tipo", "-")
    v_uuid = _riga_dettaglio(det, 2, "UUID", "-")
    v_uso = _riga_dettaglio(det, 3, "Spazio", "-")
    v_smart = _riga_dettaglio(det, 4, "SMART", "-")
    v_prot = _riga_dettaglio(det, 5, "Protezione", "-")

    body.pack_start(stato, False, False, 0)

    azioni = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    azioni.set_margin_top(6)
    body.pack_start(azioni, False, False, 0)
    azioni2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    body.pack_start(azioni2, False, False, 0)

    b_ro = icon_button("Monta sola lettura", "drive-harddisk-symbolic", primary=True)
    b_rw = icon_button("Monta in scrittura", "dialog-warning-symbolic")
    b_um = icon_button("Smonta", "media-eject-symbolic")
    b_apri = icon_button("Apri cartella", "folder-open-symbolic")
    for b in (b_ro, b_rw, b_um, b_apri):
        azioni.pack_start(b, False, False, 0)

    b_prot = icon_button("Blocca scrittura", "changes-prevent-symbolic")
    b_img = icon_button("Immagine dd...", "media-floppy-symbolic")
    b_agg = icon_button("Aggiorna", "view-refresh-symbolic")
    for b in (b_prot, b_img, b_agg):
        azioni2.pack_start(b, False, False, 0)

    ctx = {"nodi": [], "sel": None, "busy": False}

    # --- costruzione elenco ---------------------------------------------
    def ricarica(_w=None):
        sel_path = ctx["sel"].path if ctx["sel"] else None
        store.clear()
        ctx["nodi"] = model.list_devices()
        iter_da_riselezionare = [None]

        def aggiungi(n, padre):
            it = store.append(padre, [
                n.path,
                n.name if padre is None else "   " + n.name,
                model.human(n.size),
                n.fstype or ("-" if n.is_disk else "(nessuno)"),
                n.label or (n.model if n.is_disk else ""),
                n.mountpoint or "",
            ])
            if n.path == sel_path:
                iter_da_riselezionare[0] = it
            for c in n.children:
                aggiungi(c, it)

        for d in ctx["nodi"]:
            aggiungi(d, None)
        tree.expand_all()
        if iter_da_riselezionare[0] is not None:
            tree.get_selection().select_iter(iter_da_riselezionare[0])
        else:
            aggiorna_dettaglio()

    def nodo_selezionato():
        m, it = tree.get_selection().get_selected()
        if it is None:
            return None
        return model.find(ctx["nodi"], m[it][0])

    def aggiorna_dettaglio(*_a):
        n = nodo_selezionato()
        ctx["sel"] = n
        if n is None:
            for v in (v_perc, v_tipo, v_uuid, v_uso, v_smart, v_prot):
                v.set_text("-")
            for b in (b_ro, b_rw, b_um, b_apri, b_prot, b_img):
                b.set_sensitive(False)
            return
        v_perc.set_text(n.path)
        v_tipo.set_text("%s  %s" % (n.type, n.descrizione))
        v_uuid.set_text(n.uuid or "-")

        u = model.uso(n.mountpoint) if n.mounted else None
        v_uso.set_text("%s usati su %s" % (model.human(u[0]), model.human(u[1]))
                       if u else "-")
        v_prot.set_text("BLOCCATA in scrittura" if model.protetto_in_scrittura(n.path)
                        else "scrivibile")
        v_smart.set_text("(lettura in corso...)" if n.is_disk else "-")
        if n.is_disk:
            def leggi_smart(path=n.path):
                s = model.smart(path)
                def mostra():
                    if ctx["sel"] is not None and ctx["sel"].path == path:
                        if s is None:
                            v_smart.set_text("non disponibile")
                        else:
                            ore = ("  -  %s ore di accensione" % s["ore"]) if s["ore"] else ""
                            v_smart.set_text("%s%s" % (s["stato"], ore))
                    return False
                GLib.idle_add(mostra)
            threading.Thread(target=leggi_smart, daemon=True).start()

        montabile = n.mountable and not n.mounted and not ctx["busy"]
        b_ro.set_sensitive(montabile)
        b_rw.set_sensitive(montabile)
        b_um.set_sensitive(n.mounted and not ctx["busy"])
        b_apri.set_sensitive(n.mounted)
        b_prot.set_sensitive(n.is_disk and not ctx["busy"])
        b_img.set_sensitive(not ctx["busy"])
        b_prot.set_label("Sblocca scrittura" if model.protetto_in_scrittura(n.path)
                         else "Blocca scrittura")

    tree.get_selection().connect("changed", aggiorna_dettaglio)

    # --- operazioni (in thread: non bloccano la finestra) ----------------
    def esegui(fn, msg_attesa):
        ctx["busy"] = True
        stato.set_text(msg_attesa)
        for b in (b_ro, b_rw, b_um, b_prot, b_img):
            b.set_sensitive(False)

        def worker():
            ok, msg = fn()
            def fine():
                ctx["busy"] = False
                stato.set_text(("OK - %s" if ok else "Errore: %s") % msg)
                ricarica()
                return False
            GLib.idle_add(fine)
        threading.Thread(target=worker, daemon=True).start()

    def on_ro(_w):
        n = ctx["sel"]
        if n:
            esegui(lambda: mount.mount_ro(n), "Montaggio in sola lettura di %s..." % n.path)

    def on_rw(_w):
        n = ctx["sel"]
        if not n:
            return
        d = Gtk.MessageDialog(transient_for=win, modal=True,
                              message_type=Gtk.MessageType.WARNING,
                              buttons=Gtk.ButtonsType.OK_CANCEL,
                              text="Montare %s in SCRITTURA?" % n.path)
        d.format_secondary_text(
            "Il contenuto del disco potra' essere modificato. Su un disco da "
            "esaminare questo ne altera lo stato e puo' comprometterne il "
            "valore probatorio.\n\nSe ti serve solo leggere, annulla e usa "
            "\"Monta sola lettura\".")
        r = d.run()
        d.destroy()
        if r == Gtk.ResponseType.OK:
            esegui(lambda: mount.mount_rw(n), "Montaggio in scrittura di %s..." % n.path)

    def on_um(_w):
        n = ctx["sel"]
        if n:
            esegui(lambda: mount.smonta(n), "Smontaggio di %s..." % n.mountpoint)

    def on_prot(_w):
        n = ctx["sel"]
        if not n:
            return
        attiva = not model.protetto_in_scrittura(n.path)
        esegui(lambda: mount.write_protect(n.path, attiva),
               "%s la protezione in scrittura..." % ("Attivo" if attiva else "Rimuovo"))

    def on_apri(_w):
        n = ctx["sel"]
        if n and n.mounted:
            run_bg(["pcmanfm", n.mountpoint] if have("pcmanfm") else ["xdg-open", n.mountpoint])

    def on_img(_w):
        """Immagine grezza del dispositivo. Gira in un TERMINALE, non qui:
        dd puo' durare ore e l'avanzamento va visto (status=progress)."""
        n = ctx["sel"]
        if not n:
            return
        ch = Gtk.FileChooserDialog(title="Salva l'immagine di %s" % n.path,
                                   transient_for=win,
                                   action=Gtk.FileChooserAction.SAVE)
        ch.add_buttons("Annulla", Gtk.ResponseType.CANCEL, "Salva", Gtk.ResponseType.OK)
        ch.set_current_name("%s.img" % n.name)
        r = ch.run()
        dest = ch.get_filename()
        ch.destroy()
        if r != Gtk.ResponseType.OK or not dest:
            return
        cmd = ("doas dd if=%s of=%s bs=4M conv=noerror,sync status=progress; "
               "echo; echo 'Premi Invio per chiudere'; read x" % (n.path, dest))
        if have("lxterminal"):
            run_bg(["lxterminal", "-e", cmd])
        else:
            run_bg(["xterm", "-e", cmd])
        stato.set_text("Copia avviata in una finestra di terminale.")

    b_ro.connect("clicked", on_ro)
    b_rw.connect("clicked", on_rw)
    b_um.connect("clicked", on_um)
    b_prot.connect("clicked", on_prot)
    b_apri.connect("clicked", on_apri)
    b_img.connect("clicked", on_img)
    b_agg.connect("clicked", ricarica)

    ricarica()
    win.show_all()
    return win


def main():
    win = open_disks()
    win.connect("destroy", Gtk.main_quit)
    Gtk.main()


if __name__ == "__main__":
    main()
