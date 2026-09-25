# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""Cronologia di NexusSec Browser (solo modalita' normale).

La modalita' anonima NON registra nulla: e' il suo scopo. In quella normale
si ricordano le pagine visitate (fino a MAX voci, piu' recenti in testa) in
~/.nxs-browser/history.json, disattivabile dalle Impostazioni. Servono a:
  - suggerimenti mentre si scrive nella barra indirizzi (con i preferiti);
  - finestra Cronologia (Ctrl+H): cerca, apri, elimina voce, cancella tutto.
"""
import json
import time
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango  # noqa: E402

from nxs_browser.config import config

try:
    from nxs_i18n import t as _t
except Exception:                # noqa: BLE001
    def _t(key, **kw):
        return key

MAX = 5000
FILE = Path.home() / ".nxs-browser" / "history.json"
_ESCLUSI = ("about:", "data:", "file:", "view-source:")


class Cronologia:
    def __init__(self):
        self.voci = []                 # [{"url", "title", "t", "n"}]
        try:
            self.voci = json.loads(FILE.read_text())
        except (OSError, ValueError):
            self.voci = []
        self._da_salvare = False
        # modello per i suggerimenti della barra indirizzi: (titolo, url)
        self.modello = Gtk.ListStore(str, str)
        self._ricostruisci_modello()

    def attiva(self):
        return bool(config.get("history", True))

    def registra(self, url, titolo=""):
        if not self.attiva() or not url or url.startswith(_ESCLUSI):
            return
        for i, v in enumerate(self.voci):
            if v.get("url") == url:
                v["t"] = time.time()
                v["n"] = v.get("n", 1) + 1
                if titolo:
                    v["title"] = titolo
                self.voci.insert(0, self.voci.pop(i))
                break
        else:
            self.voci.insert(0, {"url": url, "title": titolo, "t": time.time(), "n": 1})
            del self.voci[MAX:]
        self._salva()

    def titolo(self, url, titolo):
        """Il titolo arriva dopo l'URL: aggiorna la voce appena registrata."""
        if not titolo or not self.voci or not self.attiva():
            return
        for v in self.voci[:5]:
            if v.get("url") == url and v.get("title") != titolo:
                v["title"] = titolo
                self._salva()
                return

    def elimina(self, url):
        self.voci = [v for v in self.voci if v.get("url") != url]
        self._salva()

    def cancella_tutto(self):
        self.voci = []
        self._salva()

    def _salva(self):
        self._ricostruisci_modello()
        try:
            FILE.parent.mkdir(exist_ok=True)
            tmp = FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.voci, ensure_ascii=False))
            tmp.replace(FILE)
        except OSError:
            pass

    def _ricostruisci_modello(self, preferiti=()):
        self.modello.clear()
        visti = set()
        for titolo, url in preferiti:
            if url not in visti:
                visti.add(url)
                self.modello.append(["★ " + (titolo or url), url])
        # le piu' visitate prima, poi le piu' recenti
        for v in sorted(self.voci, key=lambda v: (-v.get("n", 1), -v.get("t", 0)))[:1500]:
            if v["url"] not in visti:
                visti.add(v["url"])
                self.modello.append([v.get("title") or v["url"], v["url"]])

    def aggiorna_preferiti(self, preferiti):
        self._ricostruisci_modello(preferiti)


def completamento(cronologia, on_scelta):
    """Gtk.EntryCompletion per la barra indirizzi: cerca nel titolo e
    nell'URL (non solo l'inizio), mostra titolo + indirizzo."""
    c = Gtk.EntryCompletion()
    c.set_model(cronologia.modello)
    c.set_minimum_key_length(2)
    c.set_popup_set_width(True)
    c.set_inline_completion(False)

    def corrisponde(_c, chiave, it):
        chiave = chiave.lower().strip()
        m = cronologia.modello
        return chiave in (m[it][0] or "").lower() or chiave in (m[it][1] or "").lower()
    c.set_match_func(corrisponde)

    r1 = Gtk.CellRendererText()
    r1.set_property("ellipsize", Pango.EllipsizeMode.END)
    r1.set_property("width-chars", 40)
    c.pack_start(r1, True)
    c.add_attribute(r1, "text", 0)
    r2 = Gtk.CellRendererText()
    r2.set_property("ellipsize", Pango.EllipsizeMode.MIDDLE)
    r2.set_property("foreground", "#8f8f9d")
    r2.set_property("width-chars", 40)
    c.pack_start(r2, True)
    c.add_attribute(r2, "text", 1)

    def scelto(_c, m, it):
        on_scelta(m[it][1])
        return True
    c.connect("match-selected", scelto)
    return c


