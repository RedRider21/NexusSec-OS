# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""Fase 3 - generatore di procedure guidate (wizard) con l'IA.

Approccio ROBUSTO (un modello piccolo non deve produrre JSON complesso):
- l'IA propone solo la SEQUENZA di comandi (un tool per riga, con <TARGET> come
  segnaposto del bersaglio), usando SOLO tool dell'arsenale reale;
- il CODICE costruisce il wizard JSON valido attorno a quella sequenza e lo
  valida (tool nel catalogo, niente comandi distruttivi, niente pipe/redirect:
  il runner esegue un solo tool+args per step via isolation.build_cmd);
- l'utente RIVEDE la bozza e conferma prima di salvarla.

Il wizard salvato riusa il runner esistente (installa i tool on-demand, applica
il profilo, ecc.): la IA non esegue nulla qui, prepara solo una ricetta."""
from __future__ import annotations

import json
import re
import sys

from . import agent, executor

_BAD_SHELL = re.compile(r"[|;&><`]|\$\(|\&\&|\|\|")


def _catalog_names() -> set[str]:
    try:
        sys.path.insert(0, "/usr/local/lib")
        from nxs_profiles import model
        path = getattr(model, "REPO_JSON", "/usr/local/share/nexussec/repo.json")
        return set(json.load(open(path)).get("tools", {}))
    except Exception:                          # noqa: BLE001
        return set()


def _current_profile() -> str:
    try:
        from nxs_profiles import model
        return model.current_profile()
    except Exception:                          # noqa: BLE001
        return "base"


def _args_template(rest: str) -> str:
    """Rende gli argomenti sicuri per str.format del runner: raddoppia le graffe
    letterali (es. awk '{print}') e converte <TARGET> nel segnaposto {target}."""
    a = rest.replace("{", "{{").replace("}", "}}")
    a = re.sub(r"<\s*target\s*>", "{target}", a, flags=re.I)
    return a.strip()


def generate(description: str, log=print) -> dict | None:
    """Chiede all'IA la catena di comandi e costruisce il wizard (bozza).
    Ritorna il dict del wizard o None se non si e' ricavato nulla di valido."""
    catalog = _catalog_names()
    prompt = (
        "Devi comporre una PROCEDURA per NexusSec OS per questo obiettivo:\n"
        f"\"{description}\"\n\n"
        "Elenca i comandi in SEQUENZA, in un UNICO blocco ```, UN comando per "
        "riga. Regole ferme:\n"
        "- usa SOLO strumenti dell'arsenale NexusSec (te li ho elencati nel "
        "contesto);\n"
        "- un solo strumento per riga, con i suoi argomenti; NIENTE pipe, "
        "redirezioni, && o sottoshell;\n"
        "- usa <TARGET> come segnaposto per il bersaglio (dominio/IP/URL);\n"
        "- niente comandi distruttivi o sui dischi;\n"
        "- nessuna spiegazione: SOLO i comandi nel blocco.")
    try:
        reply = agent.ask(prompt)
    except Exception as e:                     # noqa: BLE001
        log(f"[IA] impossibile generare la procedura: {e}")
        return None

    steps, skipped = [], []
    for cmd in executor.extract_commands(reply):
        # il segnaposto <TARGET> contiene '<'/'>': va neutralizzato PRIMA di
        # controllare pipe/redirezioni, altrimenti falsi positivi.
        probe = re.sub(r"<\s*target\s*>", "TARGET", cmd, flags=re.I)
        if _BAD_SHELL.search(probe):
            skipped.append((cmd, "pipe/redirezione non ammessa in uno step"))
            continue
        level, _net, why = executor.classify(cmd)
        if level == "blocked":
            skipped.append((cmd, why))
            continue
        parts = cmd.split()
        tool = re.sub(r"^.*/", "", parts[0])
        if catalog and tool not in catalog:
            skipped.append((cmd, f"'{tool}' non e' nel catalogo NexusSec"))
            continue
        rest = cmd[len(parts[0]):].strip()
        steps.append({"tool": tool,
                      "desc": f"{tool}: {description[:60]}",
                      "args": _args_template(rest)})
    for cmd, why in skipped:
        log(f"[IA] step scartato ({why}): {cmd}")
    if not steps:
        log("[IA] nessuno step valido ricavato dalla risposta.")
        return None

    uses_target = any("{target}" in s["args"] for s in steps)
    wiz = {
        "name": description[:48].strip().capitalize() or "Procedura IA",
        "profile": _current_profile(),
        "icon": "system-run-symbolic",
        "description": f"Procedura generata dall'assistente IA: {description}",
        "stealth_default": False,
        "fields": ([{"key": "target",
                     "label": "Bersaglio (dominio / IP / URL)",
                     "required": True,
                     "placeholder": "es. example.com"}] if uses_target else []),
        "steps": steps,
    }
    return wiz
