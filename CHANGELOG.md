# NexusSec OS — storico delle release

Note di ogni versione pubblicata, dalla più recente. (Riunite qui il 2026-11-22
dai vecchi `out/RELEASE_NOTES_AAMMGG.md`.)

---

## v2026.11.22

#### Installazione su disco sicura, con installatore grafico
Icona *Installa su disco* → procedura guidata (controllo della chiavetta, scelta del disco, passphrase, riepilogo con conferma, avanzamento). Funziona **senza Internet** e avvia PC con **BIOS** e **UEFI**. Il sistema sta in una partizione in **sola lettura** e torna pulito a ogni avvio; dati, strumenti scaricati, container, loot e reti salvate stanno in una parte **cifrata LUKS** sbloccata all'accensione. Le impronte dei file copiati vengono verificate. Da terminale: `nxs-install-disco --disco /dev/sdX`. Il vecchio installatore di Alpine senza rete si fermava subito.

#### ISO x86_64 fast-boot
Sistema già installato in un unico file compresso invece di ~600 pacchetti da installare a ogni avvio: ISO più piccola (~690 MB) e circa **700 MB di RAM in più** liberi a desktop pronto. Con almeno 4 GB di RAM il sistema compresso viene copiato in RAM all'avvio (`nxs_toram=yes|no` per forzare).

#### Finestre in stile macOS
Predefinito «macOS scuro» (c'è anche il chiaro) nel colore del profilo: semafori a sinistra, titolo centrato, icona del programma a destra (logo NexusSec sulle nostre finestre), bordi e angoli afferrabili per ridimensionare. Angoli arrotondati e ombre solo con una scheda video vera: nelle macchine virtuali il compositor resta spento (con l'OpenGL software rendeva bianche le finestre in VirtualBox e nere HORUS e il browser).

#### Splash di avvio vera
L'immagine NexusSec dall'accensione al desktop al posto del testo che scorre (subito con UEFI; con BIOS e nelle VM appena il driver video è caricato). Senza schermo grafico l'avvio resta testuale come prima; se serve la passphrase o il login la splash si fa da parte. `splash=no` la disattiva.

#### Terminale e barra
Logo del terminale più grande a due toni con versione, profilo, rete, stato dei dati e colori dei profili. Barra in basso come in MATE: tasto destro sul pulsante di una finestra (riduci/ripristina, massimizza, sempre in primo piano, sposta su un altro desktop, chiudi) e solo le finestre del desktop corrente.

#### Altro
- Registro degli incarichi con impronte SHA-256 (`nxs-registro`, *Registro e log*).
- Collaudo automatico esteso all'installazione su disco (BIOS e UEFI), con tempo di avvio e RAM libera, e all'usabilità (programmi principali, strumento dal catalogo, profilo, lingua, finestre web, errori nei log); verifica anche in una VirtualBox vera.
- Logo e materiali grafici in `branding/`.
- Repository ripulito (file di lavoro e prototipi superati).

---

## v2026.11.21

Immagini rigenerate dalla v2026.10.10 aggiornando l'overlay (stesso kernel 6.18.55 e stessi pacchetti).

#### Persistenza sulla stessa chiavetta: funziona
`nxs-persist` propone per prima una piccola partizione `NXSDATA` nello spazio **dopo** la distro: nome predefinito, dimensione a scelta, INVIO per confermare. La distro non viene toccata. Collaudata in VM: creazione, scrittura, riavvio, dati ritrovati e persistenza montata da sola.
Corretti cinque difetti delle versioni precedenti:
- lo spazio libero era calcolato **sopra** la distro (rischio di cancellarla);
- la persistenza risultava "già configurata" senza esserlo;
- le domande non leggevano la tastiera;
- la partizione EFI della chiavetta veniva proposta da formattare;
- le partizioni della chiavetta di avvio non si potevano formattare né montare (ora tramite un loop esatto).

La persistenza **cifrata** ora chiede davvero la passphrase al login.

#### Sistema
- `doas` funzionante: i file di configurazione hanno permessi corretti indipendentemente da dove viene creata l'immagine.
- Gestore dischi:
  - la chiavetta della live e la persistenza non si possono smontare, rimontare o proteggere in scrittura per errore;
  - filesystem ed etichette sono visibili anche da utente;
  - il montaggio non fallisce più su ext4/vfat;
  - l'installatore non propone di formattare partizioni montate o la persistenza.

