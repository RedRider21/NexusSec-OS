# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""CLI dell'assistente: `nxs-ai "domanda"` (one-shot) o `nxs-ai` (conversazione).

Fase 1: consulente read-only. Nessun comando viene eseguito dall'agente."""
from __future__ import annotations

import sys

from . import agent, backend, config

BANNER = """NexusSec - Assistente IA (consulente, non esegue comandi)
Backend: {be}{model}   |   'exit' per uscire.
"""


def _model_note(cfg) -> str:
    be = cfg.get("backend")
    if be == "local":
        return "  modello locale: " + (cfg["local"].get("model") or "?")
    if be == "cloud":
        return "  modello cloud: " + (cfg["cloud"].get("model") or "?")
    return ""


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cfg = config.load()

    if cfg.get("backend", "off") == "off":
        print("Assistente IA disattivato. Attivalo dal Centro di Controllo "
              "-> Assistente IA (scegli backend locale o cloud).", file=sys.stderr)
        return 2

    # "explain": spiega un output/errore passato via pipe o come argomenti.
    #   nmap ... 2>&1 | nxs-ai explain      |     nxs-ai explain "<incolla output>"
    if argv and argv[0] == "explain":
        text = " ".join(argv[1:]).strip()
        if not sys.stdin.isatty():
            piped = sys.stdin.read().strip()
            text = (text + "\n" + piped).strip() if text else piped
        if not text:
            print("Uso: <comando> 2>&1 | nxs-ai explain   oppure   "
                  "nxs-ai explain \"<output>\"", file=sys.stderr)
            return 2
        prompt = ("Spiega il seguente output di un comando eseguito su NexusSec: "
                  "cosa indica, l'eventuale problema e il passo successivo "
                  "(mostra i comandi da copiare). Output:\n```\n" + text[:6000] + "\n```")
        try:
            print(agent.ask(prompt))
            return 0
        except backend.AIError as e:
            print(f"[IA] {e}", file=sys.stderr)
            return 1

    # "wizard": genera una procedura guidata (catena di tool) da una descrizione
    #   nxs-ai wizard "scansione web completa di un dominio"
    if argv and argv[0] == "wizard":
        desc = " ".join(argv[1:]).strip()
        if not desc:
            print('Uso: nxs-ai wizard "descrizione dell\'obiettivo"', file=sys.stderr)
            return 2
        from . import wizardgen
        print("Genero la procedura con l'IA, un momento…")
        wiz = wizardgen.generate(desc)
        if not wiz:
            return 1
        print(f"\nBozza procedura: {wiz['name']}")
        if wiz.get("fields"):
            print("  Chiede: " + ", ".join(f["label"] for f in wiz["fields"]))
        for i, s in enumerate(wiz["steps"], 1):
            print(f"  [{i}] {s['tool']} {s['args']}")
        print()
        if not sys.stdin.isatty():
            print("(non interattivo: non salvo la procedura)")
            return 0
        import re as _re
        try:
            if input("Salvare questa procedura? [s/N] ").strip().lower() not in ("s", "si", "y", "yes"):
                print("Annullato."); return 0
            default = _re.sub(r"[^a-z0-9]+", "-", wiz["name"].lower()).strip("-") or "wizard-ia"
            slug = input(f"Nome breve/id [{default}]: ").strip() or default
        except (EOFError, KeyboardInterrupt):
            print(); return 0
        slug = _re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-") or default
        from nxs_wizards import recipes
        if recipes.save_custom(slug, wiz):
            print(f"Salvata come '{slug}'. La trovi in `nxs-wizard`, nel menu del "
                  "profilo e nel costruttore (dove puoi rifinirla).")
            return 0
        print("[IA] salvataggio non riuscito.", file=sys.stderr)
        return 1

    # one-shot
    if argv:
        prompt = " ".join(argv)
        try:
            print(agent.ask(prompt))
            return 0
        except backend.AIError as e:
            print(f"[IA] {e}", file=sys.stderr)
            return 1

    # conversazione
    print(BANNER.format(be=cfg.get("backend"), model=_model_note(cfg)))
    history: list[dict] = []
    while True:
        try:
            prompt = input("tu> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not prompt:
            continue
        if prompt.lower() in ("exit", "quit", ":q"):
            return 0
        try:
            reply = agent.ask(prompt, history)
        except backend.AIError as e:
            print(f"[IA] {e}\n", file=sys.stderr)
            continue
        print(f"\n{reply}\n")
        history += [{"role": "user", "content": prompt},
                    {"role": "assistant", "content": reply}]
        history = history[-12:]                 # limita la memoria di contesto
        # Fase 2: se abilitata, offri l'esecuzione CONFERMATA dei comandi proposti
        if cfg.get("allow_exec") and sys.stdin.isatty():
            _offer_exec(reply, history)


def _offer_exec(reply: str, history: list[dict]) -> None:
    """Elenca i comandi proposti e, su conferma esplicita, li esegue in sandbox.
    Nulla parte senza che l'utente scelga il comando e confermi (s/N)."""
    from . import executor
    cmds = executor.extract_commands(reply)
    if not cmds:
        return
    print("Comandi proposti (esecuzione confermata in sandbox):")
    for i, c in enumerate(cmds, 1):
        print(f"  [{i}] {c}")
    try:
        sel = input("Esegui quale? (numero, Invio = nessuno) ").strip()
    except (EOFError, KeyboardInterrupt):
        print(); return
    if not sel.isdigit() or not (1 <= int(sel) <= len(cmds)):
        return
    cmd = cmds[int(sel) - 1]
    level, needs_net, why = executor.classify(cmd)
    if level == "blocked":
        print(f"[IA] Comando NON eseguibile: {why}. Valutalo e lancialo a mano se sicuro.")
        return
    net = "CON accesso di rete" if needs_net else "senza rete"
    try:
        ok = input(f"Confermi l'esecuzione ({net}) di:\n    {cmd}\n[s/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print(); return
    if ok not in ("s", "si", "y", "yes"):
        print("Annullato.")
        return
    rc, out = executor.run_confirmed(cmd, needs_net)
    # rimanda l'output all'agente cosi' puo' commentarlo al giro successivo
    history.append({"role": "user",
                    "content": f"Ho eseguito `{cmd}` (uscita {rc}). Output:\n{out[:3000]}"})


if __name__ == "__main__":
    raise SystemExit(main())
