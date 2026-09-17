# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""Fase 3b - assistente d'indagine per HORUS (OSINT/GEOINT).

Riusa il backend IA di NexusSec (nxs_ai): stesso motore locale (ollama) o cloud
(OpenAI-compatibile) configurato nel Centro di Controllo, stesso consenso e audit.
L'assistente lavora SOLO sui dati del fascicolo forniti da HORUS: riassume,
correla, suggerisce pivot leciti e abbozza il report. NON esegue scansioni.

Locale-first per la privacy: con backend locale il fascicolo non lascia la
macchina; con backend cloud esce solo se l'utente ha dato il consenso (gestito
da nxs_ai.backend)."""
from __future__ import annotations

import datetime as _dt

from . import backend, config

SYSTEM_OSINT = """Sei un analista OSINT/GEOINT che assiste l'operatore dentro
HORUS (la plancia investigativa di NexusSec OS). Regole ferme:
- Lavori ESCLUSIVAMENTE sui dati del fascicolo che ti vengono forniti: non
  inventare entita', indicatori, relazioni o fatti che non sono nel contesto.
- Sei un CONSULENTE: suggerisci pivot e passi, ma NON esegui scansioni ne'
  comandi. Quando proponi uno strumento, cita quelli gia' disponibili in
  NexusSec/HORUS (whois, dig, nmap, subfinder, theHarvester, maigret, holehe,
  h8mail, phoneinfoga, ecc.) e ricorda che vanno lanciati dall'operatore.
- Attieniti a fonti e tecniche LECITE e all'ambito autorizzato dell'indagine.
- Rispondi in italiano, conciso e strutturato (elenchi puntati dove utile)."""

_PROMPTS = {
    "summary": ("Riassumi il fascicolo d'indagine: entita' principali, indicatori "
                "chiave, collegamenti gia' emersi e stato attuale. Evidenzia lacune."),
    "pivot": ("Sulla base del fascicolo, elenca i prossimi PIVOT OSINT piu' utili: "
              "cosa approfondire, perche', e con quali strumenti leciti gia' presenti "
              "in HORUS/NexusSec. Ordina per priorita'."),
    "report": ("Scrivi una BOZZA di report d'indagine, in tono professionale e "
               "narrativo: contesto, cosa e' stato trovato, collegamenti, e "
               "conclusioni provvisorie. Solo dai dati del fascicolo."),
}


def analyze(task: str, context: str, question: str = "") -> str:
    """Esegue un compito d'analisi sul fascicolo. task: summary|pivot|report|ask.
    Solleva backend.AIError (gestita dal chiamante) su problemi del backend."""
    context = (context or "").strip()[:12000]
    if task == "ask":
        instr = (question or "").strip()
        if not instr:
            raise backend.AIError("Nessuna domanda fornita.")
    else:
        instr = _PROMPTS.get(task)
        if not instr:
            raise backend.AIError(f"Compito sconosciuto: {task}")
    user = instr + ("\n\n--- FASCICOLO ---\n" + context if context
                    else "\n\n(Il fascicolo e' vuoto.)")
    reply = backend.chat([{"role": "system", "content": SYSTEM_OSINT},
                          {"role": "user", "content": user}])
    _audit(task, question or task, reply)
    return reply


def _audit(task: str, prompt: str, reply: str) -> None:
    try:
        config.CONF_DIR.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().isoformat(timespec="seconds")
        with open(config.AUDIT, "a") as f:
            f.write(f"[{ts}] HORUS/{task}: {prompt[:160]}\n")
            f.write(f"[{ts}] A: {reply[:200]}\n")
    except Exception:                          # noqa: BLE001
        pass