#### HORUS
- 13 nuovi layer gratuiti e senza chiave: GDACS, eventi NASA, allerte NWS, aurora, radioattività, blackout Internet, ransomware, rete Tor, lanci spaziali, bolidi, aeroporti, attaccanti da honeypot, server di comando di botnet.
- Viste specializzate per più monitor (Cyber, Disastri, Trasporti, Geopolitica) con modalità parete.
- CISA KEV con scheda CVE.
- Il server locale è protetto dalle richieste di altri siti.

#### Altro
- Bluetooth: nome e MAC di ogni dispositivo; quelli senza nome sono nascosti di default.
- `write-usb.sh`: propone la ISO adatta al PC, riconosce schede SD/NVMe e protegge il disco di sistema anche con root cifrata.

Immagini: `alpine-nexussec-261121-x86_64.iso`, `alpine-nexussec-261121-aarch64.iso`, `nexussec-rpi-261121-aarch64.img.gz` (Raspberry: beta, da validare su hardware reale).

---

## v2026.10.10

Release di **correzioni critiche**, dopo le prove su VM VirtualBox.

#### Correzione principale: i tool ora partono (niente crash della sessione)

Sintomo: lanciando un tool del catalogo (es. `enum4linux`) comparivano messaggi
a raffica, la cosa "ciclava" e alla fine si veniva **riportati alla schermata di
login** (la sessione grafica crashava).

Causa a monte: gli **shim** dei tool (uno per ogni voce del catalogo, in coda al
PATH, per poterli lanciare per nome dal terminale) venivano scambiati per il tool
**già installato**. Risultato: il sistema saltava l'installazione ed eseguiva lo
shim, che si richiamava all'infinito (ricorsione) consumando le risorse finché la
sessione X veniva terminata.

Ora un tool non installato risulta correttamente **non installato** (anche il
pallino del menu), e lanciandolo parte la **vera installazione** e poi gira,
senza più crash.

#### Altre correzioni

- **Sandbox bubblewrap affidabile**: il collaudo della sandbox ora usa gli stessi
  identici parametri del lancio reale; se su un kernel la sandbox non è
  utilizzabile, il tool parte comunque **senza sandbox** invece di bloccarsi.
- **User namespace attivati presto all'avvio** (runlevel `boot`, prima del
  desktop): niente più finestra in cui i primi tool lanciati trovavano gli user
  namespace ancora spenti.
- **Installer su disco**: menu a ciclo (non chiude più il terminale) e scelta del
  disco/partizione da **elenco numerato** (niente `/dev/sdX` digitato a mano).
- **Nomi file nel gestore file**: il trattino basso (`_`) non viene più tagliato
  nelle viste a icone/elenco.
- **Diagnostica**: `nxs-diag` mostra ora lo stato di sandbox/user namespace/Podman.

#### Immagini
- **x86_64** — `alpine-nexussec-261010-x86_64.iso` (avvio BIOS + UEFI; PC e VM)
- **aarch64** — `alpine-nexussec-261010-aarch64.iso` (avvio UEFI; VM ARM)
- **Raspberry Pi 4/5** — `nexussec-rpi-261010-aarch64.img.gz` (microSD; scrivi con
  `dd`/Raspberry Pi Imager/balenaEtcher — build da validare su hardware reale)

Verifica: `sha256sum -c SHA256SUMS.txt`

---

## v2026.10.07

Release di **correzioni e robustezza**, costruita dopo le prove su VM VirtualBox.
Raccoglie anche i miglioramenti che erano su master ma non ancora in una ISO.

#### Correzioni importanti

##### I tool già installati ora partono davvero
In VM alcuni tool (es. `enum4linux`) stampavano «sandbox bwrap attiva» seguito da
`bwrap: unshare user ns: No space left on device` e non partivano mai; allo stesso
modo falliva ogni installazione di tool in **container**. Causa a monte: gli
**user namespace** non privilegiati erano disattivati nel kernel della live
(`user.max_user_namespaces=0`) — e sia la sandbox **bubblewrap** sia **Podman
rootless** ne hanno bisogno. Quel messaggio NON riguarda lo spazio su disco: è il
limite dei namespace.

