# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""Agente consulente (Fase 1): costruisce il contesto read-only e il system
prompt, interroga il backend e registra un audit trail locale.

Fase 1 = READ-ONLY: l'agente risponde e PROPONE comandi (in blocchi ```), ma
NON li esegue. L'esecuzione confermata arrivera' in Fase 2."""
from __future__ import annotations

import datetime as _dt
import sys

from . import backend, config

SYSTEM_IT = """Sei l'assistente di NexusSec OS, una distro live di cybersecurity
basata su Alpine Linux (musl, apk, OpenRC; desktop Openbox; tool isolati in
container Podman o sandbox bubblewrap). Aiuti l'operatore in italiano, con
risposte concise e tecniche.

REGOLE FERME (non negoziabili su una distro di sicurezza):
- Sei un CONSULENTE: spieghi e PROPONI i comandi, ma NON li esegui. Mostra ogni
  comando in un blocco di codice ``` cosi' l'operatore lo copia e lancia dopo
  averlo valutato.
- Rispetta il profilo attivo: in Forensics i dischi non si scrivono (montaggio
  in sola lettura); in OSINT si resta passivi. Non suggerire azioni che violano
  il profilo corrente.
- Usa gli strumenti NexusSec quando pertinenti: `nxs-tool install/launch <tool>`
  per l'arsenale, `nxs-profile` per i profili, `nxs-harden`, `nxs-firewall`,
  `nxs-persist`, `nxs-anon`, HORUS per l'OSINT.
- Non inventare comandi o opzioni: se non sei sicuro, dillo.
- Ricorda all'operatore che agisce sotto la propria responsabilita' e solo su
  sistemi che e' autorizzato a testare."""


def _context() -> str:
    """Contesto read-only: profilo attivo e alcuni tool installati."""
    lines = []
    try:
        sys.path.insert(0, "/usr/local/lib")
        from nxs_profiles import model  # noqa: E402
        prof = model.current_profile()
        lines.append(f"Profilo attivo: {prof}")
    except Exception:                          # noqa: BLE001
        pass
    return "\n".join(lines)


def _audit(prompt: str, reply: str) -> None:
    try:
        config.CONF_DIR.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().isoformat(timespec="seconds")
        with open(config.AUDIT, "a") as f:
            f.write(f"[{ts}] Q: {prompt[:200]}\n")
            f.write(f"[{ts}] A: {reply[:200]}\n")
    except Exception:                          # noqa: BLE001
        pass


def ask(prompt: str, history: list[dict] | None = None) -> str:
    """Una domanda -> risposta (con contesto + audit). `history` opzionale per la
    conversazione continua nella REPL/pannello."""
    ctx = _context()
    sysmsg = SYSTEM_IT + (f"\n\nContesto corrente:\n{ctx}" if ctx else "")
    messages = [{"role": "system", "content": sysmsg}]
    if history:
        messages += history
    messages.append({"role": "user", "content": prompt})
    reply = backend.chat(messages)
    _audit(prompt, reply)
    return reply
