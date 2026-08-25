"""NexusSec Browser - interfaccia GTK3 + WebKit2.

Port fedele del browser originale (PyQt5/QtWebEngine) sullo stack nativo di
NexusSec: GTK3 + WebKit2 (PyGObject). Stesse funzioni dell'originale:
  - tab multiple chiudibili con titolo e favicon
  - sidebar dei preferiti (aggiungi/modifica/elimina/aggiorna, collassabile)
  - barra URL intelligente con progress
  - navigazione completa (indietro/avanti/ricarica/home) e zoom
  - tema chiaro/scuro con persistenza
  - inspector (DevTools nativi di WebKit, F12)

QtWebEngine (Chromium) non e' disponibile su TinyCore (python3.9, niente
tcz/ABI): WebKit2GTK e' la resa equivalente e nativa per lo stack NexusSec.
"""

import json
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf, WebKit2  # noqa: E402

from nxs_browser.config import config

APP_NAME = "NexusSec Browser"

# ---------------------------------------------------------------------------
# Modalita' STEALTH (anonima) - attiva di default.
#   ON  = contesto effimero (niente cookie/cronologia/cache su disco)
#         + traffico via Tor (SOCKS 9050, IP nascosto)
#         + anti-leak (WebRTC off, User-Agent generico, no geoloc/prefetch).
#   OFF = browser normale: memorizza cookie/cronologia/cache in ~/.nxs-browser,
#         connessione diretta.
# L'interruttore in barra commuta le NUOVE schede e ricarica quella corrente
# (il contesto e' fissato alla creazione della WebView, non modificabile a caldo).
# ---------------------------------------------------------------------------
TOR_HOST, TOR_PORT = "127.0.0.1", 9050
TOR_SOCKS = "socks://%s:%d" % (TOR_HOST, TOR_PORT)
# UA generico e diffuso: ci confonde nella massa (niente stringa "NexusSec/WebKit").
STEALTH_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) "
              "Gecko/20100101 Firefox/128.0")
# Larghezza sidebar espansa: deve bastare a "Preferiti" + pulsanti intestazione
# e alle etichette titolo/URL dei preferiti senza tagliarle. SIDEBAR_MIN = stato
# collassato (solo le icone dei preferiti restano visibili).
SIDEBAR_W = 250
SIDEBAR_MIN = 60


# ---------------------------------------------------------------------------
# Temi (palette dell'originale: chiaro default, scuro stile VS Code Dark+)
# ---------------------------------------------------------------------------
CSS_LIGHT = b"""
.nxs-browser { background: #eef1f5; color: #1e2833;
  font-family: "DejaVu Sans", "Cantarell", sans-serif; }
.nxs-toolbar { background: #f4f6f9; padding: 7px 8px; }
.nxs-toolbar button { background: transparent; border: none; border-radius: 9px;
  padding: 6px 8px; color: #1e2833; box-shadow: none; outline: none;
  transition: background 120ms ease, color 120ms ease; }
.nxs-toolbar button:hover { background: #e4e9ef; }
.nxs-urlbar { border: 1px solid #d3dae2; border-radius: 16px; padding: 7px 16px;
  background: #ffffff; color: #1e2833; }
.nxs-urlbar:focus { border-color: #b9c4d0; }
.nxs-sidebar { background: #f4f6f9; border-right: 1px solid #e2e7ee; }
.nxs-sidebar-head { background: #f4f6f9; padding: 7px 8px; }
.nxs-sidebar-head button { padding: 3px 5px; min-width: 0; min-height: 0; margin: 0;
  border-radius: 8px; }
.nxs-bm-list { background: #ffffff; color: #1e2833; padding: 4px; }
.nxs-bm-list row { border-radius: 9px; padding: 3px; margin: 1px 2px; }
.nxs-bm-list row:hover { background: #eef1f5; }
.nxs-bm-list row:selected { background: #e6ebf1; }
.nxs-bm-title { font-weight: 600; }
.nxs-bm-url { color: #8595a5; font-size: 8pt; }
notebook header { background: #f4f6f9; border: none; }
notebook tab { padding: 6px 12px; margin: 2px 1px 0 1px; color: #6b7a89;
  border-radius: 8px 8px 0 0; }
notebook tab:hover { background: #e9edf2; }
notebook tab:checked { color: #1e2833; font-weight: 600; background: #ffffff; }
menubar { background: #eef1f5; color: #1e2833; }
menubar > menuitem { padding: 4px 10px; border-radius: 8px; }
menubar > menuitem:hover { background: #e4e9ef; }
menu { background: #ffffff; color: #1e2833; border: 1px solid #e2e7ee;
  border-radius: 10px; padding: 4px; }
menu menuitem { border-radius: 7px; padding: 5px 10px; }
paned > separator { background: #e2e7ee; min-width: 1px; min-height: 1px; }
"""