- Ora all'avvio NexusSec abilita gli user namespace (sysctl, con file persistente
  anche per il sistema installato).
- In più, se un kernel non li supporta affatto, il tool viene eseguito **senza
  sandbox** (con avviso) invece di bloccarsi e ripetere all'infinito.

##### Installer su disco più chiaro e a prova di errore
- Il menu di `nxs-install` ora **gira in ciclo**: scegliere «mostra dischi» (o
  qualsiasi voce informativa) non chiude più il terminale di colpo — si torna al
  menu dopo una pausa.
- **Scelta del disco da elenco numerato** (come già faceva la persistenza): per
  «disco intero» e «a fianco» non si digita più `/dev/sdX` a mano (fonte di
  errori), si sceglie un numero. Il supporto di avvio della live è escluso
  automaticamente, con dimensione e modello del disco ben visibili.
- La partizione di **persistenza** (`nxs-persist` senza argomenti) continua a
  proporre i dispositivi a numero, marcando `(consigliato)` le chiavette USB.

#### Già pronti, ora nella ISO

- **Tool dal terminale come dal menu**: digitando il nome di un tool del catalogo
  (anche non ancora installato) parte l'installazione on-demand e poi l'esecuzione,
  esattamente come dalla voce di menu. I comandi non in catalogo restano «not found».
- **Procedure guidate**: al cambio lingua a caldo si aggiorna anche l'intestazione
  interna della finestra; costruttore di procedure personalizzate tradotto (5 lingue).
- **Editor nxs-editor**: grafica rifinita e colori/menu leggibili che seguono il profilo.

#### Immagini
- **x86_64** — `alpine-nexussec-261007-x86_64.iso` (avvio BIOS + UEFI)

Verifica: `sha256sum -c SHA256SUMS.txt`

---

## v2026.09.26

#### Novità principali

##### Browser con le funzioni di Firefox
NexusSec Browser resta anonimo di default (Tor, nessuna traccia locale) e ora ha
anche le funzioni di un browser completo:

- **Traduci pagina**, come in Chrome: il pulsante dopo *Stealth* si illumina
  quando la pagina è in un'altra lingua; la traduzione avviene sul posto,
  mantenendo l'impaginazione, e *Mostra originale* la ripristina. Servizio Google
  (predefinito) o LibreTranslate, anche su un server proprio. In modalità anonima
  anche la richiesta di traduzione passa via Tor.
- **Download** con pulsante e percentuale nella barra; pannello con avanzamento,
  velocità, tempo residuo, *Annulla*, *Apri*, *Mostra nella cartella*.
- **Lucchetto**: stato della connessione, certificato (intestatario, emittente,
  validità, problemi) e **permessi per sito** (microfono e fotocamera, notifiche,
  posizione: *Chiedi / Consenti / Blocca*, con «Ricorda la scelta»).
- **Solo HTTPS**: i link `http://` si provano in `https://`, con una pagina di
  avviso se il sito non lo supporta. Indirizzi IP e reti locali sono esclusi, per
  il lavoro in laboratorio.
- **Antitracciamento**: blocca i tracker di analisi, pubblicità e social caricati
  da altri siti (elenco curato da NexusSec). Popup automatici bloccati.
- **Cronologia** (solo navigazione normale) con suggerimenti nella barra
  indirizzi, insieme ai preferiti.
- Trova nella pagina, stampa / salva come PDF (preselezionata «Stampa su file»),
  salva pagina, sorgente, riapri scheda chiusa, silenzia scheda, riordino delle
  schede trascinandole, ripristino della sessione (opzionale).
- **Scorciatoie di Firefox**: Ctrl+T/W, Ctrl+Maiusc+T, Ctrl+Tab, Ctrl+L, Ctrl+F,
  Ctrl+H, Ctrl+J, Ctrl+P, Ctrl+S, Ctrl+U, Alt+frecce, zoom…
- **Impostazioni**: pagina iniziale, motore di ricerca, cartella download, tema,
  modalità anonima, solo HTTPS, antitracciamento, cronologia, servizio di
  traduzione, cancella dati.
