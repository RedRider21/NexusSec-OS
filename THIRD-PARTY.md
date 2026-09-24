# Componenti di terze parti e relative licenze

NexusSec OS è una **distribuzione**: aggrega software di terzi, ciascuno soggetto
alla **propria** licenza. La licenza del progetto (AGPLv3, vedi [`LICENSE`](LICENSE))
si applica **soltanto al codice originale NexusSec** — pannello e Centro di
Controllo GTK (`nxs_cc`), sistema di profili (`nxs_profiles`), assistente IA
(`nxs_ai`), i18n (`nxs_i18n`), HORUS, le app `nxs_*`, gli script `nxs-*`, i
profili e i dati di catalogo (`profiles.json`, `repo.json`), i temi e gli sfondi
originali.

L'inclusione di componenti di terzi avviene per **mera aggregazione** (programmi
separati, installati o scaricati su richiesta, non modificati né collegati al
codice NexusSec): questa non estende il copyleft NexusSec ai componenti terzi, né
le loro licenze al codice NexusSec. La **licenza commerciale** di NexusSec (vedi
[`COMMERCIAL.md`](COMMERCIAL.md)) copre solo il codice originale NexusSec, **mai**
i componenti elencati qui.

Dentro il sistema, questo documento e le licenze di NexusSec si trovano in
`/usr/share/doc/nexussec/`; le licenze dei singoli pacchetti in
`/usr/share/licenses/`.

## 1. Cosa contiene l'immagine (ISO e microSD)

- **Alpine Linux** (musl, apk, OpenRC, BusyBox, ...) — licenze varie
  (principalmente MIT/BSD/GPL); vedi i singoli pacchetti Alpine.
- **Linux kernel** (`linux-lts`, `linux-rpi` per Raspberry Pi) — GPL-2.0.
- **Firmware** nel modloop (driver WiFi/Bluetooth USB, `sof-firmware` per
  l'audio dei portatili, `wireless-regdb`) — in parte **non liberi ma
  ridistribuibili**, ciascuno secondo la propria licenza (vedi il file `WHENCE`
  e le licenze del progetto *linux-firmware*).
- **Xorg, Openbox, GTK3, PCManFM, dunst, PipeWire, BlueZ, Podman, bubblewrap,
  nftables, cryptsetup, xinput, ...** — licenze rispettive (MIT/BSD/GPL/LGPL).
- **Utilità preinstallate**: **Tor** (BSD-3-Clause), **torsocks** (GPL-2.0),
  **MAT2** (LGPL-3.0).
- **WebKitGTK** (browser) — LGPL/BSD.
- **gcompat** — shim di compatibilità glibc→musl, licenza propria (NCSA/MIT).
- **Font**: *Chakra Petch* (Cadson Demak) e *IBM Plex Mono* (IBM) — **SIL Open
  Font License 1.1** (`/usr/share/fonts/nexussec/LICENSE.txt`).
- **Icone del menu del tasto destro** (`/usr/local/share/nexussec/menu-icons/`)
  — icone simboliche di **adwaita-icon-theme** (GNOME Project), ricolorate da
  `build/make-menu-icons.py`; licenza CC-BY-SA 3.0 / LGPL-3.0.
- **Temi Openbox di terzi**:
  - *NexusSec-Arc-Dark / -Light* — adattati da **Lubuntu Arc-Round**
    (the-zero885), GPL-3.0.
  - *1977* (9 varianti, installati in `~/.themes`) — di **Thayer Williams**; la
    famiglia *NexusSec-Retro-\** ne deriva. Nei file originali **non è indicata
    una licenza**: da verificare con la pagina di pubblicazione dell'autore o con
    l'autore stesso (vedi `build/openbox-templates/retro`).

### Sorgenti dei componenti dell'immagine

I pacchetti Alpine inclusi sono quelli dei repository ufficiali Alpine (ramo
*edge*) alla data della build indicata nel nome dell'immagine; ricette e
sorgenti sono pubblicati da Alpine: <https://gitlab.alpinelinux.org/alpine/aports>
e i mirror dei *distfiles*.

**Offerta scritta.** Per almeno **tre anni** dalla distribuzione di ciascuna
immagine, l'autore di NexusSec OS fornisce a chiunque, su richiesta e al solo
costo del supporto e della spedizione, una copia completa in forma leggibile dal
computer del **codice sorgente corrispondente** dei componenti coperti da GPL o
LGPL inclusi nell'immagine. Richieste a: **deplano.d@gmail.com**, indicando il
nome esatto dell'immagine (es. `alpine-nexussec-260917-x86_64.iso`).

## 2. Pacchetti compilati da NexusSec (repository apk)

Alcuni strumenti non presenti nei repository Alpine sono **compilati da NexusSec
dai sorgenti originali** e pubblicati nel repository apk del progetto
(<https://redrider21.github.io/NexusSec-OS/>). **Non sono nell'immagine**: si
scaricano solo su richiesta. Restano sotto le **licenze originali**:

| Pacchetto | Licenza |
|---|---|
| bulk-extractor | MIT |
| chkrootkit | BSD-2-Clause |
| dirb | GPL-2.0-or-later |
| dmitry | GPL-3.0-or-later |
| foremost | licenza propria (dominio pubblico, U.S. Air Force OSI) |
| medusa | GPL-2.0-or-later |
| rkhunter | GPL-2.0-or-later |
| scalpel | GPL-2.0-or-later |

Ogni pacchetto installa in `/usr/share/licenses/<pacchetto>/` i file di licenza
originali e un `NOTICE` con autori e sorgente. Ricette di compilazione (`APKBUILD`)
e patch sono in [`aports/`](aports/); il **sorgente originale** di ciascuna
versione pubblicata è copiato, verificato col checksum della ricetta, nella
cartella `sources/` accanto al repository apk (`build/collect-sources.sh`).

## 3. Arsenale (strumenti su richiesta)

Gli strumenti del catalogo (`repo.json`) **non fanno parte della
distribuzione**: vengono scaricati sul computer dell'utente solo quando li
richiede, dalle fonti degli autori, e restano soggetti alle **loro licenze**. Al
primo download `nxs-tool` indica la fonte. Fonti possibili:

- **repository Alpine** (`apk`);
- **immagini container ufficiali** dei progetti (Docker Hub, GHCR), scaricate da
  Podman; NexusSec non ospita immagini proprie;
- **container ufficiale Kali Linux** (`kalilinux/kali-rolling`), in cui il
  pacchetto viene installato con `apt` sul computer dell'utente;
- **binari rilasciati dagli autori** (tool Go e Rust, da GitHub Releases) o
  compilati sul computer dell'utente;
- **PyPI** e **repository git** degli autori.

Alcuni strumenti hanno condizioni particolari (per esempio limiti all'uso
commerciale): l'utente è tenuto a verificarle prima dell'uso professionale.

## 4. Assistente IA

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
