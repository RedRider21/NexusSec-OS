# Agente AI in NexusSec OS — proposta di design

> Documento di lavoro per decidere con calma. Nessuna implementazione ancora fatta.
> Redatto: 2026-09-03. Vedi roadmap voce 6 in `CLAUDE.md`.

---

## 0. Valutazione dimensioni: quanto pesa un modello sulla ISO?

La ISO oggi è **~0,7 GB**. La domanda è quanto crescerebbe includendo un modello
locale. Contano tre cose diverse: il **runtime**, il **file del modello** e la
**RAM** (la live gira in RAM, quindi il modello caricato in tmpfs "mangia" RAM).

### Modelli recenti utili (settembre 2026) e peso reale Q4_K_M

Q4_K_M è lo standard 2026 per l'on-device: conserva ~95% della qualità a ¼ della
dimensione. GGUF è il formato per **llama.cpp** (il motore di inferenza locale più
diffuso e leggero).

| Modello (recente) | Parametri | File Q4_K_M (≈) | Note |
|-------------------|-----------|-----------------|------|
| Qwen3.5-0.8B | 0,8B | ~0,5–0,7 GB | minimo sindacale, risposte brevi |
| Llama 3.2-1B / Gemma 4 E2B | 1–2B | ~0,8–1,5 GB | leggeri, per Q&A e comandi |
| Qwen3.5-2B | 2B | ~1,3–1,6 GB | buon rapporto qualità/peso |
| **SmolLM3-3B / Qwen3.5-4B** | 3–4B | **~2,0–2,6 GB** | sweet spot assistente serio |
| Phi-4-mini | 3,8B | ~2,5 GB | ottimo su ragionamento |
| Qwen3.5-9B | 9B | ~6,6 GB | qualità alta, richiede molta RAM |
| Gemma 4 12B / Phi-4 14B | 12–14B | ~7,6–9 GB | fuori scala per una live |

### Tre scenari di distribuzione e impatto sulla ISO

| Scenario | Peso sulla ISO | RAM richiesta | Giudizio |
|----------|----------------|---------------|----------|
| **A. Solo runtime nell'ISO, modello on-demand** (scaricato nella persistenza NXSDATA al primo uso) | **+~10 MB** (solo `llama.cpp`) → ISO resta ~0,7 GB | il modello si **mmap** dal file su USB: poca RAM extra | ⭐ **consigliato** |
| **B. Modello piccolo preincluso** (es. Qwen3.5-2B) | +~1,3–1,6 GB → ISO ~2–2,3 GB | ~2–3 GB solo per il modello in tmpfs | ok per una "edizione AI" |
| **C. Modello 3–4B preincluso** (SmolLM3-3B/Qwen3.5-4B) | +~2,0–2,6 GB → ISO ~2,7–3,3 GB | ~4–6 GB RAM | pesante per la live standard |

**Raccomandazione (scenario A).** Mettere nell'ISO **solo il motore** `llama.cpp`
(pochi MB) e trattare il **modello come un tool on-demand**: si scarica al primo
uso e vive nella **persistenza** (`/var/nxs-data`), da cui `llama.cpp` lo **mmap-a**
direttamente dalla chiavetta — così **non gonfia né l'ISO né la RAM**. È
esattamente la stessa filosofia già usata per i tool di sicurezza (niente bloat,
ogni cosa arriva dal canale giusto). Chi vuole l'esperienza "tutto incluso" può
avere una **edizione AI** separata (scenario B/C) con il modello preinstallato.

> Nota di onestà: il default resta comunque il **backend cloud opt-in** (vedi §4).
> Il modello locale è l'opzione per chi lavora offline / air-gapped e ha RAM a
> sufficienza (≥ 6–8 GB per un 3–4B usabile).

---

## 1. Principi guida

- **Human-in-the-loop sempre.** L'agente *propone*, non *esegue*. Ogni comando
  (specie rete/distruttivo) passa da una conferma esplicita. Su una distro cyber
  non è negoziabile.
- **Eredita i vincoli del profilo.** In *Forensics* non tocca i dischi (montaggio
  ro), in *OSINT* resta passivo, ecc. L'agente sta *dentro* il modello dei profili,
  non è un'eccezione.
