# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""Impostazioni di NexusSec Browser (sul modello di Firefox).

Generale: pagina iniziale, cartella dei download (o "chiedi ogni volta"),
motore di ricerca. Aspetto: tema scuro. Privacy: avvio in modalita' anonima,
cancellazione dei dati di navigazione della modalita' normale (quella anonima
non ne lascia: vive solo in RAM). Tutto in ~/.nxs-browser/config.json.
"""
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, GLib, WebKit2  # noqa: E402

from nxs_browser.config import config
from nxs_browser.downloads import cartella_download, cartella_predefinita

try:
    from nxs_i18n import t as _t
except Exception:                # noqa: BLE001
    def _t(key, **kw):
        return key

# motori di ricerca: chiave -> (nome, URL con %s al posto dei termini)
MOTORI = {
    "duckduckgo": ("DuckDuckGo", "https://duckduckgo.com/?q=%s"),
    "startpage": ("Startpage", "https://www.startpage.com/do/search?q=%s"),
    "brave": ("Brave Search", "https://search.brave.com/search?q=%s"),
    "qwant": ("Qwant", "https://www.qwant.com/?q=%s"),
    "google": ("Google", "https://www.google.com/search?q=%s"),
    "bing": ("Bing", "https://www.bing.com/search?q=%s"),
}


def url_ricerca(termini: str) -> str:
    chiave = config.get("search_engine", "duckduckgo")
    modello = MOTORI.get(chiave, MOTORI["duckduckgo"])[1]
    return modello % GLib.uri_escape_string(termini, None, True)


def _sezione(testo):
    lab = Gtk.Label(label=testo)
    lab.set_xalign(0)
    lab.get_style_context().add_class("nxs-set-section")
    return lab


def _riga(griglia, r, etichetta, widget, nota=None):
    lab = Gtk.Label(label=etichetta)
    lab.set_xalign(0)
    lab.set_valign(Gtk.Align.CENTER)
    griglia.attach(lab, 0, r, 1, 1)
    widget.set_hexpand(True)
    griglia.attach(widget, 1, r, 1, 1)
    if nota:
        n = Gtk.Label(label=nota)
        n.set_xalign(0)
        n.set_line_wrap(True)
        n.set_max_width_chars(60)
        n.get_style_context().add_class("nxs-set-note")
        griglia.attach(n, 1, r + 1, 1, 1)
        return r + 2
    return r + 1


def apri_impostazioni(browser):
    """Dialogo modale; salva alla chiusura e riapplica tema/scelte al volo."""
    dlg = Gtk.Dialog(title=_t("br.set.title"), transient_for=browser, modal=True)
    dlg.set_default_size(620, -1)
    dlg.get_style_context().add_class("nxs-settings")
    dlg.add_button(_t("wel.close"), Gtk.ResponseType.CLOSE)
    area = dlg.get_content_area()
    area.set_border_width(16)
    area.set_spacing(8)

    g = Gtk.Grid(column_spacing=14, row_spacing=10)
    area.pack_start(g, True, True, 0)
    r = 0

    # --- Generale ---------------------------------------------------------------
    g.attach(_sezione(_t("br.set.general")), 0, r, 2, 1); r += 1
    home = Gtk.Entry()
    home.set_text(config.get("homepage", "https://duckduckgo.com"))
    b_cur = Gtk.Button(label=_t("br.set.use_current"))
    riga_home = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    riga_home.pack_start(home, True, True, 0)
    riga_home.pack_start(b_cur, False, False, 0)

    def usa_corrente(_w):
        v = browser.current_view()
        uri = v.get_uri() if v else ""
        if uri:
            home.set_text(uri)
    b_cur.connect("clicked", usa_corrente)
    r = _riga(g, r, _t("br.set.homepage"), riga_home)

    motore = Gtk.ComboBoxText()
    for k, (nome, _u) in MOTORI.items():
        motore.append(k, nome)
    motore.set_active_id(config.get("search_engine", "duckduckgo"))
    if motore.get_active_id() is None:
        motore.set_active_id("duckduckgo")
    r = _riga(g, r, _t("br.set.search"), motore)

    # --- Download ---------------------------------------------------------------
    g.attach(_sezione(_t("br.set.downloads")), 0, r, 2, 1); r += 1
    cartella = Gtk.FileChooserButton(title=_t("br.set.dl_dir"),
                                     action=Gtk.FileChooserAction.SELECT_FOLDER)
    try:
        cartella.set_filename(cartella_download())
    except Exception:            # noqa: BLE001
        pass
    b_pred = Gtk.Button(label=_t("br.set.default"))
    b_pred.set_tooltip_text(cartella_predefinita())
    b_pred.connect("clicked", lambda _w: cartella.set_filename(cartella_predefinita()))
    riga_dir = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    riga_dir.pack_start(cartella, True, True, 0)
    riga_dir.pack_start(b_pred, False, False, 0)
    r = _riga(g, r, _t("br.set.dl_dir"), riga_dir)
    chiedi = Gtk.CheckButton(label=_t("br.set.dl_ask"))
    chiedi.set_active(bool(config.get("download_ask", False)))
    cartella.set_sensitive(not chiedi.get_active())
    chiedi.connect("toggled", lambda w: cartella.set_sensitive(not w.get_active()))
    g.attach(chiedi, 1, r, 1, 1); r += 1

    # --- Aspetto e privacy ---------------------------------------------------------
    g.attach(_sezione(_t("br.set.look_privacy")), 0, r, 2, 1); r += 1
    scuro = Gtk.Switch(); scuro.set_halign(Gtk.Align.START)
    scuro.set_active(bool(config.get("dark_mode", True)))
    r = _riga(g, r, _t("br.set.dark"), scuro)
    anon = Gtk.Switch(); anon.set_halign(Gtk.Align.START)
    anon.set_active(bool(config.get("stealth", True)))
    r = _riga(g, r, _t("br.set.stealth"), anon, _t("br.set.stealth_note"))

    b_pulisci = Gtk.Button(label=_t("br.set.clear_data"))
    b_pulisci.set_halign(Gtk.Align.START)
    esito = Gtk.Label(); esito.set_xalign(0)
    esito.get_style_context().add_class("nxs-set-note")

    def pulisci(_w):
        ctx = browser._contexts.get(False)
        if ctx is None:
            ctx = browser._context(False)
        try:
            ctx.get_website_data_manager().clear(
                WebKit2.WebsiteDataTypes.ALL, 0, None,
                lambda m, res: (m.clear_finish(res), esito.set_text(_t("br.set.cleared"))))
        except Exception as e:   # noqa: BLE001
            esito.set_text(str(e))
    b_pulisci.connect("clicked", pulisci)
    riga_p = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    riga_p.pack_start(b_pulisci, False, False, 0)
    riga_p.pack_start(esito, True, True, 0)
    r = _riga(g, r, _t("br.set.data"), riga_p, _t("br.set.data_note"))

    dlg.show_all()
    home.set_position(-1)                     # niente testo tutto selezionato
    dlg.run()

    # --- salvataggio -------------------------------------------------------------------
    h = home.get_text().strip()
    if h:
        config.config["homepage"] = browser._normalize(h)
    config.config["search_engine"] = motore.get_active_id() or "duckduckgo"
    d = cartella.get_filename() or ""
    config.config["download_dir"] = "" if d == cartella_predefinita() else d
    config.config["download_ask"] = chiedi.get_active()
    config.save_config()
    if scuro.get_active() != browser.dark_mode:
        browser.toggle_theme()
    if anon.get_active() != browser.stealth:
        browser.toggle_stealth()
    dlg.destroy()
