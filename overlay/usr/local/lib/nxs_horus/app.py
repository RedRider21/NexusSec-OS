"""HORUS - finestra GTK3 + WebKit2.

Avvia il backend locale (server.py) su 127.0.0.1 con porta effimera e apre la
SPA in una WebView. Stesso stack del NexusSec Browser (GTK3 + webkit2gtk-4.1),
gia' preinstallato nella base: nessuna dipendenza nuova.

Se WebKit non c'e' (o non c'e' display), ripiega aprendo l'URL locale nel
browser di sistema e resta vivo a servire la dashboard.
"""
from __future__ import annotations

import sys
import webbrowser

from nxs_horus import server


def _run_webkit(url):
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("WebKit2", "4.1")
    from gi.repository import Gtk, WebKit2, Gdk

    win = Gtk.Window(title="HORUS - Occhio OSINT globale")
    win.set_default_size(1280, 800)
    win.set_icon_name("nxs-horus")

    # Fondo scuro coerente finche' la pagina non ha caricato.
    css = Gtk.CssProvider()
    css.load_from_data(b"window { background:#050a14; }")
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), css,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    view = WebKit2.WebView()
    # Contesto effimero: la dashboard e' locale, non serve cronologia/cache.
    settings = view.get_settings()
    settings.set_property("enable-developer-extras", True)
    win.add(view)
    view.load_uri(url)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    httpd, port = server.serve_in_thread()
    url = "http://127.0.0.1:%d/" % port

    # Modo "solo server": stampa l'URL e resta in ascolto (utile per debug/test).
    if "--serve" in argv:
        print(url, flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        return 0

    try:
        _run_webkit(url)
    except Exception as e:
        # Nessun WebKit/display: ripiega sul browser di sistema.
        sys.stderr.write("HORUS: WebKit non disponibile (%s); apro nel browser.\n" % e)
        try:
            webbrowser.open(url)
        except Exception:
            print("HORUS attivo su %s (Ctrl-C per uscire)" % url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0
