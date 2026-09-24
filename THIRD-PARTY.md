# Componenti di terze parti e relative licenze

NexusSec OS è una **distribuzione**: aggrega software di terzi, ciascuno soggetto
alla **propria** licenza. La licenza del progetto (AGPLv3, vedi [`LICENSE`](LICENSE))
si applica **soltanto al codice originale NexusSec** — pannello e Centro di
Controllo GTK (`nxs_cc`), sistema di profili (`nxs_profiles`), assistente IA
(`nxs_ai`), i18n (`nxs_i18n`), HORUS, gli script `nxs-*`, i profili e i dati di
catalogo (`profiles.json`, `repo.json`), i temi e gli sfondi originali.

L'inclusione di componenti di terzi avviene per **mera aggregazione** (installati
o scaricati on-demand, non modificati né linkati staticamente al codice
NexusSec): questa non estende il copyleft NexusSec ai componenti terzi, né le
loro licenze al codice NexusSec.

## Base del sistema

- **Alpine Linux** (musl, apk, OpenRC, BusyBox, ...) — licenze varie
  (principalmente MIT/BSD/GPL); vedi i singoli pacchetti Alpine.
- **Linux kernel** (`linux-lts`), **firmware** — GPL-2.0 e licenze firmware.
- **Xorg, Openbox, GTK3, PCManFM, dunst, PipeWire, BlueZ, Podman, bubblewrap,
  nftables, Tor, cryptsetup, ...** — licenze rispettive (MIT/BSD/GPL/LGPL).
- **WebKitGTK** (browser) — LGPL/BSD.
- **gcompat** — shim di compatibilità glibc→musl, licenza propria (NCSA/MIT).
- **Icone del menu del tasto destro** (`/usr/local/share/nexussec/menu-icons/`)
  — icone simboliche di **adwaita-icon-theme** (GNOME Project), ricolorate da
  `build/make-menu-icons.py`; licenza CC-BY-SA 3.0 / LGPL-3.0.

## Arsenale (tool on-demand)

Gli strumenti del catalogo (`repo.json`) sono di **terze parti**, con le
rispettive licenze, e vengono ottenuti su richiesta:

- pacchetti **Alpine** (`apk`) e **Kali** (container `kali-rolling`): licenze dei
  singoli progetti (in prevalenza GPL/BSD/MIT);
- tool **Go** e **Rust** scaricati come binari release ufficiali: licenza del
  rispettivo progetto upstream;
- tool **pip/git**: licenza del rispettivo progetto.

I pacchetti che NexusSec **compila e distribuisce** dal proprio repo (cartella
`aports/`, `.apk` su GitHub Pages: `dmitry`, `foremost`, `medusa`, `chkrootkit`,
`rkhunter`, `bulk-extractor`, ...) restano sotto le **licenze originali dei
rispettivi progetti** (dichiarate nei singoli `APKBUILD`, campo `license=`); i
sorgenti sono quelli upstream.

## Assistente IA

- **ollama** (runtime locale, opzionale, installato solo su scelta dell'utente) —
  licenza MIT.
- **Modelli linguistici**: ciascun modello scaricato dall'utente ha la **propria
  licenza d'uso** (es. Llama Community License, Apache-2.0, Qwen License, ...).
  NexusSec non distribuisce modelli.
- Backend **cloud**: eventuale servizio scelto dall'utente, con i propri termini.

---

*Elenco non esaustivo: le licenze autorevoli sono quelle incluse nei rispettivi
pacchetti/sorgenti. In caso di ridistribuzione, verifica gli obblighi (avvisi di
copyright, testo di licenza, disponibilità dei sorgenti) di ciascun componente.*
