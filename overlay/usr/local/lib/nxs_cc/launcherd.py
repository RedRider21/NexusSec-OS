"""nxs-launcherd - avvio "caldo" delle app GTK NexusSec (fork-zygote).

Importa UNA sola volta gi/GTK + i moduli pesanti nostri (SENZA aprire un
display) e resta in ascolto su un socket UNIX. A ogni richiesta fa `fork()` e
nel FIGLIO esegue l'entry point ESISTENTE (che apre la finestra e gira il suo
`Gtk.main()`): il figlio eredita i moduli gia' importati/compilati, quindi salta
il costo di import (~100-200 ms, di piu' su HW lento / primo avvio in RAM).

Sicurezza:
- il PADRE non apre mai un display ne' avvia un main loop GTK (solo socket):
  cosi' `fork()` e' sicuro (nessuno stato GTK/thread da duplicare);
- i figli sono processi INDIPENDENTI: un crash di una finestra non tocca il
  demone ne' le altre finestre;
- se il demone non c'e', il client `nxs-launch` ricade sull'avvio normale, quindi
  le app funzionano comunque.

Non e' un servizio critico: se non parte, il desktop resta identico (solo un po'
piu' lento all'apertura delle app).
"""
import os
import signal
import socket
import sys
import traceback

os.environ.setdefault("GTK_IM_MODULE", "gtk-im-context-simple")

# --- import PESANTI, una volta sola (nessun display aperto qui) ---------------
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

# precarica i moduli nostri (bytecode + risoluzione import) una volta
import nxs_cc.common          # noqa: E402,F401
import nxs_cc.views           # noqa: E402,F401
import nxs_cc.main            # noqa: E402
import nxs_profiles.model     # noqa: E402,F401
import nxs_profiles.selector  # noqa: E402
try:
    import nxs_screensaver.app as _ss   # noqa: E402
except Exception:                        # noqa: BLE001
    _ss = None


def _sock_path():
    base = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    return os.environ.get("NXS_LAUNCHERD_SOCK") or os.path.join(base, "nxs-launcherd.sock")


def _run_child(app, args):
    """Esegue nel FIGLIO l'entry esistente (apre finestra + Gtk.main())."""
    if app == "cc":
        sys.argv = ["nxs-control-center"] + args
        nxs_cc.main.run()
    elif app == "profile":
        sys.argv = ["nxs-profile"] + args
        nxs_profiles.selector.run(args)
    elif app == "screensaver" and _ss is not None:
        _ss.main(args)
    elif app == "selftest":
        # verifica non-grafica (per i test): tocca un file e esce, niente finestra
        try:
            open(args[0] if args else "/tmp/nxs-launcherd-selftest.ok", "w").close()
        except OSError:
            pass
    else:
        os._exit(2)


def _spawn(srv, conn, app, args):
    pid = os.fork()
    if pid != 0:
        return                       # PADRE: prosegue con l'ascolto
    # --- FIGLIO ---
    try:
        srv.close()                  # non tenere il socket del demone
    except OSError:
        pass
    try:
        conn.close()
    except OSError:
        pass
    try:
        os.setsid()
    except OSError:
        pass
    try:
        _run_child(app, args)
    except SystemExit:
        pass
    except Exception:                # noqa: BLE001
        traceback.print_exc()
    os._exit(0)


def main():
    # auto-reap dei figli (niente zombie); su Linux SIG_IGN li raccoglie da solo
    try:
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)
    except (ValueError, OSError):
        pass
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
    sys.stderr.write("nxs-launcherd: pronto su %s\n" % path)
    sys.stderr.flush()
    while True:
        try:
            conn, _ = srv.accept()
        except OSError:
            continue
        try:
            data = conn.recv(4096).decode("utf-8", "replace").strip()
        except OSError:
            data = ""
        parts = data.split()
        if parts and parts[0] != "ping":
            _spawn(srv, conn, parts[0], parts[1:])
        # conferma al client (dopo il fork: la richiesta e' stata presa in carico)
        try:
            conn.sendall(b"ok\n")
        except OSError:
            pass
        try:
            conn.close()
        except OSError:
            pass


if __name__ == "__main__":
    main()