def apri_finestra(browser, cronologia):
    """Finestra Cronologia: ricerca, elenco, apri/elimina, cancella tutto."""
    w = Gtk.Dialog(title=_t("br.hist.title"), transient_for=browser, modal=False)
    w.set_default_size(720, 520)
    w.get_style_context().add_class("nxs-settings")
    area = w.get_content_area()
    area.set_border_width(12)
    area.set_spacing(8)

    cerca = Gtk.SearchEntry()
    cerca.set_placeholder_text(_t("br.hist.search"))
    area.pack_start(cerca, False, False, 0)

    st = Gtk.ListStore(str, str, str)             # quando, titolo, url
    filtro = st.filter_new()
    filtro.set_visible_func(lambda m, it, _d: (
        not cerca.get_text().strip()
        or cerca.get_text().lower() in (m[it][1] or "").lower()
        or cerca.get_text().lower() in (m[it][2] or "").lower()))
    tv = Gtk.TreeView(model=filtro)
    for i, (tit, esp) in enumerate(((_t("br.hist.when"), False),
                                    (_t("br.title_label").rstrip(":"), True),
                                    ("URL", True))):
        r = Gtk.CellRendererText()
        r.set_property("ellipsize", Pango.EllipsizeMode.END)
        col = Gtk.TreeViewColumn(tit, r, text=i)
        col.set_expand(esp)
        col.set_resizable(True)
        tv.append_column(col)
    sc = Gtk.ScrolledWindow()
    sc.set_vexpand(True)
    sc.add(tv)
    area.pack_start(sc, True, True, 0)

    def ricarica():
        st.clear()
        for v in cronologia.voci:
            quando = time.strftime("%d/%m/%Y %H:%M", time.localtime(v.get("t", 0)))
            st.append([quando, v.get("title") or "", v.get("url", "")])
    ricarica()
    cerca.connect("search-changed", lambda _e: filtro.refilter())

    def selezionato():
        m, it = tv.get_selection().get_selected()
        return m[it][2] if it else None

    def apri(*_a):
        u = selezionato()
        if u:
            browser.new_tab(u)
    tv.connect("row-activated", apri)

    piede = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    b_apri = Gtk.Button(label=_t("br.open_new_tab"))
    b_apri.connect("clicked", apri)
    b_del = Gtk.Button(label=_t("br.hist.delete"))

    def elimina(_w):
        u = selezionato()
        if u:
            cronologia.elimina(u)
            ricarica()
    b_del.connect("clicked", elimina)
    b_all = Gtk.Button(label=_t("br.hist.clear_all"))

    def tutto(_w):
        d = Gtk.MessageDialog(transient_for=w, modal=True,
                              message_type=Gtk.MessageType.QUESTION,
                              buttons=Gtk.ButtonsType.YES_NO,
                              text=_t("br.hist.clear_q"))
        if d.run() == Gtk.ResponseType.YES:
            cronologia.cancella_tutto()
            ricarica()
        d.destroy()
    b_all.connect("clicked", tutto)
    b_chiudi = Gtk.Button(label=_t("wel.close"))
    b_chiudi.connect("clicked", lambda _w: w.destroy())
    for b in (b_apri, b_del):
        piede.pack_start(b, False, False, 0)
    piede.pack_end(b_chiudi, False, False, 0)
    piede.pack_end(b_all, False, False, 0)
    area.pack_start(piede, False, False, 0)
    w.show_all()
