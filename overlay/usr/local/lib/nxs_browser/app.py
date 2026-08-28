"""NexusSec Browser - interfaccia GTK3 + WebKit2.

Port fedele del browser originale (PyQt5/QtWebEngine) sullo stack nativo di
NexusSec: GTK3 + WebKit2 (PyGObject). Stesse funzioni dell'originale:
  - tab multiple chiudibili con titolo e favicon
  - sidebar dei preferiti (aggiungi/modifica/elimina/aggiorna): collassata
    mostra le icone verticali, aperta l'elenco; pulsanti e menu sempre attivi
  - barra URL intelligente con progress a linea (sopra il contenuto)
  - navigazione completa (indietro/avanti/ricarica/home) e zoom
  - tema chiaro/scuro con persistenza
  - inspector (DevTools nativi di WebKit, F12)

Struttura "clone Firefox" (2026):
  [striscia schede a pillola]      <- in cima, bg #1c1b22 (tab strip)
  [barra navigazione con URL pill] <- sotto le schede, bg #2b2a33
  [linea di progress 2px]
  [paned: sidebar preferiti (icone o elenco) | contenuto WebKit]

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
# Larghezze sidebar preferiti (come nella versione precedente): COLLASSATA
# mostra le SOLE ICONE dei preferiti in colonna verticale; APERTA mostra
# l'elenco completo. La sidebar PARTE COLLASSATA (chiusa): si vedono subito
# le icone verticali, e si espande dal rail quando serve.
SIDEBAR_MIN = 60       # larghezza collassata (colonna icone)
SIDEBAR_W = 250        # larghezza aperta (elenco completo)


# ---------------------------------------------------------------------------
# Temi "clone Firefox": palette del tema scuro/chiaro UFFICIALE di Firefox
# (toolbar #2b2a33, tab strip #1c1b22, testo #fbfbfe, ring focus #45a1ff).
# ---------------------------------------------------------------------------
CSS_LIGHT = b"""
.nxs-browser { background: #f9f9fb; color: #15141a;
  font-family: "DejaVu Sans", "Cantarell", sans-serif; }
