"""nxs_ai - Agente AI di NexusSec (Fase 1: consulente read-only).

Filosofia (vedi PROPOSTA-AGENTE-AI.md):
- L'agente CONSIGLIA prima di agire: risponde e PROPONE comandi, non li esegue.
- Human-in-the-loop sempre; nessun dato esce senza consenso esplicito (cloud).
- Backend selezionabile (come la lingua): LOCALE (ollama, offline) o CLOUD
  (endpoint compatibile OpenAI, anche il proprio AIos). NIENTE si scarica in
  automatico: il runtime locale (ollama) e il modello si installano SOLO su
  decisione esplicita dell'admin, dal pannello IA del Centro di Controllo.
"""
from . import config, backend, agent  # noqa: F401
