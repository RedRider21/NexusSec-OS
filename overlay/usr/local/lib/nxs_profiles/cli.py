"""CLI di nxs-tool: gestione profili e tool isolati.

Uso:
  nxs-tool profile                  mostra il profilo corrente
  nxs-tool profile <chiave> [--clean]  attiva profilo (apk add meta) + sfondo + accent
                                       --clean: rimuove prima il profilo precedente
  nxs-tool apply                    riapplica sfondo+accent del profilo corrente
  nxs-tool profiles                 elenca i profili disponibili
  nxs-tool list [profilo]           elenca i tool (del profilo) + stato
  nxs-tool install <tool>           installa il tool (apk add)
  nxs-tool run <tool> [args...]     esegue il tool (sandbox se NXS_ISOLATE=1)
  nxs-tool launch <tool> [args...]  installa-se-serve e poi esegue (terminale)
  nxs-tool uninstall <tool>         rimuove il tool (apk del)

  --- Persistenza tool (solo con chiavetta persistente NXSDATA) ---
  nxs-tool persisted                elenca i tool apk che verranno reinstallati al boot
  nxs-tool forget <pacchetto>       toglie un tool dalla lista (non piu' reinstallato)

  --- Arsenale Kali (qualsiasi dei ~600+ tool, anche non elencati) ---
  nxs-tool kali <pacchetto> [args...]   installa-se-serve ed esegue un tool Kali
  nxs-tool kali-install <pacchetto>     solo installa nell'ambiente Kali condiviso
  nxs-tool kali-list                    tool Kali gia presenti nell'ambiente
"""
from __future__ import annotations

import sys

from . import model, isolation


def _profile(args):
    if not args:
        key = model.current_profile()
        d = model.profile_data(key)
        print(f"{key}\t{d.get('name', key)}")
        return 0
    key = args[0]
    if key not in model.profiles():
        print(f"[!] profilo sconosciuto: {key}")
        return 1
    clean = "--clean" in args[1:]
    ok = model.activate_profile(key, clean_previous=clean)
    d = model.profile_data(key)
    print(f"[+] profilo: {d.get('name', key)}  sfondo: {model.wallpaper_path(key).name}")
    return 0 if ok else 1


def _apply(_args):
    """Riapplica sfondo + accent del profilo corrente (usato all'avvio)."""
    d = model.apply_current()
    key = model.current_profile()
    print(f"[+] profilo: {d.get('name', key)}  sfondo: {model.wallpaper_path(key).name}")
    return 0


def _profiles(_args):
    cur = model.current_profile()
    for key, d in model.profiles().items():
        mark = "*" if key == cur else " "
        print(f"{mark} {key:<10} {d.get('name','')}  - {d.get('desc','')}")
    return 0


def _list(args):
    key = args[0] if args else model.current_profile()
    tools = model.profile_tools(key)
    if not tools:
        print(f"(profilo '{key}': nessun tool specialistico)")
        return 0
    print(f"# tool del profilo '{key}':")
    for t in tools:
        ok = isolation.is_installed(t)
        method = model.tool_data(t).get("method", "apk")
        desc = model.tool_data(t).get("description", "")
        print(f"  [{'x' if ok else ' '}] {t:<14} {method:<10} {desc}")
    return 0


def _install(args):
    if not args:
        print("uso: nxs-tool install <tool>"); return 1
    return 0 if isolation.install(args[0]) else 1


def _run(args):
    if not args:
        print("uso: nxs-tool run <tool> [args...]"); return 1
    return 0 if isolation.run(args[0], " ".join(args[1:])) else 1


def _launch(args):
    if not args:
        print("uso: nxs-tool launch <tool> [args...]"); return 1
    return 0 if isolation.launch(args[0], " ".join(args[1:])) else 1


def _uninstall(args):
    if not args:
        print("uso: nxs-tool uninstall <tool>"); return 1
    return 0 if isolation.uninstall(args[0]) else 1


def _kali(args):
    """Installa-se-serve ed esegue un QUALSIASI tool dell'arsenale Kali."""
    if not args:
        print("uso: nxs-tool kali <pacchetto-kali> [args...]"); return 1
    return 0 if isolation.launch_kali_pkg(args[0], "", " ".join(args[1:])) else 1


def _kali_install(args):
    if not args:
        print("uso: nxs-tool kali-install <pacchetto-kali>"); return 1
    return 0 if isolation.install_kali_pkg(args[0]) else 1


def _kali_list(_args):
    pkgs = isolation.kali_env_pkgs()
    if not pkgs:
        print("(ambiente Kali vuoto: nessun tool ancora installato)")
        return 0
    print("# tool Kali gia presenti nell'ambiente condiviso:")
    for p in pkgs:
        print(f"  {p}")
    return 0


def _persisted(_args):
    """Elenca i tool apk registrati per la reinstallazione al boot."""
    if not isolation._persist_active():
        print("(persistenza non attiva: nessuna chiavetta NXSDATA montata)")
        return 0
    pkgs = isolation.persisted_apk_tools()
    if not pkgs:
        print("(nessun tool apk registrato: verranno aggiunti quando ne installi)")
        return 0
    print("# tool apk che il boot reinstalla (offline dalla cache):")
    for p in pkgs:
        print(f"  {p}")
    return 0


def _forget(args):
    """Toglie uno o piu' pacchetti dalla lista di persistenza."""
    if not args:
        print("uso: nxs-tool forget <pacchetto> [pacchetto...]"); return 1
    isolation._persist_forget_apk(args)
    print("rimosso dalla persistenza: " + " ".join(args))
    return 0


CMDS = {
    "profile": _profile,
    "apply": _apply,
    "profiles": _profiles,
    "list": _list,
    "install": _install,
    "run": _run,
    "launch": _launch,
    "uninstall": _uninstall,
    "persisted": _persisted,
    "forget": _forget,
    "kali": _kali,
    "kali-install": _kali_install,
    "kali-list": _kali_list,
}


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    fn = CMDS.get(cmd)
    if not fn:
        print(f"[!] comando sconosciuto: {cmd}\n{__doc__}")
        return 1
    return fn(rest)


if __name__ == "__main__":
    raise SystemExit(main())