- **Privacy per default.** Se il contesto esce verso un cloud, l'utente lo sa e lo
  autorizza. Chiavi come per `aisstream`: solo in `~/.config/nxs/`, mai nel
  repo/overlay.
- **Sandbox già pronta.** Gira dentro `nxs-ai-sandbox` (bubblewrap, root ro):
  agente e tool isolati come tutto il resto.
- **Multilingua.** Parla la lingua scelta (i18n già presente: it/en/fr/es/de).

---

## 2. Dove vive (punti di interazione)

| Superficie | Interazione | Esempio |
|-----------|-------------|---------|
| **CLI** `nxs-ai "…"` | conversazionale nel terminale | `nxs-ai "come acquisisco un'immagine E01 di /dev/sdb?"` → spiega + propone comando |
| **Pannello** (menu + scorciatoia) | box rapido stile "spotlight" | tasto → chiedi, ottieni risposta/azione |
| **Dentro HORUS** | assistente d'indagine | riassume un dossier, suggerisce pivot OSINT, bozza del report |
| **Nei Wizard/profili** | guida contestuale | "quale profilo per analizzare questo pcap?" → propone *Web/Pentest* |

---

## 3. Modello di sicurezza (il cuore)

1. **Contesto in sola lettura**: profilo attivo, tool installati, ultimo output —
   utile senza spiare.
2. **Tre livelli di azione**: *rispondi* (libero) → *proponi comando* (mostra, non
   lancia) → *esegui* (solo dopo conferma, in sandbox, nel rispetto del profilo).
3. **Audit trail locale**: registro di cosa ha proposto/eseguito (coerente con una
   distro forense). Zero telemetria.
4. **Fail-safe**: se il backend non risponde/è offline, degrada a Q&A locale, non
   blocca il lavoro.

---

## 4. Backend (astrazione selezionabile, come i motori di HORUS)

| Modalità | Pro | Contro |
|----------|-----|--------|
| **Locale** (`llama.cpp` + modello GGUF Q4_K_M) | offline, privacy totale | pesa su RAM; qualità inferiore ai grandi |
| **Cloud opt-in** (il tuo AIos, o API) | potente, ISO leggera | i dati escono → richiede consenso esplicito |

**Raccomandazione:** **cloud opt-in come default consapevole** (avviso chiaro +
chiave locale) **+ modalità locale attivabile** per chi lavora air-gapped.
Selezione come per la lingua / i motori news di HORUS.

---

## 5. Rilascio incrementale (per non rischiare)

- **Fase 1 — Consulente read-only**: Q&A su tool/comandi `nxs-`, spiega output,
  *propone* comandi senza eseguirli. Basso rischio, valore immediato.
- **Fase 2 — Esecutore confermato**: lancia comandi `nxs-`/tool dopo conferma, in
  sandbox, con i vincoli del profilo.
- **Fase 3 — Integrazione HORUS + automazioni multi-step** (sempre con conferma
  agli snodi critici).

---

## 6. Sintesi

Un agente **che consiglia prima di agire, isolato come tutto il resto, che non fa
uscire i dati senza permesso e che obbedisce al profilo attivo**. Potenzia
l'utente senza diventare esso stesso la falla — il rischio da evitare in una
distro di sicurezza. Punto d'ingresso ideale: **Fase 1** con **scenario A**
(runtime nell'ISO, modello on-demand nella persistenza).

---

### Fonti (dimensioni/modelli, settembre 2026)

- [Best Small Language Models 2026: Top SLMs Ranked (1B-14B) — localaimaster](https://localaimaster.com/blog/small-language-models-guide-2026)
- [Best Small Language Models on Hugging Face Right Now — KDnuggets](https://www.kdnuggets.com/best-small-language-models-on-hugging-face-right-now)
- [Ollama Models Cheat Sheet 2026 — ComputingForGeeks](https://computingforgeeks.com/ollama-models-cheat-sheet/)
- [Best Local LLMs 2026: Qwen, Gemma, gpt-oss — Omid Saffari](https://omidsaffari.com/blog/best-local-llms-2026)
- [Best Mobile LLM 2026: Phi-4 Mini vs Gemma 3 vs SmolLM — promptquorum](https://www.promptquorum.com/power-local-llm/mobile-llm-models-phi4-gemma-smollm)