- Tor viene ricontrollato in sottofondo: se all'apertura non è ancora pronto, il
  browser ricollega le schede anonime appena Tor risponde (prima restava
  «Stealth (no Tor)» fino alla riapertura).

##### Desktop
- **Menu del tasto destro**: spazio tra una voce e l'altra e icone della giusta
  misura; l'icona di *Benvenuto e licenze* non è più nera.
- **Traduzioni di sistema**: il menu contestuale delle pagine, i dialoghi GTK
  (file, stampa) e le app del desktop ora sono nella lingua scelta. Si tengono
  solo le 5 lingue di NexusSec, per non occupare memoria.

##### Editor di testo e codice nativo (nxs-editor)
Al posto di pluma ora c'è un **editor tutto nostro** (GtkSourceView 4), portato
da Vesper: evidenziazione della sintassi con scelta del linguaggio, schede,
numeri di riga, minimappa, cerca/sostituisci/sostituisci tutto, vai a riga,
duplica/sposta/commenta riga, stampa, rilevamento delle modifiche esterne, scelta
font e zoom, scorciatoie. Colori e sintassi seguono l'accent del profilo attivo.

##### Procedure guidate tradotte (5 lingue)
Titoli, descrizioni, campi, modalità, opzioni e passi delle procedure guidate
ora sono in it/en/fr/es/de; anche l'interfaccia del modulo è tradotta.

##### Browser — permessi per sito e traduzione a blocchi
- **Permessi per sito** dal lucchetto (microfono/fotocamera, notifiche, posizione:
  Chiedi/Consenti/Blocca, con "Ricorda la scelta"); in modalità anonima tutto negato.
- La **traduzione delle pagine** ora lavora a blocchi (una risposta per testo):
  niente più errori su pagine grandi come Wikipedia.
- Stampa preselezionata su **"Stampa su file"** (PDF nella cartella download).


#### Immagini
- **x86_64** — `alpine-nexussec-260926-x86_64.iso` (avvio BIOS + UEFI)
- **aarch64** — `alpine-nexussec-260926-aarch64.iso` (avvio UEFI; VM ARM)
- **Raspberry Pi 4/5** — `nexussec-rpi-260926-aarch64.img.gz` (microSD; build da
  validare su hardware reale)

Verifica: `sha256sum -c SHA256SUMS.txt`

---

## v2026.09.24

#### Novità principali

##### Login grafico in stile Linux Mint
Uscendo dalla sessione non si finisce più sulla console testuale (dove serviva
digitare `exit`): compare la **schermata di accesso grafica**, ridisegnata sul
modello di Linux Mint:
- barra sottile in alto con nome macchina, lingua della tastiera, rete,
  batteria, data/ora e menu **Riavvia / Spegni**;
- lo **sfondo del profilo attivo** e i suoi colori;
- un riquadro compatto con il nome utente, la password (mostra/nascondi, avviso
  **Bloc Maiusc**) e la freccia per entrare; cambio utente e *Altro utente…*.

Il login compare **prima** del desktop, come con un vero display manager: la
sessione si costruisce solo dopo la password. Al rientro non si ripetono splash,
benvenuto e selettore del profilo.
Credenziali della live: `nexus` / `nexus`.

##### Finestra di benvenuto e licenze
Al primo accesso si apre la **finestra di benvenuto** (stile Mint), sopra il
selettore di profilo: *Primi passi*, *Licenze*, *Uso responsabile*,
*Informazioni*. Chiarisce che NexusSec è AGPL-3.0 e che gli **strumenti
dell'arsenale non sono inclusi** nell'immagine: si scaricano al momento dalle
fonti dei loro autori, alle loro licenze (al primo download `nxs-tool` ne indica
fonte e licenza). Si disattiva con *Mostra all'avvio* e si richiama dal menu.

- I testi delle licenze sono ora **dentro la ISO** (`/usr/share/doc/nexussec/`).
- I pacchetti compilati da NexusSec (bulk-extractor, chkrootkit, dirb, dmitry,
  foremost, medusa, rkhunter, scalpel) contengono le **licenze dei loro autori**
  e i **sorgenti corrispondenti** sono pubblicati su Pages, in
  <https://redrider21.github.io/NexusSec-OS/sources/>.