CSS_DARK = b"""
.nxs-browser { background: #070b12; color: #dff6ff;
  font-family: "DejaVu Sans", "Cantarell", sans-serif; }
.nxs-toolbar { background: #0b1119; padding: 7px 8px; }
.nxs-toolbar button { background: transparent; border: none; border-radius: 9px;
  padding: 6px 8px; color: #dff6ff; box-shadow: none; outline: none;
  transition: background 120ms ease, color 120ms ease; }
.nxs-toolbar button image { color: #cfe9f5; }
.nxs-toolbar button:hover { background: #17293a; }
.nxs-toolbar button:active { background: #1e3346; }
/* URL bar a pillola, piatta. */
.nxs-urlbar { border: 1px solid #17293a; border-radius: 16px; padding: 7px 16px;
  background: #0d1622; color: #eaf9ff; caret-color: #dff6ff; }
.nxs-urlbar:focus { border-color: #2a4a63; }
.nxs-urlbar image { color: #6f93a6; }
.nxs-urlbar progress, .nxs-urlbar trough { min-height: 2px; }
.nxs-sidebar { background: #0b1119; border-right: 1px solid #12202e; }
.nxs-sidebar-head { background: #0b1119; padding: 7px 8px; }
.nxs-sidebar-head button { padding: 3px 5px; min-width: 0; min-height: 0; margin: 0;
  border-radius: 8px; }
.nxs-bm-list { background: #0b1119; color: #dff6ff; padding: 4px; }
.nxs-bm-list row { border-radius: 9px; padding: 3px; margin: 1px 2px; }
.nxs-bm-list row:hover { background: #12202e; }
.nxs-bm-list row:selected { background: #14202e; }
.nxs-bm-title { font-weight: 600; }
.nxs-bm-url { color: #6f93a6; font-size: 8pt; }
notebook { background: #070b12; }
notebook header { background: #0b1119; border: none; }
notebook header.top { box-shadow: inset 0 -1px #12202e; }
notebook tab { padding: 6px 12px; margin: 2px 1px 0 1px; color: #8fb0c0;
  background: transparent; border: none; border-radius: 8px 8px 0 0; }
notebook tab:hover { background: #101b28; color: #dff6ff; }
notebook tab:checked { color: #eaf9ff; font-weight: 600; background: #0d1622; }
notebook tab button { padding: 0; min-width: 18px; min-height: 18px;
  border-radius: 50%; }
notebook tab button:hover { background: #24384c; }
menubar { background: #070b12; color: #dff6ff; }
menubar > menuitem { color: #dff6ff; padding: 4px 10px; border-radius: 8px; }
menubar > menuitem:hover { background: #17293a; }
menu { background: #0d1622; color: #dff6ff; border: 1px solid #17293a;
  border-radius: 10px; padding: 4px; }
menu menuitem { border-radius: 7px; padding: 5px 10px; }
menu menuitem:hover { background: #17293a; }
paned > separator { background: #12202e; min-width: 1px; min-height: 1px; }
"""


