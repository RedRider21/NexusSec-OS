"""nxs-launcherd - avvio "caldo" delle app GTK NexusSec (servizio IN-PROCESS).

Un unico processo residente importa gi/GTK + i moduli del desktop UNA volta,
apre il display e gira un suo `Gtk.main()`. Le richieste arrivano su un socket
UNIX (integrato nel main loop GLib) e la finestra dell'app viene creata DENTRO
questo processo via `GLib.idle_add`: nessun nuovo processo, nessun re-import ->
apertura quasi immediata.

Perche' NON fork: il fork dopo l'import di GTK e' inaffidabile (se GLib/gio hanno
avviato un thread, il figlio si blocca/crasha) -> in VM le app non partivano.
Il modello in-process elimina il fork del tutto.

Robustezza:
- ogni finestra viene aperta SENZA collegare `Gtk.main_quit` alla chiusura, cosi'
  chiudere una finestra NON spegne il servizio (le altre restano);
- ogni apertura e' protetta da try/except: un errore in una vista non abbatte il
  servizio;
- se il servizio non c'e' o muore, il client `nxs-launch` ricade sull'avvio
  normale (python3 -m ...), quindi le app funzionano comunque.

Gestisce: cc (Centro di Controllo e sue viste), profile (selettore profili). Il
salvaschermo NON passa di qui (ha un suo Gtk.main a schermo intero).
"""
import os
import socket
import sys
import traceback

os.environ.setdefault("GTK_IM_MODULE", "gtk-im-context-simple")

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
try:
    gi.require_version("GdkPixbuf", "2.0")
except ValueError:
    pass
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf  # noqa: E402,F401
try:
    from gi.repository import Pango  # noqa: E402,F401
except Exception:                    # noqa: BLE001
    pass

import nxs_cc.common          # noqa: E402
import nxs_cc.views           # noqa: E402,F401
import nxs_cc.main            # noqa: E402
import nxs_profiles.model     # noqa: E402,F401
import nxs_profiles.selector  # noqa: E402


def _sock_path():
    base = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    return os.environ.get("NXS_LAUNCHERD_SOCK") or os.path.join(base, "nxs-launcherd.sock")


def _detach_quit(win):
    """Scollega Gtk.main_quit dalla chiusura della finestra: nel servizio
    condiviso una finestra che si chiude NON deve spegnere il main loop."""
    try:
        win.disconnect_by_func(Gtk.main_quit)
    except (TypeError, Exception):   # noqa: BLE001
        pass


def _open(app, args):
    """Apre l'app richiesta DENTRO il processo servizio (chiamata da idle_add)."""
    try:
        if app == "cc":
            m = nxs_cc.main
            m.apply_css()
            vm = getattr(m, "VIEW_MAP", {})
            if args and args[0] in vm:
                # una vista standalone (es. "appearance"): si chiude da se' con
                # win.destroy() (non tocca il main loop)
                vm[args[0]]()
            else:
                win = m.build_window()
                _detach_quit(win)
                win.show_all()
        elif app == "profile":
            w = nxs_profiles.selector.Selector()
            _detach_quit(w)
            w.show_all()
        # 'screensaver' e altro: non gestiti qui (fallback lato client)
    except Exception:                # noqa: BLE001
        traceback.print_exc()
    return False                     # one-shot per idle_add


def _on_socket(fd, _cond, srv):
    try:
        conn, _ = srv.accept()
    except OSError:
        return True
    try:
        data = conn.recv(4096).decode("utf-8", "replace").strip()
    except OSError:
        data = ""
    try:
        conn.sendall(b"ok\n")
    except OSError:
        pass
    try:
        conn.close()
    except OSError:
        pass
    if data and data != "ping":
        parts = data.split()
        if parts[0] in ("cc", "profile"):
            GLib.idle_add(_open, parts[0], parts[1:])
    return True                       # continua ad ascoltare


def main():
    path = _sock_path()
    try:
        os.unlink(path)
    except OSError:
        pass
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    srv.listen(8)
    srv.setblocking(False)
    GLib.io_add_watch(srv.fileno(), GLib.IO_IN, _on_socket, srv)
    sys.stderr.write("nxs-launcherd: pronto (in-process) su %s\n" % path)
    sys.stderr.flush()
    Gtk.main()


if __name__ == "__main__":
    main()
