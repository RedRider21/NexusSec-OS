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


if __name__ == "__main__":
    raise SystemExit(main())
