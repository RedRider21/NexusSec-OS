"""Backend di `nxs-wizard`.

  nxs-wizard                     -> apre la GUI (scelta procedura)
  nxs-wizard gui [id]            -> GUI, eventualmente sul wizard <id>
  nxs-wizard new                 -> GUI sul costruttore di wizard personalizzati
  nxs-wizard list                -> elenca le procedure disponibili
  nxs-wizard run <id> k=v ...    -> esegue headless una procedura
      chiavi speciali: mode=<id modalita'>  opt=<id1,id2,...>  (opzioni attive)
      esempio: nxs-wizard run pentest-quick target=10.0.0.5 mode=deep opt=osdetect,vulnscan
"""
from __future__ import annotations

import sys

from . import recipes, runner


def _print_list() -> None:
    ws = recipes.all_wizards()
    if not ws:
        print("(nessuna procedura definita)")
        return
    for wid, w in ws.items():
        tag = "personalizzato" if w.get("custom") else w.get("profile", "-")
        print(f"{wid:18}  {w.get('name', ''):28}  [{tag}]")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or argv[0] in ("gui", "-g", "--gui"):
        from . import gui
        wid = argv[1] if len(argv) > 1 else None
        return gui.main(wid)

    cmd = argv[0]
    if cmd in ("new", "build", "create"):
        from . import gui
        return gui.main(start_builder=True)
    if cmd in ("list", "ls"):
        _print_list()
        return 0
    if cmd == "run":
        if len(argv) < 2:
            print("uso: nxs-wizard run <id> campo=valore ... [mode=<id>] [opt=<id1,id2>]")
            return 2
        wid = argv[1]
        values = {}
        mode = None
        options = None
        stealth = False
        for kv in argv[2:]:
            if "=" not in kv:
                continue
            k, v = kv.split("=", 1)
            if k == "mode":
                mode = v
            elif k in ("opt", "opts", "options"):
                options = [x.strip() for x in v.split(",") if x.strip()]
            elif k == "stealth":
                stealth = v.strip().lower() in ("1", "on", "true", "si", "yes")
            else:
                values[k] = v
        ok = runner.run_wizard(wid, values, print, mode=mode, options=options,
                               stealth=stealth)
        return 0 if ok else 1

    print(f"comando sconosciuto: {cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