- `THIRD-PARTY.md` riscritto: contenuto reale dell'immagine, sorgenti e offerta
  scritta, pacchetti compilati, fonti dell'arsenale.

##### Desktop
- **Rotazione dello schermo** (normale, sinistra, destra, capovolto) dal Centro
  di Controllo → Schermi → *Orientamento* o con `nxs-screens rotate`; touch e
  penna seguono la rotazione.
- **Visualizzatore di immagini** integrato (`nxs-viewer`): doppio clic su
  un'immagine; zoom, rotazione, scorrimento nella cartella, imposta come sfondo.
- **Menu del tasto destro** rinnovato: icone, intestazione, font del tema,
  margini e traduzione nella lingua attiva; colori e icone seguono il
  **profilo** anche col tema finestre di base.
- **Terminale**: il prompt compare subito; le cornici del prompt (anche in stile
  Kali/Parrot) e il nome utente prendono il **colore del profilo** attivo.
- I popup del pannello compaiono già al loro posto (niente lampeggio).
- Browser: avviso a fine download; il pulsante del manuale apre direttamente la
  pagina giusta.

##### Localizzazione
Completata in 5 lingue (it / en / fr / es / de) anche per: login, fine sessione,
benvenuto, menu del tasto destro, popup del pannello, lettori audio/video,
registratore, visualizzatore, salvaschermo, blocco schermo, appunti, pulizia
metadati, screenshot, spotlight IA. La data della barra segue la lingua attiva.

##### Correzioni
- **Bluetooth**: i dispositivi che non trasmettono un nome (molti dispositivi
  LE nei dintorni) non compaiono più come MAC nudo ma come "Produttore · senza
  nome (…ultime cifre)" e vanno in fondo all'elenco, dopo connessi, associati e
  dispositivi con nome.
- **Gestione Bluetooth**: testo dei pulsanti leggibile (prima "Connetti" era
  chiaro su fondo acceso), pulsanti e nomi centrati nella riga, stati tradotti.
- Su **hardware reale** (per esempio da chiavetta) non compare più l'avviso sui
  servizi di VirtualBox: partono solo dentro una VM VirtualBox.
- La finestra di benvenuto segue il cambio lingua anche quando è già aperta; il
  testo dei pulsanti premuti resta leggibile.

#### Immagini
- **x86_64** — `alpine-nexussec-260924-x86_64.iso` (avvio BIOS + UEFI)
- **aarch64** — `alpine-nexussec-260924-aarch64.iso` (avvio UEFI; VM ARM)
- **Raspberry Pi 4/5** — `nexussec-rpi-260924-aarch64.img.gz` (microSD; build da
  validare su hardware reale)

Verifica: `sha256sum -c SHA256SUMS.txt`

---

## v2026.09.17

#### Novità principali

##### Localizzazione completa dell'interfaccia (it / en / fr / es / de)
Tutto il sistema operativo è ora tradotto nelle 5 lingue, con cambio **al volo**
dal pannello (applet 🌐), dal menu (voce **Lingua**) o dal Centro di Controllo:
- **Centro di Controllo** e tutte le sue viste (sistema, rete, pacchetti,
  aspetto, temi, firewall, utenti, sicurezza, privacy, schermi, IA, ecc.)
- **Pannello**: menu, tooltip (rete, batteria, Bluetooth), stati, categorie tool
- **App**: Browser, Dischi, Casi forensi, Selettore del Profilo operativo
- **Icone del desktop** e scorciatoie

##### Correzione del cambio lingua a runtime
Risolto il caso in cui alcune finestre restavano nella lingua d'avvio: il
servizio di avvio "caldo" (launcher) viene ora riavviato al cambio lingua e
rilegge la lingua attiva ad ogni apertura; anche pcmanfm si riavvia così le
icone del desktop seguono subito la nuova lingua.

> Nota forensic: nell'app *Casi forensi* la catena di custodia e la relazione
> restano in italiano di proposito — sono l'artefatto con valore probatorio e
> vanno tenuti in una lingua stabile e riproducibile.