class Browser(Gtk.Window):
    """Finestra principale del browser."""

    def __init__(self):
        super().__init__(title=APP_NAME)
        self.set_default_size(1200, 800)
        self.set_icon_name("nxs-browser")

        self.data_dir = Path.home() / ".nxs-browser"
        self.data_dir.mkdir(exist_ok=True)
        self.bookmarks_file = self.data_dir / "bookmarks.json"
        # Cache favicon dei preferiti (favicon.ico scaricata dal sito, come nel
        # browser originale): un file per dominio + set di domini in corso/falliti
        # per non riscaricare a ripetizione.
        self._fav_dir = self.data_dir / "bm_favicons"
        self._fav_inflight = set()
        self._fav_failed = set()

        # Default SCURO: coerente con l'ambiente NexusSec (palette navy/cyan).
        # L'accent lo prende dal profilo attivo (vedi _accent_css).
        self.dark_mode = bool(config.get("dark_mode", True))
        self.stealth = bool(config.get("stealth", True))   # anonimo di default
        self.bookmarks_minimized = False
        self._is_fullscreen = False   # stato schermo intero (F11)
        self._tab_labels = {}   # WebView -> (event_box, label, image)
        self._view_mode = {}    # WebView -> bool (True = scheda stealth)
        self._contexts = {}     # bool stealth -> WebKit2.WebContext (lazy)
        self._tor_ok = None     # None=non verificato, True/False

        # Provider CSS locale al processo (non tocca pannello/desktop).
        self._css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), self._css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self._build_ui()
        self.apply_theme()
        self.new_tab(config.get("homepage", "https://duckduckgo.com"))
        self.connect("destroy", Gtk.main_quit)
        self.show_all()
        self._update_stealth_button()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        root.get_style_context().add_class("nxs-browser")
        self.add(root)

        root.pack_start(self._build_menubar(), False, False, 0)
        root.pack_start(self._build_toolbar(), False, False, 0)

        self.paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.paned.set_position(SIDEBAR_W)
        root.pack_start(self.paned, True, True, 0)

        # shrink=True: la maniglia puo' rimpicciolire la sidebar col trascinamento
        # (come il QSplitter dell'originale); la larghezza minima la fissa il box.
        self.paned.pack1(self._build_sidebar(), False, True)

        self.notebook = Gtk.Notebook()
        self.notebook.set_scrollable(True)
        self.notebook.connect("switch-page", self._on_switch_page)
        self.paned.pack2(self.notebook, True, True)

        # F12 -> inspector ; F11 -> schermo intero (toggle)
        accel = Gtk.AccelGroup()
        self.add_accel_group(accel)
        accel.connect(Gdk.KEY_F12, 0, Gtk.AccelFlags.VISIBLE,
                      lambda *_: (self.toggle_inspector(), True)[1])
        accel.connect(Gdk.KEY_F11, 0, Gtk.AccelFlags.VISIBLE,
                      lambda *_: (self.toggle_fullscreen(), True)[1])
        # Traccia lo stato reale della finestra (per sapere se siamo in fullscreen).
        self.connect("window-state-event", self._on_window_state)

    def _build_menubar(self):
        bar = Gtk.MenuBar()

        def menu(label):
            item = Gtk.MenuItem(label=label)
            sub = Gtk.Menu()
            item.set_submenu(sub)
            bar.append(item)
            return sub

        def add(sub, label, cb):
            mi = Gtk.MenuItem(label=label)
            mi.connect("activate", lambda _w: cb())
            sub.append(mi)

        m_file = menu("File")
        add(m_file, "Nuova Tab", lambda: self.new_tab())
        add(m_file, "Chiudi Tab", lambda: self.close_tab(self.notebook.get_current_page()))
        m_file.append(Gtk.SeparatorMenuItem())
        add(m_file, "Esci", self.destroy)

        m_view = menu("Visualizza")
        add(m_view, "Zoom +", self.zoom_in)
        add(m_view, "Zoom -", self.zoom_out)
        add(m_view, "Zoom Normale", self.reset_zoom)

        m_pref = menu("Preferenze")
        add(m_pref, "Cambia Tema", self.toggle_theme)

        m_dev = menu("Developer")
        add(m_dev, "Inspector (F12)", self.toggle_inspector)
        add(m_dev, "Developer Tools", self.toggle_inspector)
        return bar

    def _btn(self, label, tooltip, cb):
        b = Gtk.Button(label=label)
        b.set_relief(Gtk.ReliefStyle.NONE)
        b.set_tooltip_text(tooltip)
        b.connect("clicked", lambda _w: cb())
        return b

    def _iconbtn(self, icon_name, tooltip, cb):
        """Pulsante con icona tematica (niente emoji: rendono tofu su TC e
        sono fuori stile NexusSec). Usa icone simboliche, gia' coperte dal tema."""
        b = Gtk.Button()
        b.set_relief(Gtk.ReliefStyle.NONE)
        b.set_tooltip_text(tooltip)
        b.set_image(Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.SMALL_TOOLBAR))
        b.set_always_show_image(True)
        b.connect("clicked", lambda _w: cb())
        return b

    def _build_toolbar(self):
        tb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        tb.get_style_context().add_class("nxs-toolbar")
        tb.pack_start(self._iconbtn("go-previous-symbolic", "Indietro", self.navigate_back), False, False, 0)
        tb.pack_start(self._iconbtn("go-next-symbolic", "Avanti", self.navigate_forward), False, False, 0)
        tb.pack_start(self._iconbtn("view-refresh-symbolic", "Ricarica", self.refresh), False, False, 0)
        tb.pack_start(self._iconbtn("go-home-symbolic", "Home", self.navigate_home), False, False, 0)

        self.url_bar = Gtk.Entry()
        self.url_bar.get_style_context().add_class("nxs-urlbar")
        self.url_bar.set_placeholder_text("Cerca o digita un indirizzo")
        self.url_bar.connect("activate", lambda _w: self.navigate_to_url())
        tb.pack_start(self.url_bar, True, True, 4)

        tb.pack_start(self._iconbtn("tab-new-symbolic", "Nuova tab", lambda: self.new_tab()), False, False, 0)
        tb.pack_start(self._iconbtn("bookmark-new-symbolic", "Aggiungi ai preferiti", self.add_bookmark), False, False, 0)
        tb.pack_start(self._iconbtn("weather-clear-night-symbolic", "Cambia tema", self.toggle_theme), False, False, 0)
        tb.pack_start(self._iconbtn("edit-find-symbolic", "Inspector (F12)", self.toggle_inspector), False, False, 0)

        # Interruttore stealth (anonimato Tor + niente tracce). Mostra icona+testo.
        self._stealth_btn = Gtk.Button()
        self._stealth_btn.set_relief(Gtk.ReliefStyle.NONE)
        self._stealth_btn.set_always_show_image(True)
        self._stealth_btn.connect("clicked", lambda _w: self.toggle_stealth())
        tb.pack_start(self._stealth_btn, False, False, 0)
        return tb

    def _build_sidebar(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.get_style_context().add_class("nxs-sidebar")
        # Larghezza minima (== stato collassato): con shrink=True il trascinamento
        # della maniglia resta libero fin qui senza far sparire del tutto i preferiti.
        box.set_size_request(SIDEBAR_MIN, -1)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        head.get_style_context().add_class("nxs-sidebar-head")
        title = Gtk.Label(label="Preferiti")
        title.set_xalign(0)
        # ellissi di sicurezza: se la sidebar viene stretta col trascinamento il
        # titolo si accorcia in modo pulito invece di sparire dietro i pulsanti.
        title.set_ellipsize(3)
        head.pack_start(title, True, True, 4)
        for icon, tip, cb in (
            ("list-add-symbolic", "Aggiungi il sito corrente", self.add_bookmark),
            ("document-edit-symbolic", "Modifica selezionato", self.edit_bookmark),
            ("user-trash-symbolic", "Elimina selezionato", self.delete_bookmark),
            ("view-refresh-symbolic", "Aggiorna", self.load_bookmarks),
            ("pan-start-symbolic", "Collassa/espandi", self.toggle_sidebar_collapse),
        ):
            head.pack_start(self._iconbtn(icon, tip, cb), False, False, 0)
        self._collapse_btn = head.get_children()[-1]
        # Titolo + pulsanti di gestione: da nascondere in modalita' collassata,
        # altrimenti l'header pretende ~158px di larghezza minima e impedisce
        # alla sidebar di stringersi davvero a SIDEBAR_MIN (le icone dei
        # preferiti finirebbero centrate nella parte nascosta sotto il browser).
        # Resta visibile solo il pulsante espandi.
        self._bm_head_extra = head.get_children()[:-1]
        box.pack_start(head, False, False, 0)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.bm_list = Gtk.ListBox()
        self.bm_list.get_style_context().add_class("nxs-bm-list")
        self.bm_list.connect("row-activated", self._on_bookmark_activated)
        self.bm_list.connect("button-press-event", self._on_bookmark_click)
        sw.add(self.bm_list)
        box.pack_start(sw, True, True, 0)

        self.load_bookmarks()
        return box

    # ------------------------------------------------------- stealth / Tor
    def _tor_running(self):
        try:
            with socket.create_connection((TOR_HOST, TOR_PORT), timeout=0.6):
                return True
        except OSError:
            return False

    def _ensure_tor(self):
        """SOCKS di Tor su 9050 raggiungibile? Se no, prova ad avviare un tor
        utente (rootless, data-dir in home). Ritorna True/False; in caso di
        fallimento le schede stealth restano effimere ma SENZA proxy (fallback
        onesto: nessuna traccia locale, ma IP reale) e il badge lo segnala."""
        if self._tor_running():
            self._tor_ok = True
            return True
        tor_bin = shutil.which("tor")
        if tor_bin:
            try:
                tdir = self.data_dir / "tor"
                tdir.mkdir(exist_ok=True)
                subprocess.Popen(
                    [tor_bin, "--SocksPort", str(TOR_PORT),
                     "--DataDirectory", str(tdir), "--quiet"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=True)
            except Exception:
                pass
            for _ in range(15):            # il listener SOCKS si apre in fretta
                if self._tor_running():
                    self._tor_ok = True
                    return True
                time.sleep(0.2)
        self._tor_ok = False
        return False

    def _context(self, stealth):
        ctx = self._contexts.get(stealth)
        if ctx is not None:
            return ctx
        if stealth:
            # Effimero: cookie/cache/cronologia SOLO in RAM, niente su disco.
            try:
                ctx = WebKit2.WebContext.new_ephemeral()
            except Exception:
                ctx = WebKit2.WebContext.new()
            if self._ensure_tor():         # instrada tutto via Tor (IP nascosto)
                try:
                    ps = WebKit2.NetworkProxySettings.new(TOR_SOCKS, None)
                    ctx.set_network_proxy_settings(
                        WebKit2.NetworkProxyMode.CUSTOM, ps)
                except Exception:
                    pass
        else:
            # Persistente: ricorda cookie/cronologia/cache in ~/.nxs-browser.
            ctx = WebKit2.WebContext.new()
            try:
                ctx.set_favicon_database_directory(str(self.data_dir / "favicons"))
            except Exception:
                pass
            try:
                ctx.get_cookie_manager().set_persistent_storage(
                    str(self.data_dir / "cookies.sqlite"),
                    WebKit2.CookiePersistentStorage.SQLITE)
            except Exception:
                pass
        self._contexts[stealth] = ctx
        return ctx

    def _harden(self, view):
        """Anti-leak per le schede stealth: niente WebRTC (fuga IP locale), UA
        generico, niente prefetch DNS/hyperlink-auditing, permessi negati."""
        s = view.get_settings()
        for prop, val in (("enable-webrtc", False),
                          ("enable-hyperlink-auditing", False),
                          ("enable-dns-prefetching", False)):
            try:
                s.set_property(prop, val)
            except Exception:
                pass
        try:
            s.set_property("user-agent", STEALTH_UA)
        except Exception:
            pass
        try:
            view.connect("permission-request",
                         lambda _v, req: (req.deny(), True)[1])
        except Exception:
            pass

    # --------------------------------------------------------------- tabs
    def new_tab(self, url=None, switch=True, view=None, stealth=None):
        # Se `view` e' gia' fornito, e' stato creato da WebKit per un popup /
        # link target=_blank (segnale "create"): NON va ricreato, e il caricamento
        # dell'URL di destinazione lo gestisce WebKit stesso (non caricare a mano).
        webkit_created = view is not None
        mode = self.stealth if stealth is None else stealth
        if view is None:
            view = WebKit2.WebView(web_context=self._context(mode))
        else:
            # il popup eredita il contesto (e quindi la modalita') dell'apertura
            mode = self._view_mode.get(view, mode)
        self._view_mode[view] = mode
        settings = view.get_settings()
        try:
            settings.set_property("enable-developer-extras", True)
        except Exception:
            pass
        if mode:
            self._harden(view)
        view.connect("notify::title", self._on_title)
        view.connect("notify::uri", self._on_uri)
        view.connect("notify::favicon", self._on_favicon)
        view.connect("notify::estimated-load-progress", self._on_progress)
        view.connect("create", self._on_create)
        view.show()

        label = self._make_tab_label(view, "Nuova Tab")
        index = self.notebook.append_page(view, label)
        self.notebook.set_tab_reorderable(view, True)
        if switch:
            self.notebook.set_current_page(index)
        if url and not webkit_created:
            view.load_uri(self._normalize(url))
        return view

    def _make_tab_label(self, view, text):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        img = Gtk.Image.new_from_icon_name("text-html", Gtk.IconSize.MENU)
        lbl = Gtk.Label(label=text)
        lbl.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        lbl.set_max_width_chars(16)
        close = Gtk.Button()
        close.set_relief(Gtk.ReliefStyle.NONE)
        close.set_image(Gtk.Image.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU))
        close.connect("clicked", lambda _w: self.close_tab(self.notebook.page_num(view)))
        box.pack_start(img, False, False, 0)
        box.pack_start(lbl, True, True, 0)
        box.pack_start(close, False, False, 0)
        box.show_all()
        self._tab_labels[view] = (box, lbl, img)
        return box

    def close_tab(self, index):
        if index < 0 or self.notebook.get_n_pages() <= 1:
            if self.notebook.get_n_pages() <= 1:
                return
        view = self.notebook.get_nth_page(index)
        if view is not None:
            self._tab_labels.pop(view, None)
            self.notebook.remove_page(index)
            view.destroy()

    def current_view(self):
        idx = self.notebook.get_current_page()
        return self.notebook.get_nth_page(idx) if idx >= 0 else None

    def _on_create(self, view, nav_action):
        # Link target=_blank / window.open -> nuova tab. Il nuovo WebView DEVE
        # nascere da new_with_related_view(view): condivide web process e
        # sessione della pagina che lo apre. Restituire un WebKit2.WebView()
        # scollegato manda WebKit in crash (assert WebCore::WindowFeatures).
        new_view = WebKit2.WebView.new_with_related_view(view)
        # il popup eredita la modalita' (stealth/normale) della scheda d'origine
        self._view_mode[new_view] = self._view_mode.get(view, self.stealth)
        self.new_tab(view=new_view, switch=True)
        return new_view

    def toggle_stealth(self):
        self.stealth = not self.stealth
        config.set("stealth", self.stealth)
        if self.stealth:
            self._ensure_tor()             # (ri)avvia/verifica Tor
            self._contexts.pop(True, None)  # ricrea il contesto stealth col proxy aggiornato
        self._update_stealth_button()
        self._reopen_current_in_mode()

    def _reopen_current_in_mode(self):
        """Ricarica la scheda corrente nella modalita' attuale: il contesto e'
        fissato per-view alla creazione, quindi si sostituisce la view."""
        cur = self.current_view()
        if cur is None:
            return
        idx = self.notebook.page_num(cur)
        uri = cur.get_uri() or config.get("homepage", "https://duckduckgo.com")
        newv = self.new_tab(uri, switch=True)
        self.notebook.reorder_child(newv, idx)
        self._tab_labels.pop(cur, None)
        self._view_mode.pop(cur, None)
        self.notebook.remove_page(self.notebook.page_num(cur))
        cur.destroy()

    def _update_stealth_button(self):
        btn = getattr(self, "_stealth_btn", None)
        if btn is None:
            return
        sc = btn.get_style_context()
        if self.stealth:
            if self._tor_ok:
                icon, label = "security-high-symbolic", "Stealth ON"
                tip = ("Navigazione ANONIMA attiva: traffico via Tor (IP nascosto) "
                       "e nessuna traccia locale. Click per disattivare.")
            else:
                icon, label = "security-medium-symbolic", "Stealth (no Tor)"
                tip = ("Nessuna traccia locale, ma Tor non e' disponibile: "
                       "l'IP reale e' visibile. Installa/avvia 'tor'. Click per disattivare.")
            sc.add_class("nxs-stealth-on")
            sc.remove_class("nxs-stealth-off")
        else:
            icon, label = "security-low-symbolic", "Stealth OFF"
            tip = ("Navigazione NORMALE: memorizza cookie, cronologia e cache. "
                   "Click per attivare l'anonimato (Tor).")
            sc.add_class("nxs-stealth-off")
            sc.remove_class("nxs-stealth-on")
        btn.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.SMALL_TOOLBAR))
        btn.set_label(label)
        btn.set_tooltip_text(tip)

    def _on_switch_page(self, _nb, view, _num):
        if view is not None:
            self.url_bar.set_text(view.get_uri() or "")

    def _on_title(self, view, _p):
        entry = self._tab_labels.get(view)
        if entry:
            title = view.get_title() or "Nuova Tab"
            entry[1].set_text(title)
            entry[0].set_tooltip_text(title)

    def _on_uri(self, view, _p):
        if view is self.current_view():
            self.url_bar.set_text(view.get_uri() or "")

    def _on_progress(self, view, _p):
        if view is self.current_view():
            prog = view.get_estimated_load_progress()
            self.url_bar.set_progress_fraction(prog if prog < 1.0 else 0.0)

    def _on_favicon(self, view, _p):
        entry = self._tab_labels.get(view)
        if not entry:
            return
        try:
            surface = view.get_favicon()
            if surface is None:
                return
            w, h = surface.get_width(), surface.get_height()
            pix = Gdk.pixbuf_get_from_surface(surface, 0, 0, w, h)
            if pix is not None:
                entry[2].set_from_pixbuf(pix.scale_simple(16, 16, 2))
        except Exception:
            pass

    # --------------------------------------------------------- navigazione
    @staticmethod
    def _normalize(url):
        url = url.strip()
        if not url:
            return "about:blank"
        if url.startswith(("http://", "https://", "about:", "file://", "data:")):
            return url
        if "." in url and " " not in url:
            return "https://" + url
        # altrimenti: ricerca
        return "https://duckduckgo.com/?q=" + GLib.uri_escape_string(url, None, True)

    def navigate_to_url(self):
        v = self.current_view()
        if v:
            v.load_uri(self._normalize(self.url_bar.get_text()))

    def navigate_back(self):
        v = self.current_view()
        if v and v.can_go_back():
            v.go_back()

    def navigate_forward(self):
        v = self.current_view()
        if v and v.can_go_forward():
            v.go_forward()

    def refresh(self):
        v = self.current_view()
        if v:
            v.reload()

    def navigate_home(self):
        v = self.current_view()
        if v:
            v.load_uri(config.get("homepage", "https://duckduckgo.com"))

    def zoom_in(self):
        v = self.current_view()
        if v:
            v.set_zoom_level(v.get_zoom_level() + 0.1)

    def zoom_out(self):
        v = self.current_view()
        if v:
            v.set_zoom_level(max(0.3, v.get_zoom_level() - 0.1))

    def reset_zoom(self):
        v = self.current_view()
        if v:
            v.set_zoom_level(1.0)

    def toggle_inspector(self):
        v = self.current_view()
        if v:
            insp = v.get_inspector()
            if insp:
                insp.show()

    def toggle_fullscreen(self):
        """F11: schermo intero on/off. Lo stato reale arriva da
        window-state-event (_on_window_state), cosi' resta coerente anche se il
        WM cambia lo stato da solo."""
        if self._is_fullscreen:
            self.unfullscreen()
        else:
            self.fullscreen()

    def _on_window_state(self, _w, event):
        self._is_fullscreen = bool(
            event.new_window_state & Gdk.WindowState.FULLSCREEN)
        return False

    # ----------------------------------------------------------- preferiti
    def _read_bookmarks(self):
        if self.bookmarks_file.exists():
            try:
                with open(self.bookmarks_file, "r") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _write_bookmarks(self, bookmarks):
        try:
            with open(self.bookmarks_file, "w") as f:
                json.dump(bookmarks, f, indent=2)
        except Exception:
            pass

    def load_bookmarks(self):
        for child in self.bm_list.get_children():
            self.bm_list.remove(child)
        for title, url in self._read_bookmarks():
            self.bm_list.add(self._make_bookmark_row(title, url))
        self.bm_list.show_all()

    def _make_bookmark_row(self, title, url):
        row = Gtk.ListBoxRow()
        row.bookmark = (title, url)
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        hbox.set_margin_top(3); hbox.set_margin_bottom(3)
        hbox.set_margin_start(4); hbox.set_margin_end(4)
        # Icona del preferito: parte da quella generica, poi (async) viene
        # sostituita con la favicon reale del sito se e' nel database WebKit
        # (pagine gia' visitate). In modalita' ristretta e' piu' grande e
        # centrata, cosi' i preferiti compaiono con la loro icona come nel
        # browser originale.
        minimized = self.bookmarks_minimized
        icon_size = 22 if minimized else 16
        icon = Gtk.Image.new_from_icon_name("user-bookmarks", Gtk.IconSize.MENU)
        icon.set_pixel_size(icon_size)
        # Collassata: icona CENTRATA nella colonna. Ora e' possibile perche' in
        # modalita' ristretta l'header viene nascosto e la sidebar si stringe
        # davvero a SIDEBAR_MIN (prima, con la sidebar larga 158px sotto il
        # browser, il centro cadeva nella parte nascosta e le icone sparivano).
        icon.set_halign(Gtk.Align.CENTER if minimized else Gtk.Align.START)
        hbox.pack_start(icon, minimized, minimized, 0)
        self._apply_bookmark_favicon(icon, url, icon_size)
        if not self.bookmarks_minimized:
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            # width_chars basso (minimo) + ellissi: l'etichetta si adatta alla
            # larghezza REALE della sidebar (non forza il box oltre il pannello,
            # cosa che prima tagliava titolo/URL). max_width_chars limita solo il
            # naturale quando la sidebar e' larga.
            t = Gtk.Label(label=title or url); t.set_xalign(0)
            t.set_ellipsize(3); t.set_width_chars(6); t.set_max_width_chars(24)
            t.get_style_context().add_class("nxs-bm-title")
            u = Gtk.Label(label=url); u.set_xalign(0)
            u.set_ellipsize(3); u.set_width_chars(6); u.set_max_width_chars(24)
            u.get_style_context().add_class("nxs-bm-url")
            vbox.pack_start(t, False, False, 0)
            vbox.pack_start(u, False, False, 0)
            hbox.pack_start(vbox, True, True, 0)
        row.add(hbox)
        row.set_tooltip_text("%s\n%s" % (title, url))
        return row

    @staticmethod
    def _favicon_domain(url):
        try:
            net = urlparse(url if "://" in url else "http://" + url).netloc
            return net.split("@")[-1].split(":")[0].lower()
        except Exception:
            return ""

    def _apply_bookmark_favicon(self, image, url, size):
        """Mostra la favicon.ico REALE del sito sul preferito (come il browser
        originale), per TUTTI i preferiti. La favicon di ogni dominio viene
        scaricata una volta e messa in cache su disco; se gia' in cache la usa
        subito, altrimenti resta l'icona generica e parte il download in
        background che poi aggiorna la lista."""
        domain = self._favicon_domain(url)
        if not domain:
            return
        path = self._fav_dir / (domain + ".img")
        if path.exists():
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_size(str(path), size, size)
                if pb is not None and image.get_parent() is not None:
                    image.set_from_pixbuf(pb)
                return
            except Exception:
                # file in cache corrotto: lo elimino e riscarico
                try:
                    path.unlink()
                except Exception:
                    pass
        if domain in self._fav_failed:
            return
        self._fetch_favicon_async(domain)

    def _fetch_favicon_async(self, domain):
        if not domain or domain in self._fav_inflight:
            return
        self._fav_inflight.add(domain)
        threading.Thread(target=self._fetch_favicon,
                         args=(domain,), daemon=True).start()

    def _fetch_favicon(self, domain):
        """Scarica la favicon.ico provando gli URL comuni; la valida come
        immagine e la salva in cache. Gira in un thread separato (rete)."""
        candidates = ("https://%s/favicon.ico" % domain,
                      "https://www.%s/favicon.ico" % domain,
                      "http://%s/favicon.ico" % domain)
        data = None
        for u in candidates:
            try:
                req = urllib.request.Request(
                    u, headers={"User-Agent": STEALTH_UA})
                with urllib.request.urlopen(req, timeout=6) as r:
                    if getattr(r, "status", 200) == 200:
                        d = r.read(200000)
                        if d and self._valid_image(d):
                            data = d
                            break
            except Exception:
                continue
        self._fav_inflight.discard(domain)
        if not data:
            self._fav_failed.add(domain)
            return
        try:
            self._fav_dir.mkdir(parents=True, exist_ok=True)
            with open(self._fav_dir / (domain + ".img"), "wb") as f:
                f.write(data)
        except Exception:
            return
        # ricarica la lista sul thread principale: la nuova favicon compare
        GLib.idle_add(self.load_bookmarks)

    @staticmethod
    def _valid_image(data):
        """True se i byte sono un'immagine decodificabile (ICO/PNG/GIF...)."""
        try:
            loader = GdkPixbuf.PixbufLoader()
            loader.write(data)
            loader.close()
            return loader.get_pixbuf() is not None
        except Exception:
            return False

    def _on_bookmark_activated(self, _list, row):
        if row and getattr(row, "bookmark", None):
            _title, url = row.bookmark
            v = self.current_view()
            if v:
                v.load_uri(self._normalize(url))

    def _on_bookmark_click(self, _list, event):
        if event.button == 3:  # tasto destro
            row = self.bm_list.get_row_at_y(int(event.y))
            self._bookmark_menu(row, event)
            return True
        return False

    def _bookmark_menu(self, row, event):
        menu = Gtk.Menu()

        def item(label, cb):
            mi = Gtk.MenuItem(label=label)
            mi.connect("activate", lambda _w: cb())
            menu.append(mi)

        item("Aggiungi sito corrente", self.add_bookmark)
        if row is not None and getattr(row, "bookmark", None):
            self.bm_list.select_row(row)
            menu.append(Gtk.SeparatorMenuItem())
            item("Apri in nuova tab",
                 lambda: self.new_tab(row.bookmark[1]))
            item("Modifica", self.edit_bookmark)
            item("Elimina", self.delete_bookmark)
        menu.show_all()
        menu.popup_at_pointer(event)

    def add_bookmark(self):
        v = self.current_view()
        if not v:
            return
        url = v.get_uri() or ""
        title = v.get_title() or url
        if not url:
            return
        bookmarks = self._read_bookmarks()
        bookmarks.append([title, url])
        self._write_bookmarks(bookmarks)
        self.load_bookmarks()

    def _selected_bookmark(self):
        row = self.bm_list.get_selected_row()
        return row.bookmark if row and getattr(row, "bookmark", None) else None

    def edit_bookmark(self):
        bm = self._selected_bookmark()
        if not bm:
            return
        old_title, old_url = bm
        new_title = self._prompt("Modifica preferito", "Titolo:", old_title)
        if new_title is None:
            return
        new_url = self._prompt("Modifica preferito", "URL:", old_url)
        if new_url is None:
            return
        new_url = self._normalize(new_url)
        bookmarks = [[t, u] for t, u in self._read_bookmarks()
                     if not (t == old_title and u == old_url)]
        bookmarks.append([new_title.strip() or new_url, new_url])
        self._write_bookmarks(bookmarks)
        self.load_bookmarks()

    def delete_bookmark(self):
        bm = self._selected_bookmark()
        if not bm:
            return
        title, url = bm
        dlg = Gtk.MessageDialog(
            transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Eliminare il preferito?")
        dlg.format_secondary_text(title)
        resp = dlg.run()
        dlg.destroy()
        if resp == Gtk.ResponseType.YES:
            bookmarks = [[t, u] for t, u in self._read_bookmarks()
                         if not (t == title and u == url)]
            self._write_bookmarks(bookmarks)
            self.load_bookmarks()

    def _prompt(self, title, label, text=""):
        dlg = Gtk.Dialog(title=title, transient_for=self, modal=True)
        dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                        Gtk.STOCK_OK, Gtk.ResponseType.OK)
        box = dlg.get_content_area()
        box.set_spacing(6)
        box.set_border_width(8)
        box.add(Gtk.Label(label=label, xalign=0))
        entry = Gtk.Entry()
        entry.set_text(text)
        entry.set_activates_default(True)
        dlg.set_default_response(Gtk.ResponseType.OK)
        box.add(entry)
        dlg.show_all()
        resp = dlg.run()
        value = entry.get_text() if resp == Gtk.ResponseType.OK else None
        dlg.destroy()
        return value

    def toggle_sidebar_collapse(self):
        self.bookmarks_minimized = not self.bookmarks_minimized
        icon = "pan-end-symbolic" if self.bookmarks_minimized else "pan-start-symbolic"
        self._collapse_btn.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.SMALL_TOOLBAR))
        # Nasconde titolo + pulsanti di gestione quando collassata: cosi' l'header
        # non impone la sua larghezza minima e la sidebar si stringe a SIDEBAR_MIN.
        for w in self._bm_head_extra:
            w.set_visible(not self.bookmarks_minimized)
        self.paned.set_position(SIDEBAR_MIN if self.bookmarks_minimized else SIDEBAR_W)
        self.load_bookmarks()

    # -------------------------------------------------------------- tema
    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        config.set("dark_mode", self.dark_mode)
        self.apply_theme()

    def _profile_accent(self):
        """Colore accent del profilo NexusSec attivo (cyan se non disponibile).
        Cosi' il browser e' coerente con barra/menu della modalita' scelta."""
        try:
            from nxs_profiles import model
            return model.accent()
        except Exception:
            return "#00e5ff"

    def _accent_css(self):
        """Override CSS che colora di accent gli elementi chiave dell'interfaccia
        (accento toolbar, focus URL con alone, tab attiva sottolineata, preferito
        selezionato, badge stealth). Usa rgba per hover/aloni morbidi e piatti."""
        a = self._profile_accent()
        try:
            h = a.lstrip("#")
            r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        except (ValueError, IndexError):
            r, g, b = 0, 229, 255
        rgb = "%d,%d,%d" % (r, g, b)
        return ("""
.nxs-toolbar { box-shadow: inset 0 2px %(a)s; }
.nxs-toolbar button:hover { background: rgba(%(rgb)s,0.16); color: %(a)s; }
.nxs-toolbar button:hover image { color: %(a)s; }
.nxs-toolbar button:active { background: rgba(%(rgb)s,0.26); }
.nxs-urlbar:focus { border-color: %(a)s; box-shadow: 0 0 0 3px rgba(%(rgb)s,0.18); }
.nxs-urlbar:focus image { color: %(a)s; }
.nxs-bm-list row:hover { background: rgba(%(rgb)s,0.10); }
.nxs-bm-list row:selected { background: rgba(%(rgb)s,0.20); }
.nxs-bm-list row:selected .nxs-bm-title { color: %(a)s; }
notebook tab:checked { color: %(a)s; font-weight: 600;
  box-shadow: inset 0 -2px %(a)s; }
notebook tab:hover { color: %(a)s; }
.nxs-sidebar-head button:hover { background: rgba(%(rgb)s,0.16); color: %(a)s; }
menubar > menuitem:hover { background: rgba(%(rgb)s,0.16); color: %(a)s; }
menu menuitem:hover { background: rgba(%(rgb)s,0.18); }
.nxs-stealth-on { color: %(a)s; font-weight: bold; }
.nxs-stealth-off { color: #6f8494; font-weight: normal; }
""" % {"a": a, "rgb": rgb}).encode()

    def apply_theme(self):
        base = CSS_DARK if self.dark_mode else CSS_LIGHT
        # base + override accent del profilo: l'accent vince (caricato dopo).
        self._css.load_from_data(base + self._accent_css())
        try:
            settings = Gtk.Settings.get_default()
            settings.set_property("gtk-application-prefer-dark-theme", self.dark_mode)
        except Exception:
            pass


def main():
    win = Browser()  # noqa: F841
    Gtk.main()


if __name__ == "__main__":
    main()
