# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""Backend selezionabile per l'agente AI (astrazione unica: chat()).

- LOCALE: server ollama su 127.0.0.1:11434 (API /api/chat). Il runtime e il
  modello NON si scaricano mai in automatico: se mancano, si restituisce un
  errore chiaro che invita ad attivarli dal pannello IA. Il server (gia'
  installato) viene avviato al volo se non attivo (non e' un download).
- CLOUD: endpoint compatibile OpenAI (/v1/chat/completions), quindi funziona con
  il proprio AIos, con API OpenAI e simili. Il contesto esce SOLO se l'utente ha
  dato il consenso (config.consent_cloud).

Solo stdlib (urllib/json): nessuna dipendenza aggiuntiva sulla live.
"""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import time
import urllib.request

from . import config


class AIError(Exception):
    """Errore d'uso mostrato all'utente (fail-safe, non traceback)."""


# ------------------------------------------------------------------ ollama utils
def ollama_installed() -> bool:
    return shutil.which("ollama") is not None


def _host_port() -> tuple[str, int]:
    hp = config.load()["local"].get("host", "127.0.0.1:11434")
    host, _, port = hp.partition(":")
    return host or "127.0.0.1", int(port or "11434")


def server_running() -> bool:
    host, port = _host_port()
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except Exception:                          # noqa: BLE001
        return False


def ensure_server(timeout: float = 12.0) -> bool:
    """Avvia `ollama serve` in background se installato e non gia' attivo.
    Non scarica nulla. Ritorna True se il server risponde."""
    if server_running():
        return True
    if not ollama_installed():
        return False
    try:
        subprocess.Popen(["ollama", "serve"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except Exception:                          # noqa: BLE001
        return False
    deadline = time.time() + timeout
    while time.time() < deadline:
        if server_running():
            return True
        time.sleep(0.4)
    return False


def ollama_models() -> list[str]:
    """Modelli locali gia' scaricati (`ollama list`)."""
    if not ollama_installed():
        return []
    try:
        out = subprocess.run(["ollama", "list"], capture_output=True, text=True,
                             timeout=8)
        names = []
        for line in out.stdout.splitlines()[1:]:
            line = line.strip()
            if line:
                names.append(line.split()[0])
        return names
    except Exception:                          # noqa: BLE001
        return []


# ------------------------------------------------------------------ chat
def _http_json(url: str, payload: dict, headers: dict, timeout: int = 120) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _chat_local(messages: list[dict]) -> str:
    cfg = config.load()
    model = cfg["local"].get("model") or config.DEFAULT_LOCAL_MODEL
    if not ollama_installed():
        raise AIError("La IA locale non e' attiva: installa il runtime (ollama) "
                      "dal Centro di Controllo -> Assistente IA.")
    if not ensure_server():
        raise AIError("Impossibile avviare il server ollama locale.")
    if model not in ollama_models():
        raise AIError(f"Il modello '{model}' non e' scaricato. Scaricalo dal "
                      "pannello Assistente IA (nessun download automatico).")
    host, port = _host_port()
    try:
        res = _http_json(f"http://{host}:{port}/api/chat",
                         {"model": model, "messages": messages, "stream": False},
                         {"Content-Type": "application/json"})
    except Exception as e:                     # noqa: BLE001
        raise AIError(f"Errore dal motore locale: {e}")
    return (res.get("message") or {}).get("content", "").strip()


def _chat_cloud(messages: list[dict]) -> str:
    cfg = config.load()
    if not cfg.get("consent_cloud"):
        raise AIError("Backend cloud non autorizzato: il contesto uscirebbe verso "
                      "un servizio esterno. Dai il consenso dal pannello Assistente IA.")
    c = cfg["cloud"]
    endpoint = (c.get("endpoint") or "").rstrip("/")
    if not endpoint or not c.get("model"):
        raise AIError("Cloud non configurato: imposta endpoint e modello nel pannello IA.")
    url = endpoint + ("/chat/completions" if endpoint.endswith("/v1")
                      else "/v1/chat/completions")
    headers = {"Content-Type": "application/json"}
    if c.get("api_key"):
        headers["Authorization"] = "Bearer " + c["api_key"]
    try:
        res = _http_json(url, {"model": c["model"], "messages": messages}, headers)
    except Exception as e:                     # noqa: BLE001
        raise AIError(f"Errore dal backend cloud: {e}")
    try:
        return res["choices"][0]["message"]["content"].strip()
    except Exception:                          # noqa: BLE001
        raise AIError("Risposta cloud non valida.")


def chat(messages: list[dict]) -> str:
    """Invia la conversazione al backend attivo e ritorna il testo di risposta.
    Fail-safe: solleva AIError con messaggio leggibile (mai traceback)."""
    be = config.load().get("backend", "off")
    if be == "off":
        raise AIError("Assistente IA disattivato. Attivalo dal Centro di "
                      "Controllo -> Assistente IA (scegli locale o cloud).")
    if be == "local":
        return _chat_local(messages)
    if be == "cloud":
        return _chat_cloud(messages)
    raise AIError(f"Backend sconosciuto: {be}")
