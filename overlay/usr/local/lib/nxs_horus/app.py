# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""HORUS - finestre GTK3 + WebKit2.

Avvia il backend locale (server.py) su 127.0.0.1 con porta effimera e apre la
SPA in una WebView. Stesso stack del NexusSec Browser (GTK3 + webkit2gtk-4.1),
gia' preinstallato nella base: nessuna dipendenza nuova.

MULTI-SCHERMO (2026-11): un SOLO processo/server per sessione, tante finestre.
    nxs-horus                    finestra con la vista completa
    nxs-horus --vista cyber      finestra con la vista Cyber (o disastri,
                                 trasporti, geopolitica)
Se HORUS e' gia' aperto, la seconda invocazione NON avvia un altro server:
chiede a quello attivo (POST /api/open-window) di aprire un'altra finestra,
cosi' i dati si scaricano una volta sola anche con 4 monitor. Il pulsante
"nuova finestra" nella pagina usa lo stesso meccanismo. Il processo termina
quando si chiude l'ultima finestra.

Se WebKit non c'e' (o non c'e' display), ripiega aprendo l'URL locale nel
browser di sistema e resta vivo a servire la dashboard.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
import webbrowser

from nxs_horus import server

VISTE = ("completa", "cyber", "disastri", "trasporti", "geopolitica")


def _port_file():
    base = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    return os.path.join(base, "nxs-horus-%d.port" % os.getuid())


def _running_port():
    """Porta di un HORUS gia' attivo per questo utente (o None)."""
    try:
        port = int(open(_port_file()).read().strip())
        with urllib.request.urlopen("http://127.0.0.1:%d/api/status" % port, timeout=2):
            return port
    except Exception:          # noqa: BLE001 - file assente/stantio/server giu'
        return None


def _ask_window(port, vista):
    """Chiede all'HORUS attivo di aprire una finestra. True se l'ha aperta."""
    req = urllib.request.Request(
        "http://127.0.0.1:%d/api/open-window" % port,
        data=json.dumps({"vista": vista}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return bool(json.loads(r.read().decode()).get("gtk"))
    except Exception:          # noqa: BLE001
        return False


def _url(port, vista):
    u = "http://127.0.0.1:%d/" % port
    return u + ("?vista=" + vista if vista and vista != "completa" else "")


class _Windows:
    """Gestore delle finestre WebKit di questo processo."""

    _TITOLI = {"cyber": "Cyber", "disastri": "Disastri e clima",
               "trasporti": "Spazio e trasporti", "geopolitica": "Geopolitica"}

    def __init__(self, port):
        import gi
        gi.require_version("Gtk", "3.0")
        try:
            gi.require_version("WebKit2", "4.1")     # Alpine / NexusSec
        except ValueError:
            gi.require_version("WebKit2", "4.0")     # distro con la sola 4.0
        from gi.repository import Gtk, WebKit2, Gdk, GLib
        self.Gtk, self.WebKit2, self.GLib = Gtk, WebKit2, GLib
        self.port = port
        self.count = 0
        # Fondo scuro coerente finche' la pagina non ha caricato.
        css = Gtk.CssProvider()
        css.load_from_data(b"window { background:#050a14; }")
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def open(self, vista=""):
        Gtk, WebKit2 = self.Gtk, self.WebKit2
        t = self._TITOLI.get(vista)
        win = Gtk.Window(title="HORUS" + (" - " + t if t else " - Occhio OSINT globale"))
        win.set_default_size(1280, 800)
        win.set_icon_name("nxs-horus")
        view = WebKit2.WebView()
        st = view.get_settings()
        st.set_property("enable-developer-extras", True)
        # La pagina riconosce di girare nella finestra nativa (pulsante "nuova
        # finestra" -> /api/open-window invece di window.open).
        st.set_user_agent_with_application_details("NexusSecHORUS", "1")
        win.add(view)
        view.load_uri(_url(self.port, vista))
        win.connect("destroy", self._closed)
        win.show_all()
        self.count += 1
        return False                       # per GLib.idle_add

    def _closed(self, _w):
        self.count -= 1
        if self.count <= 0:
            self.Gtk.main_quit()

    def request(self, vista):
        """Chiamata dal thread del server: la GUI si tocca solo dal main loop."""
        self.GLib.idle_add(self.open, vista)


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    vista = ""
    if "--vista" in argv:
        i = argv.index("--vista")
        vista = (argv[i + 1] if i + 1 < len(argv) else "").lower()
        if vista not in VISTE:
            sys.stderr.write("vista sconosciuta: %s (usa: %s)\n" % (vista, ", ".join(VISTE)))
            return 2

    # HORUS gia' aperto? Apri solo un'altra finestra sul server esistente.
    if "--serve" not in argv:
        port = _running_port()
        if port:
            if not _ask_window(port, vista):
                # HORUS attivo ma senza finestre native (ripiego su browser):
                # apriamo una scheda sullo STESSO server, niente secondo server.
                webbrowser.open(_url(port, vista))
            return 0

    httpd, port = server.serve_in_thread()

    # Modo "solo server": stampa l'URL e resta in ascolto (utile per debug/test).
    if "--serve" in argv:
        print(_url(port, vista), flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        return 0

    pf = _port_file()
    try:
        with open(pf, "w") as f:
            f.write(str(port))
    except OSError:
        pf = None
    try:
        try:
            wins = _Windows(port)
        except Exception as e:             # noqa: BLE001
            # Nessun WebKit/display: ripiega sul browser di sistema.
            sys.stderr.write("HORUS: WebKit non disponibile (%s); apro nel browser.\n" % e)
            try:
                webbrowser.open(_url(port, vista))
            except Exception:              # noqa: BLE001
                print("HORUS attivo su %s (Ctrl-C per uscire)" % _url(port, vista))
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                pass
            return 0
        server.OPEN_WINDOW = wins.request
        wins.open(vista)
        wins.Gtk.main()
    finally:
        if pf:
            try:
                if open(pf).read().strip() == str(port):
                    os.remove(pf)
            except OSError:
                pass
    return 0