/* Striscia schede (piu' chiara della navbar, come Firefox) */
.nxs-tabstrip { background: #f0f0f4; box-shadow: inset 0 -1px #e1e1e6; }
.nxs-tab { background: transparent; color: #5b5b66; border-radius: 10px 10px 0 0;
  margin: 5px 2px 0 2px; padding: 0 4px; min-height: 34px; }
.nxs-tab:hover { background: #e0e0e6; color: #15141a; }
.nxs-tab-active, .nxs-tab-active:hover { background: #f9f9fb; color: #15141a;
  box-shadow: inset 0 1px 0 #ffffff; }
.nxs-tab button { background: transparent; border: none; border-radius: 50%;
  padding: 0; min-width: 18px; min-height: 18px; color: #737380; }
.nxs-tab button:hover { background: #d6d6de; color: #15141a; }
.nxs-tab-new { background: transparent; border: none; border-radius: 8px;
  padding: 6px 8px; color: #5b5b66; margin: 5px 4px 0 0; }
.nxs-tab-new:hover { background: #e0e0e6; color: #15141a; }
/* Barra navigazione con URL pill */
.nxs-navbar { background: #f9f9fb; padding: 6px 8px; border-bottom: 1px solid #e1e1e6; }
.nxs-nav-btn { background: transparent; border: none; border-radius: 8px;
  padding: 6px 7px; color: #5b5b66; box-shadow: none; outline: none; }
.nxs-nav-btn:hover { background: #e1e1e6; color: #15141a; }
.nxs-nav-btn:active { background: #d6d6de; }
.nxs-urlbar { background: #ffffff; color: #15141a; border: 1px solid transparent;
  border-radius: 14px; padding: 5px 14px; min-height: 20px; caret-color: #15141a; }
.nxs-urlbar:hover { background: #f0f0f4; }
.nxs-urlbar:focus { background: #ffffff; border-color: #0060df;
  box-shadow: 0 0 0 3px rgba(0, 96, 223, 0.20); }
.nxs-urlbar image { color: #737380; }
/* Linea di progress (sopra il contenuto, come Firefox) */
.nxs-progress { background: transparent; border: none; padding: 0; min-height: 2px; }
.nxs-progress trough { min-height: 2px; background: #e1e1e6; }
.nxs-progress progress { min-height: 2px; background: #0060df; }
/* Sidebar preferiti (come la versione precedente): header orizzontale quando
   e' APERTA, rail verticale con le SOLE ICONE dei preferiti quando e'
   COLLASSATA. I pulsanti e il menu (tasto destro) sono attivi in entrambi. */
.nxs-sidebar { background: #f9f9fb; border-right: 1px solid #e1e1e6; }
.nxs-sidebar-head { background: #f9f9fb; padding: 8px 6px 6px 10px; }
.nxs-sidebar-title { color: #5b5b66; font-weight: 700; font-size: 9pt; }
.nxs-sidebar-head button, .nxs-sidebar-rail button {
  background: transparent; border: none; border-radius: 8px; padding: 7px;
  min-width: 0; min-height: 0; margin: 2px; color: #5b5b66; box-shadow: none; }
.nxs-sidebar-head button:hover, .nxs-sidebar-rail button:hover {
  background: #e1e1e6; color: #15141a; }
.nxs-sidebar-rail { padding: 6px 0 2px; }
.nxs-sidebar-rail button { padding: 8px; }
.nxs-rail-sep { background: #e1e1e6; min-height: 1px; margin: 4px 12px; }
.nxs-bm-list { background: #f9f9fb; color: #15141a; padding: 4px; }
.nxs-bm-list row { border-radius: 8px; padding: 4px; margin: 1px 4px; }
.nxs-bm-list row:hover { background: #e1e1e6; }
.nxs-bm-list row:selected { background: #d6d6de; }
.nxs-bm-title { font-weight: 600; }
.nxs-bm-url { color: #737380; font-size: 8pt; }
menu { background: #ffffff; color: #15141a; border: 1px solid #e1e1e6;
  border-radius: 10px; padding: 4px; }
menu menuitem { border-radius: 7px; padding: 5px 10px; }
menu menuitem:hover { background: #e1e1e6; }
paned > separator { background: transparent; min-width: 1px; min-height: 1px; }
"""

CSS_DARK = b"""
.nxs-browser { background: #2b2a33; color: #fbfbfe;
  font-family: "DejaVu Sans", "Cantarell", sans-serif; }
/* Striscia schede: piu' scura della navbar (Firefox dark) */
.nxs-tabstrip { background: #1c1b22; box-shadow: inset 0 -1px #1a191f; }
.nxs-tab { background: transparent; color: #cfcfd8; border-radius: 10px 10px 0 0;
  margin: 5px 2px 0 2px; padding: 0 4px; min-height: 34px; }
.nxs-tab:hover { background: #23222b; color: #fbfbfe; }
.nxs-tab-active, .nxs-tab-active:hover { background: #2b2a33; color: #fbfbfe;
  box-shadow: inset 0 1px 0 #5b5b66; }
.nxs-tab button { background: transparent; border: none; border-radius: 50%;
  padding: 0; min-width: 18px; min-height: 18px; color: #9d9da6; }
.nxs-tab button:hover { background: #3a3944; color: #fbfbfe; }
.nxs-tab-new { background: transparent; border: none; border-radius: 8px;
  padding: 6px 8px; color: #cfcfd8; margin: 5px 4px 0 0; }
.nxs-tab-new:hover { background: #23222b; color: #fbfbfe; }
/* Barra navigazione con URL pill */
.nxs-navbar { background: #2b2a33; padding: 6px 8px; border-bottom: 1px solid #1c1b22; }
.nxs-nav-btn { background: transparent; border: none; border-radius: 8px;
  padding: 6px 7px; color: #cfcfd8; box-shadow: none; outline: none; }
.nxs-nav-btn:hover { background: #3a3944; color: #fbfbfe; }
.nxs-nav-btn:active { background: #454451; }
.nxs-urlbar { background: #1c1b22; color: #fbfbfe; border: 1px solid transparent;
  border-radius: 14px; padding: 5px 14px; min-height: 20px; caret-color: #fbfbfe; }
.nxs-urlbar:hover { background: #26252e; }
.nxs-urlbar:focus { background: #2b2a33; border-color: #45a1ff;
  box-shadow: 0 0 0 3px rgba(69, 161, 255, 0.28); }
.nxs-urlbar image { color: #9d9da6; }
/* Linea di progress (sopra il contenuto, come Firefox) */
.nxs-progress { background: transparent; border: none; padding: 0; min-height: 2px; }
.nxs-progress trough { min-height: 2px; background: #1c1b22; }
.nxs-progress progress { min-height: 2px; background: #45a1ff; }
/* Sidebar preferiti (come la versione precedente): header orizzontale quando
   e' APERTA, rail verticale con le SOLE ICONE dei preferiti quando e'
   COLLASSATA. I pulsanti e il menu (tasto destro) sono attivi in entrambi. */
.nxs-sidebar { background: #2b2a33; border-right: 1px solid #1c1b22; }
.nxs-sidebar-head { background: #2b2a33; padding: 8px 6px 6px 10px; }
.nxs-sidebar-title { color: #cfcfd8; font-weight: 700; font-size: 9pt; }
.nxs-sidebar-head button, .nxs-sidebar-rail button {
  background: transparent; border: none; border-radius: 8px; padding: 7px;
  min-width: 0; min-height: 0; margin: 2px; color: #cfcfd8; box-shadow: none; }
.nxs-sidebar-head button:hover, .nxs-sidebar-rail button:hover {
  background: #3a3944; color: #fbfbfe; }
.nxs-sidebar-rail { padding: 6px 0 2px; }
.nxs-sidebar-rail button { padding: 8px; }
.nxs-rail-sep { background: #1c1b22; min-height: 1px; margin: 4px 12px; }
.nxs-bm-list { background: #2b2a33; color: #fbfbfe; padding: 4px; }
.nxs-bm-list row { border-radius: 8px; padding: 4px; margin: 1px 4px; }
.nxs-bm-list row:hover { background: #3a3944; }
.nxs-bm-list row:selected { background: #454451; }
.nxs-bm-title { font-weight: 600; }
.nxs-bm-url { color: #9d9da6; font-size: 8pt; }
menu { background: #2b2a33; color: #fbfbfe; border: 1px solid #1c1b22;
  border-radius: 10px; padding: 4px; }
menu menuitem { border-radius: 7px; padding: 5px 10px; }
menu menuitem:hover { background: #3a3944; }
paned > separator { background: transparent; min-width: 1px; min-height: 1px; }
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

        # Default SCURO (clone del tema scuro di Firefox). La sidebar PARTE
        # COLLASSATA: si vedono subito le icone dei preferiti in colonna; si
        # espande (elenco completo) a richiesta.
        self.dark_mode = bool(config.get("dark_mode", True))
        self.stealth = bool(config.get("stealth", True))   # anonimo di default
        self.bookmarks_minimized = True   # sidebar collassata all'avvio (icone)
        self._is_fullscreen = False   # stato schermo intero (F11)
        self._tab_labels = {}   # WebView -> (box, img, label)
        self._tabs = {}         # WebView -> tab EventBox
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

        # Layout clone Firefox: striscia schede in CIMA, poi barra navigazione
        # con URL pill, poi la linea di progress e infine il contenuto.
        self._tabstrip = self._build_tabstrip()
        self._navbar = self._build_navbar()
        root.pack_start(self._tabstrip, False, False, 0)
        root.pack_start(self._navbar, False, False, 0)

        self.progress = Gtk.ProgressBar()
        self.progress.get_style_context().add_class("nxs-progress")
        self.progress.set_fraction(0.0)
        self.progress.hide()
        root.pack_start(self.progress, False, False, 0)

        self.paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        root.pack_start(self.paned, True, True, 0)

        # Rail + pannello preferiti (la sidebar si apre/chiude dal rail).
        self._sidebar = self._build_sidebar()
        self.paned.pack1(self._sidebar, False, True)

        self.stack = Gtk.Stack()
        self.stack.connect("notify::visible-child", self._on_stack_child)
        self.paned.pack2(self.stack, True, True)

        # Chiusa all'avvio: solo rail. Impostata DOPO pack1/pack2 (altrimenti
        # GtkPaned scarta la posizione applicata prima di avere i figli).
        self.paned.set_position(SIDEBAR_MIN)

        # F12 -> inspector ; F11 -> schermo intero (toggle)
        accel = Gtk.AccelGroup()
        self.add_accel_group(accel)
        accel.connect(Gdk.KEY_F12, 0, Gtk.AccelFlags.VISIBLE,
                      lambda *_: (self.toggle_inspector(), True)[1])
        accel.connect(Gdk.KEY_F11, 0, Gtk.AccelFlags.VISIBLE,
                      lambda *_: (self.toggle_fullscreen(), True)[1])
        # Traccia lo stato reale della finestra (per sapere se siamo in fullscreen).
        self.connect("window-state-event", self._on_window_state)

    def _build_tabstrip(self):
        """Striscia delle schede (Firefox): strip scrollabile a pillola + "+"."""
        strip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        strip.get_style_context().add_class("nxs-tabstrip")
        sc = Gtk.ScrolledWindow()
        sc.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        sc.set_shadow_type(Gtk.ShadowType.NONE)
        self.tab_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        sc.add(self.tab_box)
        strip.pack_start(sc, True, True, 0)
        b = self._iconbtn("tab-new-symbolic", "Nuova tab", lambda: self.new_tab())
        b.get_style_context().add_class("nxs-tab-new")
        strip.pack_start(b, False, False, 0)
        return strip

    def _build_navbar(self):
        """Barra navigazione (Firefox): indietro/avanti/ricarica/home + URL pill
        + azioni essenziali a destra (preferito, tema, stealth, menu). Nuova tab
        sta nella striscia schede; inspector resta SOLO nel menu."""
        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        nav.get_style_context().add_class("nxs-navbar")
        nav.pack_start(self._navbtn("go-previous-symbolic", "Indietro", self.navigate_back), False, False, 0)
        nav.pack_start(self._navbtn("go-next-symbolic", "Avanti", self.navigate_forward), False, False, 0)
        nav.pack_start(self._navbtn("view-refresh-symbolic", "Ricarica", self.refresh), False, False, 0)
        nav.pack_start(self._navbtn("go-home-symbolic", "Home", self.navigate_home), False, False, 0)

        self.url_bar = Gtk.Entry()
        self.url_bar.get_style_context().add_class("nxs-urlbar")
        self.url_bar.set_placeholder_text("Cerca o digita un indirizzo")
        # Icona "lucchetto" del sito all'inizio dell'URL pill (come Firefox).
        try:
            self.url_bar.set_icon_from_icon_name(
                Gtk.EntryIconPosition.PRIMARY, "security-high-symbolic")
        except Exception:
            pass
        self.url_bar.connect("activate", lambda _w: self.navigate_to_url())
        nav.pack_start(self.url_bar, True, True, 4)

        nav.pack_start(self._navbtn("bookmark-new-symbolic", "Aggiungi ai preferiti", self.add_bookmark), False, False, 0)
        nav.pack_start(self._navbtn("weather-clear-night-symbolic", "Cambia tema", self.toggle_theme), False, False, 0)

        # Interruttore stealth (anonimato Tor + niente tracce). Mostra icona+testo.
        self._stealth_btn = Gtk.Button()
        self._stealth_btn.set_relief(Gtk.ReliefStyle.NONE)
        self._stealth_btn.set_always_show_image(True)
        self._stealth_btn.get_style_context().add_class("nxs-nav-btn")
        self._stealth_btn.connect("clicked", lambda _w: self.toggle_stealth())
        nav.pack_start(self._stealth_btn, False, False, 0)

        # Menu a hamburger (sostituisce la menubar, come Firefox).
        self._menu_btn = self._navbtn("open-menu-symbolic", "Menu", self._show_menu)
        nav.pack_start(self._menu_btn, False, False, 0)
        return nav

    def _show_menu(self):
        menu = Gtk.Menu()

        def item(label, cb):
            mi = Gtk.MenuItem(label=label)
            mi.connect("activate", lambda _w: cb())
            menu.append(mi)

        item("Nuova Tab", lambda: self.new_tab())
        item("Chiudi Tab", lambda: self.close_tab(self.current_view()))
        menu.append(Gtk.SeparatorMenuItem())
        item("Zoom +", self.zoom_in)
        item("Zoom -", self.zoom_out)
        item("Zoom Normale", self.reset_zoom)
        menu.append(Gtk.SeparatorMenuItem())
        item("Cambia Tema", self.toggle_theme)
        item("Inspector (F12)", self.toggle_inspector)
        menu.append(Gtk.SeparatorMenuItem())
        item("Esci", self.destroy)
        menu.show_all()
        menu.popup_at_widget(self._menu_btn, Gdk.Gravity.SOUTH_EAST,
                             Gdk.Gravity.NORTH_EAST, None)

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

    def _navbtn(self, icon_name, tooltip, cb):
        b = self._iconbtn(icon_name, tooltip, cb)
        b.get_style_context().add_class("nxs-nav-btn")
        return b

    def _build_sidebar(self):
        """Sidebar preferiti (come nella versione precedente): due layout che
        riusano le STESSE azioni, cosi' pulsanti e menu sono SEMPRE agganciati:
          - COLLASSATA (default): rail verticale con ESPANSIONE e azioni in
            ALTO, le SOLE ICONE dei preferiti in colonna.
          - APERTA: header orizzontale "Preferiti" + azioni, elenco completo
            (icona + titolo + URL), collasso in ALTO.
        Il toggle sta in ALTO in entrambi gli stati (apri e chiudi dalla stessa
        zona). Parte COLLASSATA: le icone verticali dei preferiti sono subito
        visibili."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.get_style_context().add_class("nxs-sidebar")
        # Larghezza minima (stato collassato): il trascinamento della maniglia
        # resta libero fin qui senza far sparire del tutto i preferiti.
        box.set_size_request(SIDEBAR_MIN, -1)

        # Azioni, riusate in ENTRAMBI i layout (== sempre funzionanti).
        actions = (
            ("list-add-symbolic", "Aggiungi il sito corrente", self.add_bookmark),
            ("document-edit-symbolic", "Modifica selezionato", self.edit_bookmark),
            ("user-trash-symbolic", "Elimina selezionato", self.delete_bookmark),
            ("view-refresh-symbolic", "Aggiorna", self.load_bookmarks),
        )

        # --- Header ORIZZONTALE (stato APERTO): titolo + azioni + collassa ----
        self._head_open = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self._head_open.get_style_context().add_class("nxs-sidebar-head")
        title = Gtk.Label(label="Preferiti")
        title.get_style_context().add_class("nxs-sidebar-title")
        title.set_xalign(0)
        title.set_ellipsize(3)
        self._head_open.pack_start(title, True, True, 4)
        for icon, tip, cb in actions:
            self._head_open.pack_start(self._iconbtn(icon, tip, cb), False, False, 0)
        self._head_open.pack_start(
            self._iconbtn("pan-start-symbolic", "Collassa",
                          self.toggle_sidebar_collapse), False, False, 0)
        box.pack_start(self._head_open, False, False, 0)

        # --- Rail VERTICALE (stato COLLASSATO): stesse azioni + icone ---------
        self._head_rail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._head_rail.get_style_context().add_class("nxs-sidebar-rail")
        # Espansione in ALTO (come il collasso quando e' aperta): il toggle sta
        # in alto in ENTRAMBI gli stati, niente piu' freccia in fondo.
        self._head_rail.pack_start(
            self._iconbtn("pan-end-symbolic", "Espandi",
                          self.toggle_sidebar_collapse), False, False, 0)
        for icon, tip, cb in actions:
            self._head_rail.pack_start(self._iconbtn(icon, tip, cb), False, False, 0)
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.get_style_context().add_class("nxs-rail-sep")
        self._head_rail.pack_start(sep, False, False, 3)
        box.pack_start(self._head_rail, False, False, 0)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.bm_list = Gtk.ListBox()
        self.bm_list.get_style_context().add_class("nxs-bm-list")
        self.bm_list.connect("row-activated", self._on_bookmark_activated)
        self.bm_list.connect("button-press-event", self._on_bookmark_click)
        sw.add(self.bm_list)
        box.pack_start(sw, True, True, 0)

        # Parte COLLASSATA: l'header orizzontale non compare con show_all().
        # Per riaperirlo, toggle_sidebar_collapse spegne no_show_all prima di
        # show_all() (vedi sotto).
        self._head_open.set_no_show_all(True)
        self._head_open.hide()

        self.load_bookmarks()
        return box

    # --------------------------------------------------------- sidebar open/close
    def toggle_sidebar_collapse(self):
        """Scambia i due layout: header orizzontale (aperta) <-> rail verticale
        con le SOLE ICONE dei preferiti (collassata). Nel collassato l'header
        non impone la sua larghezza minima, cosi' la sidebar si stringe davvero
        a SIDEBAR_MIN. Il toggle sta in ALTO in entrambi gli stati."""
        self.bookmarks_minimized = not self.bookmarks_minimized
        if self.bookmarks_minimized:
            self._head_open.hide()
            self._head_rail.show_all()
        else:
            self._head_rail.hide()
            self._head_open.set_no_show_all(False)   # sblocca show_all()
            self._head_open.show_all()
        self.paned.set_position(SIDEBAR_MIN if self.bookmarks_minimized else SIDEBAR_W)
        self.load_bookmarks()

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

        self.stack.add_named(view, str(id(view)))
        ev = self._make_tab(view, "Nuova Tab")
        self.tab_box.pack_start(ev, False, False, 0)
        ev.show_all()
        if switch:
            self._set_active_tab(view)
        if url and not webkit_created:
            view.load_uri(self._normalize(url))
        return view

    def _make_tab(self, view, text):
        """Scheda a pillola (EventBox cliccabile): favicon + titolo + chiudi."""
        ev = Gtk.EventBox()
        ev.get_style_context().add_class("nxs-tab")

        def on_press(_w, event):
            if event.button == 1:
                self._set_active_tab(view)
                return True
            if event.button == 2:      # click centrale: chiudi la scheda
                self.close_tab(view)
                return True
            return False

        ev.connect("button-press-event", on_press)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        box.set_margin_start(6)
        box.set_margin_end(6)
        img = Gtk.Image.new_from_icon_name("text-html", Gtk.IconSize.MENU)
        lbl = Gtk.Label(label=text)
        lbl.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        lbl.set_max_width_chars(18)
        close = Gtk.Button()
        close.set_relief(Gtk.ReliefStyle.NONE)
        close.set_image(Gtk.Image.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU))
        close.connect("clicked", lambda _w: self.close_tab(view))
        box.pack_start(img, False, False, 0)
        box.pack_start(lbl, False, False, 0)
        box.pack_start(close, False, False, 0)
        ev.add(box)
        self._tabs[view] = ev
        self._tab_labels[view] = (box, img, lbl)
        return ev

    def _set_active_tab(self, view):
        """Evidenzia la scheda attiva e mostra il suo contenuto nello stack."""
        for v, ev in list(self._tabs.items()):
            ctx = ev.get_style_context()
            if v is view:
                ctx.add_class("nxs-tab-active")
            else:
                ctx.remove_class("nxs-tab-active")
        if view is not None:
            if self.stack.get_visible_child() is not view:
                self.stack.set_visible_child(view)
            self.url_bar.set_text(view.get_uri() or "")

    def _on_stack_child(self, _s, _p):
        v = self.stack.get_visible_child()
        if v is not None:
            self.url_bar.set_text(v.get_uri() or "")

    def close_tab(self, view):
        if view not in self._tabs or len(self.stack.get_children()) <= 1:
            return
        self.tab_box.remove(self._tabs.pop(view))
        self._tab_labels.pop(view, None)
        self._view_mode.pop(view, None)
        self.stack.remove(view)
        view.destroy()
        cur = self.stack.get_visible_child()
        if cur is not None:
            self._set_active_tab(cur)

    def current_view(self):
        return self.stack.get_visible_child()

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
        views = self.stack.get_children()
        try:
            idx = views.index(cur)
        except ValueError:
            idx = 0
        uri = cur.get_uri() or config.get("homepage", "https://duckduckgo.com")
        ev = self._tabs.get(cur)
        if ev is not None:
            self.tab_box.remove(ev)
        self._tab_labels.pop(cur, None)
        self._view_mode.pop(cur, None)
        self.stack.remove(cur)
        cur.destroy()
        newv = self.new_tab(uri, switch=True)
        # Gtk.Stack non ha reorder_child: l'ordine dello stack non conta (la
        # scheda visibile la fissiamo sempre esplicitamente), conta solo la
        # striscia visuale -> riordiniamo la Gtk.Box (che lo supporta).
        if idx < len(self.tab_box.get_children()):
            self.tab_box.reorder_child(self._tabs[newv], idx)
        self._set_active_tab(newv)

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

    def _on_title(self, view, _p):
        entry = self._tab_labels.get(view)
        if entry:
            box, _img, lbl = entry
            title = view.get_title() or "Nuova Tab"
            lbl.set_text(title)
            box.set_tooltip_text(title)

    def _on_uri(self, view, _p):
        if view is self.current_view():
            self.url_bar.set_text(view.get_uri() or "")

    def _on_progress(self, view, _p):
        if view is self.current_view():
            prog = view.get_estimated_load_progress()
            if self._is_fullscreen:
                self.progress.hide()
            elif prog < 1.0:
                self.progress.set_fraction(prog)
                self.progress.show()
            else:
                self.progress.hide()

    def _on_favicon(self, view, _p):
        entry = self._tab_labels.get(view)
        if not entry:
            return
        _box, img, _lbl = entry
        try:
            surface = view.get_favicon()
            if surface is None:
                return
            w, h = surface.get_width(), surface.get_height()
            pix = Gdk.pixbuf_get_from_surface(surface, 0, 0, w, h)
            if pix is not None:
                img.set_from_pixbuf(pix.scale_simple(16, 16, 2))
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
        # In schermo intero nascondiamo TUTTO il cromo del browser: striscia
        # schede, barra navigazione, linea di progress e sidebar (rail+pannello).
        # Cosi' F11 da' un vero fullscreen "kiosk" con solo la pagina; prima
        # restavano visibili sidebar e schede ("parti che non scompaiono").
        # Le schede si cambiano comunque con Ctrl+Tab... no: con la tab attiva
        # cliccata da prima, o col click (non visibile). Ripristiniamo uscendo.
        vis = not self._is_fullscreen
        for bar in (getattr(self, "_tabstrip", None),
                    getattr(self, "_navbar", None),
                    getattr(self, "_sidebar", None)):
            if bar is not None:
                bar.set_visible(vis)
        # Anche la linea di progress sparisce in schermo intero (la rimette
        # _on_progress se una pagina sta caricando uscendo dal kiosk).
        if not vis:
            self.progress.hide()
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
        """Riga preferito. COLLASSATA: SOLO l'icona (grande e centrata) -> la
        colonna verticale delle icone sulla barra. APERTA: icona piccola +
        titolo + URL."""
        row = Gtk.ListBoxRow()
        row.bookmark = (title, url)
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        hbox.set_margin_top(3); hbox.set_margin_bottom(3)
        hbox.set_margin_start(4); hbox.set_margin_end(4)
        minimized = self.bookmarks_minimized
        icon_size = 22 if minimized else 16
        icon = Gtk.Image.new_from_icon_name("user-bookmarks", Gtk.IconSize.MENU)
        icon.set_pixel_size(icon_size)
        # Collassata: icona centrata nella colonna (l'header e' nascosto e la
        # sidebar si stringe davvero a SIDEBAR_MIN).
        icon.set_halign(Gtk.Align.CENTER if minimized else Gtk.Align.START)
        hbox.pack_start(icon, minimized, minimized, 0)
        self._apply_bookmark_favicon(icon, url, icon_size)
        if not minimized:
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            # width_chars basso (minimo) + ellissi: l'etichetta si adatta alla
            # larghezza REALE della sidebar (non forza il box oltre).
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
                      "https://%s/favicon.png" % domain,
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
        # ICO con frame PNG compressi: gdk-pixbuf non legge il contenitore
        # ("Compressed icons are not supported"). Estraiamo il PNG e salviamo
        # QUELLO in cache, cosi' new_from_file_at_size lo decodifica al reload.
        png = self._extract_png_from_ico(data)
        if png:
            data = png
        try:
            self._fav_dir.mkdir(parents=True, exist_ok=True)
            with open(self._fav_dir / (domain + ".img"), "wb") as f:
                f.write(data)
        except Exception:
            return
        # ricarica la lista sul thread principale: la nuova favicon compare
        GLib.idle_add(self.load_bookmarks)

    @staticmethod
    def _extract_png_from_ico(data):
        """Estrae il frame PNG da un contenitore ICO, se presente. Molti siti
        servono un favicon.ico con frame PNG compressi: il loader di gdk-pixbuf
        li rifiuta ("Compressed icons are not supported"). Ritorna i byte PNG
        o None."""
        if not data or len(data) < 22 or data[:4] != b"\x00\x00\x01\x00":
            return None
        try:
            count = data[4] | (data[5] << 8)
            for i in range(count):
                off = 6 + i * 16            # directory entry
                if off + 16 > len(data):
                    break
                size = int.from_bytes(data[off + 8:off + 12], "little")
                pos = int.from_bytes(data[off + 12:off + 16], "little")
                blob = data[pos:pos + size]
                if blob[:8] == b"\x89PNG\r\n\x1a\n":
                    return blob
        except Exception:
            return None
        return None

    @staticmethod
    def _valid_image(data):
        """True se i byte sono un'immagine decodificabile (ICO/PNG/GIF...),
        includendo gli ICO con frame PNG compressi (estratti a mano)."""
        try:
            loader = GdkPixbuf.PixbufLoader()
            loader.write(data)
            loader.close()
            if loader.get_pixbuf() is not None:
                return True
        except Exception:
            pass
        return Browser._extract_png_from_ico(data) is not None

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
        """Override accent del PROFILO attivo (pentest/forensics/osint/web):
        il clone Firefox mantiene la struttura e i colori ufficiali, ma l'accent
        del profilo NexusSec colora gli elementi chiave, come farebbe un tema
        Firefox personalizzato: ring della URL bar, linea della tab attiva,
        barra di progress, preferito selezionato e badge stealth."""
        a = self._profile_accent()
        try:
            h = a.lstrip("#")
            r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        except (ValueError, IndexError):
            r, g, b = 0, 229, 255
        rgb = "%d,%d,%d" % (r, g, b)
        return ("""
.nxs-urlbar:focus { border-color: %(a)s;
  box-shadow: 0 0 0 3px rgba(%(rgb)s, 0.28); }
.nxs-tab-active, .nxs-tab-active:hover { box-shadow: inset 0 1px 0 %(a)s; }
.nxs-progress progress { background: %(a)s; }
.nxs-bm-list row:selected .nxs-bm-title { color: %(a)s; }
.nxs-stealth-on { color: %(a)s; font-weight: bold; }
.nxs-stealth-off { color: #9d9da6; font-weight: normal; }
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