#### Immagini
- **x86_64** — `alpine-nexussec-260917-x86_64.iso` (avvio BIOS + UEFI)
- **aarch64** — `alpine-nexussec-260917-aarch64.iso` (avvio UEFI; VM ARM)
- **Raspberry Pi 4/5** — `nexussec-rpi-260917-aarch64.img.gz` (microSD; build da
  validare su hardware reale)

Verifica: `sha256sum -c SHA256SUMS.txt`

---

## v2026.09.10

Versione dedicata a **affidabilità degli strumenti on-demand**, **audio/microfono**
e rifiniture del desktop, oltre a un nuovo **registratore vocale**. Include tutto
il lavoro delle versioni precedenti (avvio rapido delle app, zram, temi/skin,
HORUS, sito bilingue).

Immagini **x86_64 + aarch64 + microSD Raspberry Pi** allineate, datate `…260910…`.

#### Novità principali
- **Installazioni on-demand più solide.** Nuovo meccanismo `apk_deps`: i tool
  `pip`/`git`/`apk` possono dichiarare le dipendenze runtime (binari host) che
  vengono installate in automatico. Risolto `enum4linux` (mancavano
  `smbclient`/`rpcclient`/`nmblookup`/`net` → `samba-client` + `samba-common-tools`);
  aggiunte le companion per `wifite` e `autorecon`.
- **Audit completo del catalogo (447 tool).** Ogni strumento verificato nel suo
  canale reale (apk edge, kali-rolling, immagini container, pip/git). Correzioni:
  `ghidra` e `mitm6` → metodo `kali` (non installabili altrimenti), `pupy` rimosso
  (abbandonato, incompatibile con Python 3.12+). C2 leggero coperto da `villain`.
- **Ricerca del menu.** Dal profilo **base** la ricerca copre l'**intero catalogo**
  (trovi e installi qualunque programma); durante la ricerca il menu mostra solo i
  risultati (lista piatta) e li ripristina a campo svuotato.
- **Microfono.** Applet **on-demand** nella barra (compare solo quando il mic è in
  uso; rotella = volume, clic = livello/muta/ingresso) e controllo source in
  `nxs-audio`. Nel **browser** in modalità normale è possibile consentire
  microfono/fotocamera (getUserMedia). *Nota: WebKitGTK non espone WebRTC
  peer-to-peer → per videochiamate (Meet/Jitsi) usare Chromium (`apk add chromium`).*
- **Registratore vocale** `nxs-recorder` (nuovo): visualizzazione a scelta
  **Spettro** (analizzatore di frequenze, FFT) o **Onda** (ampiezza), animata anche
  in **riascolto**; salvataggio WAV in `~/NexusSec-loot/registrazioni`.
- **HORUS.** Stato backend **auto-correttivo** (niente più "backend non
  raggiungibile" spurio) e **dossier DEMO** ora incluso nell'immagine.
- **Browser.** Tab più bassi/compatti (grafica invariata).
- **Sito/manuale** bilingue IT/EN con tema chiaro/scuro (GitHub Pages).

#### Immagini
- **x86_64** (`alpine-nexussec-260910-x86_64.iso`): PC Intel/AMD, boot **BIOS + UEFI**.
- **aarch64** (`alpine-nexussec-260910-aarch64.iso`): ARM64 **solo UEFI** (QEMU/EDK2,
  UTM/Parallels su Mac Apple Silicon, hardware ARM con UEFI conforme).
- **Raspberry Pi 4/5** (`nexussec-rpi-260910-aarch64.img.gz`): immagine per
  **microSD** — scrivere con `dd`, Raspberry Pi Imager o balenaEtcher. *Beta da
  validare su hardware reale.*

#### SHA256
```
3e1eecef35b9efb9e705e420b892bf68343be81c94c79ac0731520d94aa479e1  alpine-nexussec-260910-x86_64.iso
7cdd30dfc40a2a54a1982c29f28e004e27ce6ddc52e306ccb35349b1db2d1f05  alpine-nexussec-260910-aarch64.iso
75fad1c7008605450a32c9d9665cc5638e86fa7c9abfeeaa3e2c457d70b27167  nexussec-rpi-260910-aarch64.img.gz
```
