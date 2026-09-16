# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""Configurazione dell'agente AI: ~/.config/nxs/ai.json.

Le chiavi API vivono SOLO qui (mai nel repo/overlay), come per aisstream/HORUS.
Default 'off': finche' l'admin non sceglie un backend dal pannello, la IA e'
inattiva e non contatta nulla."""
from __future__ import annotations

import json
import os
from pathlib import Path

CONF_DIR = Path(os.environ.get("NXS_CONF_DIR", Path.home() / ".config" / "nxs"))
CONF = CONF_DIR / "ai.json"
AUDIT = CONF_DIR / "ai-audit.log"

# Modelli locali (ollama) proposti nel pannello. Default scelto per la live in
# RAM da 4GB: qwen2.5:3b (~2GB Q4) e' il miglior compromesso; per 4GB "stretti"
# c'e' qwen2.5:1.5b/llama3.2:1b. I piu' grandi richiedono piu' RAM/persistenza.
LOCAL_MODELS = [
    ("llama3.2:1b", "Llama 3.2 1B - minimo, molto leggero (~0.8 GB)"),
    ("qwen2.5:1.5b", "Qwen2.5 1.5B - leggero, ok con 4GB (~1.0 GB)"),
    ("qwen2.5:3b", "Qwen2.5 3B - consigliato, buon equilibrio (~2.0 GB)"),
    ("llama3.2:3b", "Llama 3.2 3B - alternativa 3B (~2.0 GB)"),
    ("gemma2:2b", "Gemma 2 2B - compatto e capace (~1.6 GB)"),
    ("qwen2.5:7b", "Qwen2.5 7B - qualita' alta, serve molta RAM (~4.7 GB)"),
]
DEFAULT_LOCAL_MODEL = "qwen2.5:3b"

DEFAULTS = {
    "backend": "off",              # off | local | cloud
    "consent_cloud": False,        # il contesto puo' uscire verso il cloud?
    "allow_exec": False,           # Fase 2: esecuzione confermata dei comandi (sandbox)
    "cloud": {
        "endpoint": "",            # es. https://api.openai.com  oppure il proprio AIos
        "api_key": "",
        "model": "",
    },
    "local": {
        "model": DEFAULT_LOCAL_MODEL,
        "host": "127.0.0.1:11434",  # server ollama locale
    },
}


def load() -> dict:
    """Carica la config unendo i default (robusto a file assente/corrotto)."""
    data = dict(DEFAULTS)
    data["cloud"] = dict(DEFAULTS["cloud"])
    data["local"] = dict(DEFAULTS["local"])
    try:
        raw = json.loads(CONF.read_text())
        for k, v in raw.items():
            if isinstance(v, dict) and isinstance(data.get(k), dict):
                data[k].update(v)
            else:
                data[k] = v
    except Exception:                          # noqa: BLE001
        pass
    return data


def save(data: dict) -> None:
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    CONF.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    try:
        CONF.chmod(0o600)                      # contiene la chiave API
    except Exception:                          # noqa: BLE001
        pass


def get(key: str, default=None):
    return load().get(key, default)


def set_values(**kw) -> dict:
    """Aggiorna e salva; supporta chiavi annidate cloud.* / local.* via dict."""
    data = load()
    for k, v in kw.items():
        if isinstance(v, dict) and isinstance(data.get(k), dict):
            data[k].update(v)
        else:
            data[k] = v
    save(data)
    return data
