# NexusSec OS

Distro Linux live x86_64 per la **cybersecurity**, basata su **Alpine Linux**
(musl, `apk`, OpenRC — niente systemd), desktop **Openbox** con **pannello e
Centro di Controllo nativi in Python (GTK3)**, tema **NexusSec-Core** (cyan su
nero).

L'idea centrale: invece dell'approccio monolitico di Kali/Parrot (600+ tool
preinstallati), NexusSec e' **modulare e a profili dinamici**. All'avvio scegli
la **modalita' operativa** — *Pen Testing, Digital Forensics, OSINT, Web
Pentest* — e il sistema adatta **menu** (solo i tool pertinenti) e **sfondo**
(inerente alla modalita'). I tool si ottengono **on-demand** e non sporcano il
sistema base.

Dimensioni: **ISO base ~150-200 MB**; a regime con un profilo attivo
~400-600 MB in RAM (contro i ~4 GB di Kali, ~2.2 GB di Parrot).

## Profili operativi (il cuore)

| Profilo | Colore/sfondo | Esempi di tool |
|---|---|---|
| **Base** | cyan `nebula.png` | solo sistema NexusSec |
| **Pen Testing** | rosso `pentest.png` | nmap, masscan, hydra, john, hashcat, sqlmap, metasploit, netexec, bettercap, aircrack-ng, wifite... |
| **Digital Forensics** | ambra `forensics.png` | sleuthkit, autopsy, volatility3, binwalk, foremost, testdisk, yara, clamav, rkhunter, steghide... |
| **OSINT** | verde `osint.png` | theharvester, recon-ng, spiderfoot, sherlock, amass, subfinder, dnsrecon, whois, holehe, shodan... |
| **Web Pentest** | viola `web.png` | nikto, sqlmap, wpscan, zaproxy, burpsuite, gobuster, ffuf, feroxbuster, nuclei, dalfox... |

Il set di strumenti per categoria e' allineato a Kali/Parrot
(`overlay/usr/local/share/nexussec/profiles.json` + `repo.json`).

### Come funziona

- **Selettore** `nxs-profile` (GTK3): mostrato all'avvio e richiamabile da
  pannello / icona desktop / `Super+P`. Schede con nome, descrizione, colore.
- Scelto un profilo, NexusSec:
  1. installa il **meta-pacchetto apk** del profilo: `apk add --no-cache
     sec-profile-<chiave>` (tira i tool del profilo disponibili in apk);
  2. cambia **sfondo** e **accent** (tinta di pannello/CC) della modalita';
  3. salva lo stato in `/etc/sec_os/state.json` e ripopola il **menu del
     pannello** coi soli tool del profilo.
- Opzione **"Pulisci profilo precedente"** (monomissione): `apk del` del
  meta-pacchetto precedente -> sistema sempre pulito e mono-scopo.

### Aspetto coordinato: temi finestre + prompt

- **Temi finestre coordinati col profilo.** Oltre al default `NexusSec-Core`
  (HUD scuro, fisso) puoi scegliere due famiglie che seguono in automatico il
  **colore del profilo attivo**: **Retro** (flat chiaro, derivato dal tema
  "1977") e **Cards** (stile "scheda" iOS, barra del titolo a tinta piena).
  Selezione da *Centro di Controllo → Aspetto coordinato* o `nxs-theme set
  <core|retro|cards>`. Sono temi Openbox **statici** generati per profilo
  (`make themes`); si puo' anche usare un tema Openbox qualsiasi con `raw:<nome>`
  (inclusi gli originali `1977-*` preinstallati).
- **Prompt del terminale commutabile.** `default` (una riga, accent NexusSec),
  `parrot` (due righe stile Parrot/Kali: `┌──[user@host]─[dir]` / `└──╼`) o
  `plain`. Da *Aspetto coordinato* o `nxs-prompt set <stile>`; vale sui nuovi
  terminali (bash e busybox ash).

### Pacchetti e isolamento dei tool

`nxs-tool` e' un sottile "direttore d'orchestra" che sceglie il metodo giusto
per ogni tool (campo `method` in `repo.json`):

- **`apk`** — pacchetto nativo Alpine (`apk add`). Il caso piu' semplice e
  integrato; **sandbox bubblewrap ATTIVA DI DEFAULT** (filesystem di sistema in
  sola lettura — il core non si tocca; disattivabile solo con `NXS_ISOLATE=0`).
- **`container`** — immagine **Podman** (daemonless, rootless: piu' robusto e
  sicuro di Docker, niente conflitti di dipendenze). Usato per i tool pesanti o
  non in apk: **Metasploit, OWASP ZAP, WPScan, Autopsy, Volatility3, ...**
- **`pip`** — pacchetto Python via `pipx` (netexec, sublist3r, holehe, ...).

```sh
nxs-tool profiles                 # elenca i profili
nxs-tool profile web --clean      # attiva un profilo (apk add meta) [+ pulizia]
nxs-tool list                     # tool del profilo + metodo + stato
nxs-tool install nmap             # apk add / podman pull / pipx install
nxs-tool launch metasploit        # installa-se-serve ed esegue (in terminale)
```

> **Perche' Podman e non Docker?** Niente daemon root sempre attivo, supporto
> rootless, OCI-compatibile, ed e' di prima classe su Alpine. Piu' adatto e
> sicuro per una live di security.

### Dove finiscono i pacchetti scaricati (live in VirtualBox)

La live gira **in RAM** (root su `tmpfs`). Senza persistenza, tutto cio' che
scarichi e' **volatile** (si perde al riavvio):

- pacchetti **apk** -> installati in `/` (RAM); con `--no-cache` non resta
  nemmeno il `.apk` in `/var/cache/apk`;
- immagini **Podman** -> `/var/lib/containers` (root) o
  `~/.local/share/containers` (rootless), in RAM;
- tool **pip** -> `~/.local/` (pipx), in RAM.

E' il comportamento "monomissione/stealth" voluto. In VirtualBox dai alla VM
**>= 2 GB di RAM** (3-4 per Forensics/Web con container).

**Con la chiavetta persistente (`NXSDATA`, `nxs-persist`)** i tool installati al
volo **sopravvivono al riavvio**, senza complicare la live "nuda" (tutto e'
attivo solo se `NXSDATA` e' montato):

- **container / Kali** -> lo storage Podman e' su `NXSDATA`: restano;
- **pip / pipx / git** -> vivono in `~/.local`, reso **persistente** (bind mount):
  tornano **senza reinstallare nulla**;
- **apk** (es. `nmap`) -> vengono **registrati** (`/var/nxs-data/tool-state/apk-tools`)
  e **reinstallati al boot, offline dalla cache**, in background (il desktop non
  aspetta). Gestione: `nxs-tool persisted` / `nxs-tool forget <pkg>`.

Per una persistenza **totale** come un PC normale resta l'installazione su disco
(`nxs-install` -> `setup-disk -m sys`).

## Confronto con Kali / Parrot Security

Stessa **copertura di strumenti** delle due distro di riferimento, ma con un
modello opposto: **niente preinstallato**, tutto **on-demand** col metodo piu'
adatto. Risultato: ISO molto piu' piccola e sistema piu' flessibile.

Il catalogo conta **443 strumenti** distribuiti su 16 categorie (incluse le nuove
**Crypto/Stego** e **Hardware/SDR**). Rispetto ai metapacchetti
`kali-linux-everything` / `parrot-tools-full`, la copertura sugli strumenti reali
e' **153/154**: le uniche voci non incluse sono librerie Python o CLI di base
(`aadict`, `aardwolf`, `aio*`, `libfuzzer`, `openssl`...), non programmi da menu.

Legenda metodo NexusSec: `apk` nativo Alpine · `kali` container Kali condiviso
on-demand · `pip` (pipx) · `ctr` container Podman · `git` clone + venv.
Vista completa navigabile (HTML): [`docs/copertura-arsenale.html`](docs/copertura-arsenale.html).

### Software per categoria (sintesi)

Legenda metodo: `apk` nativo Alpine · `pip` (pipx) · `ctr` container Podman · `kali` container Kali.

| Categoria | Kali | Parrot | NexusSec | Strumenti principali (NexusSec) |
|---|:--:|:--:|:--:|---|
| Information Gathering / OSINT | ✅ | ✅ | ✅ | nmap·masscan `apk`, theHarvester·sublist3r·holehe `pip`, amass·subfinder·recon-ng·spiderfoot·sherlock·assetfinder·findomain `kali`, dnsrecon·dnsenum·dmitry `apk` |
| Web Application | ✅ | ✅ | ✅ | sqlmap·nikto·gobuster·ffuf·nuclei·dirb `apk`, wfuzz·wafw00f·commix `pip`, wpscan·burpsuite·feroxbuster·dirsearch·arjun·caido `kali` |
| Password / Brute force | ✅ | ✅ | ✅ | john·hashcat·hydra·medusa `apk`, ncrack·patator `kali` |
| Wireless | ✅ | ✅ | ✅ | aircrack-ng `apk`, wifite `pip`, airgeddon·wash·sparrow-wifi `kali` |
| Exploitation / Post | ✅ | ✅ | ✅ | metasploit `ctr`, netexec·responder `pip`, empire·crackmapexec·bloodhound·evil-winrm `kali` |
| Sniffing / Spoofing | ✅ | ✅ | ✅ | bettercap·ettercap `apk`, dsniff·arpspoof·urlsnarf `kali` |
| Reverse / Crypto / Stego | ✅ | ✅ | ✅ | radare2·ghidra·retdec·honggfuzz `kali`, steghide `apk`, cryptcat·outguess·stegcracker·veracrypt `kali` |
| Digital Forensics | ✅ | ✅ | ✅ | sleuthkit·binwalk·testdisk·yara·foremost·bulk-extractor `apk`, autopsy·volatility3·rekall `ctr`/`kali` |
| Hardware / SDR | ✅ | ✅ | ✅ | arduino·gtkterm·minicom·simtrace·libnfc `kali` |

> Catalogo completo in `overlay/usr/local/share/nexussec/{profiles,repo}.json`
> (**443 tool**). I tool non presenti nei repo Alpine sono forniti on-demand via
> container Kali condiviso, container Podman, pip, o compilati come piccoli
> pacchetti apk nel repo `nexussec`. Nessuno e' preinstallato: la ISO resta ~0.7 GB.

<details>
<summary><b>Mostra tutti i 443 strumenti del catalogo</b> (per categoria, con metodo e presenza in Kali/Parrot)</summary>

| Categoria / Strumento | Metodo | Kali | Parrot |
|---|---|:--:|:--:|
| **Ricognizione** (30) | | | |
| `0trace` | container Kali | ✅ | ✅ |
| `2ping` | container Kali | ✅ | ✅ |
| `amap` | container Kali | ✅ | ✅ |
| `arp-scan` | apk nativo | ✅ | ✅ |
| `arping` | container Kali | ✅ | ✅ |
| `autorecon` | pip/pipx | ✅ | ✅ |
| `braa` | container Kali | ✅ | ✅ |
| `dnswalk` | container Kali | ✅ | ✅ |
| `enum4linux` | pip/pipx | ✅ | ✅ |
| `firewalk` | container Kali | ✅ | ✅ |
| `fping` | apk nativo | ✅ | ✅ |
| `fragrouter` | container Kali | ✅ | ✅ |
| `hping3` | apk nativo | ✅ | ✅ |
| `ike-scan` | container Kali | ✅ | ✅ |
| `intrace` | container Kali | ✅ | ✅ |
| `irpas` | container Kali | ✅ | ✅ |
| `masscan` | apk nativo | ✅ | ✅ |
| `massdns` | container Kali | ✅ | ✅ |
| `naabu` | apk nativo | ✅ | ✅ |
| `nbtscan` | apk nativo | ✅ | ✅ |
| `netdiscover` | apk nativo | ✅ | ✅ |
| `nmap` | apk nativo | ✅ | ✅ |
| `onesixtyone` | container Kali | ✅ | ✅ |
| `p0f` | container Kali | ✅ | ✅ |
| `sipvicious` | container Kali | ✅ | ✅ |
| `smbmap` | pip/pipx | ✅ | ✅ |
| `snmpwalk` | apk nativo | ✅ | ✅ |
| `thc-ipv6` | container Kali | ✅ | ✅ |
| `unicornscan` | container Kali | ✅ | ✅ |
| `zenmap` | container Kali | ✅ | ✅ |
| **OSINT** (32) | | | |
| `altdns` | container Kali | ✅ | ✅ |
| `amass` | container Podman | ✅ | ✅ |
| `assetfinder` | container Kali | ✅ | ✅ |
| `dmitry` | apk nativo | ✅ | ✅ |
| `dnsenum` | container Kali | ✅ | ✅ |
| `dnsmap` | container Kali | ✅ | ✅ |
| `dnsrecon` | apk nativo | ✅ | ✅ |
| `dnstracer` | container Kali | ✅ | ✅ |
| `email2phonenumber` | container Kali | ✅ | ✅ |
| `emailharvester` | container Kali | ✅ | ✅ |
| `fierce` | container Kali | ✅ | ✅ |
| `findomain` | container Kali | ✅ | ✅ |
| `holehe` | pip/pipx | ✅ | ✅ |
| `instaloader` | container Kali | ✅ | ✅ |
| `linkedin2username` | container Kali | ✅ | ✅ |
| `metagoofil` | git+venv | ✅ | ✅ |
| `netmask` | container Kali | ✅ | ✅ |
| `photon` | container Kali | ✅ | ✅ |
| `recon-ng` | apk nativo | ✅ | ✅ |
| `sherlock` | container Podman | ✅ | ✅ |
| `shodan` | apk nativo | ✅ | ✅ |
| `smtp-user-enum` | container Kali | ✅ | ✅ |
| `snmp-check` | container Kali | ✅ | ✅ |
| `spiderfoot` | container Kali | ✅ | ✅ |
| `subfinder` | container Podman | ✅ | ✅ |
| `sublist3r` | container Kali | ✅ | ✅ |
| `swaks` | container Kali | ✅ | ✅ |
| `theharvester` | container Podman | ✅ | ✅ |
| `tookie-osint` | container Kali | ✅ | ✅ |
| `twofi` | container Kali | ✅ | ✅ |
| `urlcrazy` | container Kali | ✅ | ✅ |
| `whois` | apk nativo | ✅ | ✅ |
| **Web** (69) | | | |
| `apache-users` | container Kali | ✅ | ✅ |
| `arjun` | container Kali | ✅ | ✅ |
| `burpsuite` | container Kali | ✅ | ✅ |
| `cadaver` | container Kali | ✅ | ✅ |
| `caido` | container Kali | ✅ | ✅ |
| `commix` | pip/pipx | ✅ | ✅ |
| `crlfuzz` | container Kali | ✅ | ✅ |
| `cutycapt` | container Kali | ✅ | ✅ |
| `dalfox` | container Podman | ✅ | ✅ |
| `davtest` | container Kali | ✅ | ✅ |
| `dirb` | container Kali | ✅ | ✅ |
| `dirbuster` | container Kali | ✅ | ✅ |
| `dirsearch` | container Kali | ✅ | ✅ |
| `dotdotpwn` | container Kali | ✅ | ✅ |
| `feroxbuster` | container Kali | ✅ | ✅ |
| `ffuf` | apk nativo | ✅ | ✅ |
| `ftester` | container Kali | ✅ | ✅ |
| `gobuster` | apk nativo | ✅ | ✅ |
| `gospider` | container Kali | ✅ | ✅ |
| `hakrawler` | container Kali | ✅ | ✅ |
| `heartleech` | container Kali | ✅ | ✅ |
| `httprint` | container Kali | ✅ | ✅ |
| `httrack` | apk nativo | ✅ | ✅ |
| `jboss-autopwn` | container Kali | ✅ | ✅ |
| `joomscan` | container Kali | ✅ | ✅ |
| `jsql-injection` | container Kali | ✅ | ✅ |
| `lbd` | container Kali | ✅ | ✅ |
| `nikto` | apk nativo | ✅ | ✅ |
| `nuclei` | apk nativo | ✅ | ✅ |
| `oscanner` | container Kali | ✅ | ✅ |
| `owasp-mantra-ff` | container Kali | ✅ | ✅ |
| `padbuster` | container Kali | ✅ | ✅ |
| `paros` | container Kali | ✅ | ✅ |
| `parsero` | container Kali | ✅ | ✅ |
| `proxytunnel` | container Kali | ✅ | ✅ |
| `qsslcaudit` | container Kali | ✅ | ✅ |
| `redsocks` | container Kali | ✅ | ✅ |
| `sidguesser` | container Kali | ✅ | ✅ |
| `siege` | container Kali | ✅ | ✅ |
| `skipfish` | container Kali | ✅ | ✅ |
| `slowhttptest` | container Kali | ✅ | ✅ |
| `sqlmap` | apk nativo | ✅ | ✅ |
| `sqlninja` | container Kali | ✅ | ✅ |
| `sqlsus` | container Kali | ✅ | ✅ |
| `ssldump` | container Kali | ✅ | ✅ |
| `sslscan` | apk nativo | ✅ | ✅ |
| `sslyze` | container Kali | ✅ | ✅ |
| `sstimap` | container Kali | ✅ | ✅ |
| `subjack` | container Kali | ✅ | ✅ |
| `thc-ssl-dos` | container Kali | ✅ | ✅ |
| `tinja` | container Kali | ✅ | ✅ |
| `tlssled` | container Kali | ✅ | ✅ |
| `tnscmd10g` | container Kali | ✅ | ✅ |
| `uniscan` | container Kali | ✅ | ✅ |
| `uniscan-gui` | container Kali | ✅ | ✅ |
| `uro` | container Kali | ✅ | ✅ |
| `wafw00f` | pip/pipx | ✅ | ✅ |
| `wapiti` | container Kali | ✅ | ✅ |
| `watobo` | container Kali | ✅ | ✅ |
| `wcvs` | container Kali | ✅ | ✅ |
| `webscarab` | container Kali | ✅ | ✅ |
| `webshells` | container Kali | ✅ | ✅ |
| `weevely` | container Kali | ✅ | ✅ |
| `wfuzz` | container Kali | ✅ | ✅ |
| `whatweb` | container Podman | ✅ | ✅ |
| `wpprobe` | container Kali | ✅ | ✅ |
| `wpscan` | container Podman | ✅ | ✅ |
| `xsser` | container Kali | ✅ | ✅ |
| `zaproxy` | apk nativo | ✅ | ✅ |
| **Password** (35) | | | |
| `cewl` | container Kali | ✅ | ✅ |
| `chntpw` | container Kali | ✅ | ✅ |
| `cisco-auditing-tool` | container Kali | ✅ | ✅ |
| `cmospwd` | container Kali | ✅ | ✅ |
| `crunch` | container Kali | ✅ | ✅ |
| `fcrackzip` | container Kali | ✅ | ✅ |
| `freerdp3-x11` | container Kali | ✅ | ✅ |
| `gpp-decrypt` | container Kali | ✅ | ✅ |
| `hash-identifier` | container Kali | ✅ | ✅ |
| `hashcat` | apk nativo | ✅ | ✅ |
| `hashid` | container Kali | ✅ | ✅ |
| `hydra-gtk` | container Kali | ✅ | ✅ |
| `john` | apk nativo | ✅ | ✅ |
| `johnny` | container Kali | ✅ | ✅ |
| `maskprocessor` | container Kali | ✅ | ✅ |
| `oclgausscrack` | container Kali | ✅ | ✅ |
| `ophcrack` | container Kali | ✅ | ✅ |
| `pack` | container Kali | ✅ | ✅ |
| `pack2` | container Kali | ✅ | ✅ |
| `passing-the-hash` | container Kali | ✅ | ✅ |
| `pdfcrack` | apk nativo | ✅ | ✅ |
| `pipal` | container Kali | ✅ | ✅ |
| `rainbowcrack` | container Kali | ✅ | ✅ |
| `rarcrack` | container Kali | ✅ | ✅ |
| `rcracki-mt` | container Kali | ✅ | ✅ |
| `rsmangler` | container Kali | ✅ | ✅ |
| `samdump2` | container Kali | ✅ | ✅ |
| `seclists` | container Kali | ✅ | ✅ |
| `sipcrack` | container Kali | ✅ | ✅ |
| `sqldict` | container Kali | ✅ | ✅ |
| `statsprocessor` | container Kali | ✅ | ✅ |
| `sucrack` | container Kali | ✅ | ✅ |
| `thc-pptp-bruter` | container Kali | ✅ | ✅ |
| `truecrack` | container Kali | ✅ | ✅ |
| `wordlists` | container Kali | ✅ | ✅ |
| **Brute force** (5) | | | |
| `crowbar` | container Kali | ✅ | ✅ |
| `hydra` | apk nativo | ✅ | ✅ |
| `medusa` | apk nativo | ✅ | ✅ |
| `ncrack` | container Kali | ✅ | ✅ |
| `patator` | container Kali | ✅ | ✅ |
| **Wireless** (43) | | | |
| `aircrack-ng` | apk nativo | ✅ | ✅ |
| `airgeddon` | container Kali | ✅ | ✅ |
| `asleap` | container Kali | ✅ | ✅ |
| `blue-hydra` | container Kali | ✅ | ✅ |
| `bluelog` | container Kali | ✅ | ✅ |
| `blueranger` | container Kali | ✅ | ✅ |
| `bluesnarfer` | container Kali | ✅ | ✅ |
| `btscanner` | container Kali | ✅ | ✅ |
| `bully` | container Kali | ✅ | ✅ |
| `chirp` | container Kali | ✅ | ✅ |
| `cowpatty` | container Kali | ✅ | ✅ |
| `crackle` | container Kali | ✅ | ✅ |
| `eapmd5pass` | container Kali | ✅ | ✅ |
| `fern-wifi-cracker` | container Kali | ✅ | ✅ |
| `freeradius-wpe` | container Kali | ✅ | ✅ |
| `gnuradio` | container Kali | ✅ | ✅ |
| `gqrx-sdr` | container Kali | ✅ | ✅ |
| `gr-air-modes` | container Kali | ✅ | ✅ |
| `gr-osmosdr` | container Kali | ✅ | ✅ |
| `hackrf` | container Kali | ✅ | ✅ |
| `hostapd-wpe` | container Kali | ✅ | ✅ |
| `inspectrum` | container Kali | ✅ | ✅ |
| `iw` | container Kali | ✅ | ✅ |
| `kalibrate-rtl` | container Kali | ✅ | ✅ |
| `kismet` | apk nativo | ✅ | ✅ |
| `mdk3` | container Kali | ✅ | ✅ |
| `mdk4` | container Kali | ✅ | ✅ |
| `multimon-ng` | container Kali | ✅ | ✅ |
| `pixiewps` | apk nativo | ✅ | ✅ |
| `proxmark3` | container Kali | ✅ | ✅ |
| `reaver` | container Kali | ✅ | ✅ |
| `redfang` | container Kali | ✅ | ✅ |
| `rfcat` | container Kali | ✅ | ✅ |
| `rfdump` | container Kali | ✅ | ✅ |
| `rfkill` | container Kali | ✅ | ✅ |
| `sakis3g` | container Kali | ✅ | ✅ |
| `sparrow-wifi` | container Kali | ✅ | ✅ |
| `spooftooph` | container Kali | ✅ | ✅ |
| `ubertooth` | container Kali | ✅ | ✅ |
| `uhd-host` | container Kali | ✅ | ✅ |
| `wash` | container Kali | ✅ | ✅ |
| `wifiphisher` | container Kali | ✅ | ✅ |
| `wifite` | pip/pipx | ✅ | ✅ |
| **Sniffing/Spoofing** (32) | | | |
| `above` | container Kali | ✅ | ✅ |
| `arpspoof` | container Kali | ✅ | ✅ |
| `arpwatch` | container Kali | ✅ | ✅ |
| `bettercap` | apk nativo | ✅ | ✅ |
| `darkstat` | container Kali | ✅ | ✅ |
| `dnschef` | container Kali | ✅ | ✅ |
| `driftnet` | container Kali | ✅ | ✅ |
| `dsniff` | container Kali | ✅ | ✅ |
| `ettercap` | apk nativo | ✅ | ✅ |
| `ettercap-graphical` | container Kali | ✅ | ✅ |
| `ferret-sidejack` | container Kali | ✅ | ✅ |
| `fiked` | container Kali | ✅ | ✅ |
| `hamster-sidejack` | container Kali | ✅ | ✅ |
| `hexinject` | container Kali | ✅ | ✅ |
| `isr-evilgrade` | container Kali | ✅ | ✅ |
| `mitmproxy` | apk nativo | ✅ | ✅ |
| `msgsnarf` | container Kali | ✅ | ✅ |
| `netsniff-ng` | container Kali | ✅ | ✅ |
| `ngrep` | apk nativo | ✅ | ✅ |
| `rebind` | container Kali | ✅ | ✅ |
| `responder` | apk nativo | ✅ | ✅ |
| `sniffjoke` | container Kali | ✅ | ✅ |
| `sslsniff` | container Kali | ✅ | ✅ |
| `sslsplit` | container Kali | ✅ | ✅ |
| `tcpdump` | apk nativo | ✅ | ✅ |
| `tcpflow` | container Kali | ✅ | ✅ |
| `tcpreplay` | container Kali | ✅ | ✅ |
| `tshark` | apk nativo | ✅ | ✅ |
| `urlsnarf` | container Kali | ✅ | ✅ |
| `webspy` | container Kali | ✅ | ✅ |
| `wifi-honey` | container Kali | ✅ | ✅ |
| `wireshark` | apk nativo | ✅ | ✅ |
| **Analisi vulnerabilita** (29) | | | |
| `afl++` | container Kali | ✅ | ✅ |
| `bed` | container Kali | ✅ | ✅ |
| `cisco-global-exploiter` | container Kali | ✅ | ✅ |
| `cisco-ocs` | container Kali | ✅ | ✅ |
| `cisco-torch` | container Kali | ✅ | ✅ |
| `copy-router-config` | container Kali | ✅ | ✅ |
| `dhcpig` | container Kali | ✅ | ✅ |
| `enumiax` | container Kali | ✅ | ✅ |
| `iaxflood` | container Kali | ✅ | ✅ |
| `inviteflood` | container Kali | ✅ | ✅ |
| `legion` | container Kali | ✅ | ✅ |
| `lynis` | apk nativo | ✅ | ✅ |
| `ohrwurm` | container Kali | ✅ | ✅ |
| `peass` | container Kali | ✅ | ✅ |
| `protos-sip` | container Kali | ✅ | ✅ |
| `rtpbreak` | container Kali | ✅ | ✅ |
| `rtpflood` | container Kali | ✅ | ✅ |
| `rtpinsertsound` | container Kali | ✅ | ✅ |
| `rtpmixsound` | container Kali | ✅ | ✅ |
| `sctpscan` | container Kali | ✅ | ✅ |
| `sfuzz` | container Kali | ✅ | ✅ |
| `siparmyknife` | container Kali | ✅ | ✅ |
| `sipp` | container Kali | ✅ | ✅ |
| `sipsak` | container Kali | ✅ | ✅ |
| `spike` | container Kali | ✅ | ✅ |
| `t50` | container Kali | ✅ | ✅ |
| `unix-privesc-check` | container Kali | ✅ | ✅ |
| `voiphopper` | container Kali | ✅ | ✅ |
| `yersinia` | container Kali | ✅ | ✅ |
| **Exploitation** (21) | | | |
| `armitage` | container Kali | ✅ | ✅ |
| `beef-xss` | container Kali | ✅ | ✅ |
| `bloodhound` | container Kali | ✅ | ✅ |
| `bloodhound-python` | pip/pipx | ✅ | ✅ |
| `crackmapexec` | container Kali | ✅ | ✅ |
| `empire` | container Kali | ✅ | ✅ |
| `evil-winrm` | container Podman | ✅ | ✅ |
| `exploitdb` | container Kali | ✅ | ✅ |
| `impacket` | container Kali | ✅ | ✅ |
| `metasploit` | container Podman | ✅ | ✅ |
| `msfpc` | container Kali | ✅ | ✅ |
| `netexec` | container Podman | ✅ | ✅ |
| `nishang` | container Kali | ✅ | ✅ |
| `powersploit` | container Kali | ✅ | ✅ |
| `pupy` | pip/pipx | ✅ | ✅ |
| `routersploit` | container Kali | ✅ | ✅ |
| `set` | container Kali | ✅ | ✅ |
| `shellnoob` | container Kali | ✅ | ✅ |
| `shellter` | container Kali | ✅ | ✅ |
| `termineter` | container Kali | ✅ | ✅ |
| `veil` | container Kali | ✅ | ✅ |
| **Pivoting/Tunnel** (18) | | | |
| `cymothoa` | container Kali | ✅ | ✅ |
| `dbd` | container Kali | ✅ | ✅ |
| `dns2tcp` | container Kali | ✅ | ✅ |
| `exe2hexbat` | container Kali | ✅ | ✅ |
| `iodine` | container Kali | ✅ | ✅ |
| `laudanum` | container Kali | ✅ | ✅ |
| `mimikatz` | container Kali | ✅ | ✅ |
| `miredo` | container Kali | ✅ | ✅ |
| `ncat` | apk nativo | ✅ | ✅ |
| `netcat` | apk nativo | ✅ | ✅ |
| `proxychains4` | container Kali | ✅ | ✅ |
| `ptunnel` | container Kali | ✅ | ✅ |
| `pwnat` | container Kali | ✅ | ✅ |
| `sbd` | container Kali | ✅ | ✅ |
| `socat` | apk nativo | ✅ | ✅ |
| `sslh` | container Kali | ✅ | ✅ |
| `udptunnel` | container Kali | ✅ | ✅ |
| `webacoo` | container Kali | ✅ | ✅ |
| **Reverse engineering** (17) | | | |
| `apktool` | container Kali | ✅ | ✅ |
| `binutils` | apk nativo | ✅ | ✅ |
| `clang` | container Kali | ✅ | ✅ |
| `dex2jar` | container Kali | ✅ | ✅ |
| `flare-floss` | pip/pipx | ✅ | ✅ |
| `gdb` | apk nativo | ✅ | ✅ |
| `ghidra` | apk nativo | ✅ | ✅ |
| `honggfuzz` | container Kali | ✅ | ✅ |
| `jadx` | apk nativo | ✅ | ✅ |
| `jd-gui` | container Kali | ✅ | ✅ |
| `ltrace` | apk nativo | ✅ | ✅ |
| `pev` | apk nativo | ✅ | ✅ |
| `radare2` | apk nativo | ✅ | ✅ |
| `retdec` | container Kali | ✅ | ✅ |
| `rizin` | container Kali | ✅ | ✅ |
| `strace` | apk nativo | ✅ | ✅ |
| `upx` | container Kali | ✅ | ✅ |
| **Crypto/Stego** (6) | | | |
| `cryptcat` | container Kali | ✅ | ✅ |
| `gpa` | container Kali | ✅ | ✅ |
| `outguess` | container Kali | ✅ | ✅ |
| `seahorse` | container Kali | ✅ | ✅ |
| `stegcracker` | container Kali | ✅ | ✅ |
| `veracrypt` | container Kali | ✅ | ✅ |
| **Hardware/SDR** (5) | | | |
| `arduino` | container Kali | ✅ | ✅ |
| `gtkterm` | container Kali | ✅ | ✅ |
| `libnfc` | container Kali | ✅ | ✅ |
| `minicom` | container Kali | ✅ | ✅ |
| `simtrace` | container Kali | ✅ | ✅ |
| **Forensics** (89) | | | |
| `7zip` | container Kali | ✅ | ✅ |
| `aesfix` | container Kali | ✅ | ✅ |
| `aeskeyfind` | container Kali | ✅ | ✅ |
| `afflib-tools` | container Kali | ✅ | ✅ |
| `autopsy` | container Kali | ✅ | ✅ |
| `binwalk` | apk nativo | ✅ | ✅ |
| `binwalk3` | container Kali | ✅ | ✅ |
| `bulk-extractor` | apk nativo | ✅ | ✅ |
| `bytecode-viewer` | container Kali | ✅ | ✅ |
| `cabextract` | container Kali | ✅ | ✅ |
| `ccrypt` | container Kali | ✅ | ✅ |
| `chkrootkit` | apk nativo | ✅ | ✅ |
| `clamav` | apk nativo | ✅ | ✅ |
| `creddump7` | container Kali | ✅ | ✅ |
| `dc3dd` | container Kali | ✅ | ✅ |
| `dcfldd` | container Kali | ✅ | ✅ |
| `ddrescue` | apk nativo | ✅ | ✅ |
| `dumpzilla` | container Kali | ✅ | ✅ |
| `edb-debugger` | container Kali | ✅ | ✅ |
| `ewf-tools` | container Kali | ✅ | ✅ |
| `exifprobe` | container Kali | ✅ | ✅ |
| `exiftool` | apk nativo | ✅ | ✅ |
| `exiv2` | container Kali | ✅ | ✅ |
| `ext3grep` | container Kali | ✅ | ✅ |
| `ext4magic` | container Kali | ✅ | ✅ |
| `extundelete` | apk nativo | ✅ | ✅ |
| `foremost` | apk nativo | ✅ | ✅ |
| `forensics-colorize` | container Kali | ✅ | ✅ |
| `galleta` | container Kali | ✅ | ✅ |
| `ghex` | apk nativo | ✅ | ✅ |
| `gpart` | container Kali | ✅ | ✅ |
| `gparted` | container Kali | ✅ | ✅ |
| `grokevt` | container Kali | ✅ | ✅ |
| `guymager` | container Kali | ✅ | ✅ |
| `hashdeep` | container Kali | ✅ | ✅ |
| `hexedit` | apk nativo | ✅ | ✅ |
| `inetsim` | container Kali | ✅ | ✅ |
| `javasnoop` | container Kali | ✅ | ✅ |
| `lvm2` | container Kali | ✅ | ✅ |
| `mac-robber` | container Kali | ✅ | ✅ |
| `magicrescue` | container Kali | ✅ | ✅ |
| `mdbtools` | container Kali | ✅ | ✅ |
| `memdump` | container Kali | ✅ | ✅ |
| `metacam` | container Kali | ✅ | ✅ |
| `missidentify` | container Kali | ✅ | ✅ |
| `myrescue` | container Kali | ✅ | ✅ |
| `nasm` | container Kali | ✅ | ✅ |
| `nasty` | container Kali | ✅ | ✅ |
| `ollydbg` | container Kali | ✅ | ✅ |
| `parted` | container Kali | ✅ | ✅ |
| `pasco` | container Kali | ✅ | ✅ |
| `pdf-parser` | container Kali | ✅ | ✅ |
| `pdfid` | container Kali | ✅ | ✅ |
| `polenum` | container Kali | ✅ | ✅ |
| `pst-utils` | container Kali | ✅ | ✅ |
| `readpe` | container Kali | ✅ | ✅ |
| `recoverdm` | container Kali | ✅ | ✅ |
| `recoverjpeg` | container Kali | ✅ | ✅ |
| `reglookup` | container Kali | ✅ | ✅ |
| `regripper` | container Kali | ✅ | ✅ |
| `rekall` | container Kali | ✅ | ✅ |
| `rephrase` | container Kali | ✅ | ✅ |
| `rifiuti` | container Kali | ✅ | ✅ |
| `rifiuti2` | container Kali | ✅ | ✅ |
| `rizin-cutter` | container Kali | ✅ | ✅ |
| `rkhunter` | apk nativo | ✅ | ✅ |
| `rsakeyfind` | container Kali | ✅ | ✅ |
| `safecopy` | container Kali | ✅ | ✅ |
| `scalpel` | container Kali | ✅ | ✅ |
| `scrounge-ntfs` | container Kali | ✅ | ✅ |
| `sleuthkit` | apk nativo | ✅ | ✅ |
| `sqlitebrowser` | container Kali | ✅ | ✅ |
| `ssdeep` | container Kali | ✅ | ✅ |
| `steghide` | apk nativo | ✅ | ✅ |
| `stegosuite` | container Kali | ✅ | ✅ |
| `stegseek` | container Podman | ✅ | ✅ |
| `stegsnow` | container Kali | ✅ | ✅ |
| `tcpick` | container Kali | ✅ | ✅ |
| `testdisk` | apk nativo | ✅ | ✅ |
| `undbx` | container Kali | ✅ | ✅ |
| `unhide` | container Kali | ✅ | ✅ |
| `unrar` | container Kali | ✅ | ✅ |
| `vinetto` | container Kali | ✅ | ✅ |
| `volatility3` | apk nativo | ✅ | ✅ |
| `wce` | container Kali | ✅ | ✅ |
| `winregfs` | container Kali | ✅ | ✅ |
| `xmount` | container Kali | ✅ | ✅ |
| `xplico` | container Kali | ✅ | ✅ |
| `yara` | apk nativo | ✅ | ✅ |
| **Reporting** (7) | | | |
| `cherrytree` | apk nativo | ✅ | ✅ |
| `dradis` | container Kali | ✅ | ✅ |
| `eyewitness` | container Kali | ✅ | ✅ |
| `faraday` | container Kali | ✅ | ✅ |
| `freemind` | container Kali | ✅ | ✅ |
| `maltego` | container Kali | ✅ | ✅ |
| `recordmydesktop` | container Kali | ✅ | ✅ |
| **Anonimato** (4) | | | |
| `macchanger` | apk nativo | ✅ | ✅ |
| `proxychains-ng` | apk nativo | ✅ | ✅ |
| `tor` | apk nativo | ✅ | ✅ |
| `torsocks` | apk nativo | ✅ | ✅ |
| **Altri strumenti** (1) | | | |
| `voiper` | container Kali | ✅ | ✅ |

</details>

### Risorse di sistema (valori indicativi)

| Risorsa | Kali (default) | Parrot Security | **NexusSec** |
|---|---|---|---|
| Dimensione ISO | ~3.8–4 GB | ~2.0–2.2 GB | **~0.7 GB** (Bilanciata) |
| Tool preinstallati | 600+ | 600+ | **0** (on-demand) |
| RAM minima | 2 GB (8 consigliati) | 2 GB | **2 GB** |
| RAM a riposo (live) | ~1 GB | ~0.5 GB | **~0.3–0.4 GB** |
| RAM con profilo attivo | n/d (tutto già presente) | n/d | ~0.4–0.6 GB (fino a 1–3 GB con container) |
| Desktop | Xfce/GNOME/KDE | MATE/KDE | **Openbox + pannello GTK3** (leggerissimo) |
| Init | systemd | systemd | **OpenRC** (no daemon) |
| Base | Debian (glibc) | Debian (glibc) | **Alpine** (musl) |
| Isolamento tool | nessuno (root) | nessuno (root) | **sandbox di default** (bwrap/Podman) |

## Desktop

- **Openbox** + tema finestre *NexusSec-Core*; avvio via `~/.xinitrc` ->
  `openbox-session` (autologin utente `nexus` su tty1 -> `startx`).
- **Pannello inferiore GTK3 nativo** (`nxs-panel`, la barra Python riusata dal
  progetto TinyCore): menu start con i tool del profilo, lista finestre
  (`wmctrl`), orologio/calendario, spostabile alto/basso. La sotto-etichetta
  mostra il profilo attivo, l'accent segue il colore del profilo.
- **Autoprotezione** (applet "scudo", un solo slot sulla barra): interruttori
  **Firewall** e **Tor** (`nxs-tor`, SOCKS 9050), **Screenshot** (intero/area) e
  **Blocco schermo**; l'icona riflette lo stato del firewall.
- **Multilingua** (it / en / fr / es / de): layer i18n condiviso (`nxs_i18n`) con
  selettore nel menu (voce **Lingua**) e CLI `nxs-lang`; l'italiano e' la lingua
  sorgente, con fallback lingua->inglese->italiano.
- **Centro di Controllo** (`nxs-control-center`): info sistema, monitor, rete,
  **gestore pacchetti apk**, temi, sfondo, pannello, autostart, e tile
  **Profilo operativo**.
- **NexusSec Browser** (GTK3 + WebKit2): motore `webkit2gtk` installato
  on-demand via apk.
- Lanciatori sul desktop (pcmanfm) + menu tasto destro Openbox.

## HORUS — Occhio OSINT globale

**HORUS** (`nxs-horus`) è la plancia OSINT/GEOINT di NexusSec: una **mappa
mondiale** con i feed pubblici in tempo reale e un **pannello di ricognizione**
che pilota gli strumenti già installati nel profilo.

### Da dove nasce il nome

Il progetto prende spunto da **OSIRIS**, la nota dashboard OSINT commerciale. Nel
mito egizio **Horus è il figlio di Osiris** (e di Iside): colui che raccoglie
l'eredità del padre, lo veglia e lo protegge. HORUS è, allo stesso modo, il
**discendente di quell'idea** — ma ripensato per NexusSec: **locale, privato,
senza SaaS né token**. Il simbolo è l'**Occhio di Horus** (il *Wedjat*),
nell'antico Egitto l'occhio che *tutto vede*, emblema di protezione e visione:
esattamente il ruolo di una plancia che osserva il mondo intero. Da qui il logo
— l'occhio di Horus stilizzato in cyan neon con, al posto della pupilla, un
**piccolo globo** con i meridiani: *l'occhio che vede il globo*.

### Perché è meglio di una dashboard in cloud

- Gira **in locale**: gli scan partono dal **tuo** IP (o da **Tor**, se attivo),
  non dai server di terzi che vedrebbero cosa cerchi.
- Le sorgenti sono **pubbliche e per lo più keyless**; le poche chiavi
  facoltative (AIS globale, AIS premium) restano **solo sul tuo computer**
  (`~/.config/nxs`), non entrano nella distro e non si condividono.
- **Nessun limite regionale**: i feed coprono **tutto il globo**.

### Feed globali (mondiali, tutti attivabili)

| Feed | Sorgente | Cosa mostra |
|---|---|---|
| Terremoti (24h) | USGS | sismi mondiali delle ultime 24 ore |
| Voli in tempo reale | OpenSky | aerei ADS-B (campione mondiale) |
| Vulcani attivi | Smithsonian GVP | vulcani con eruzione recente (incl. Etna) |
| Incendi mondiali | NASA EONET | incendi attivi (eventi aperti) |
| Cavi sottomarini | TeleGeography | dorsali dati oceaniche |
| Stazione ISS | wheretheiss.at | posizione attuale della ISS |
| **Satelliti** | CelesTrak (TLE) | orbite calcolate **live nel browser** (stazioni, GPS, Galileo, GLONASS, BeiDou, meteo, NOAA, GOES, geostazionari) |
| **Telecamere del traffico** | reti pubbliche ufficiali | webcam stradali **keyless**: TfL Londra (con clip video), Caltrans California, Ontario 511, Digitraffic Finlandia, NZTA Nuova Zelanda |
| **Navi (AIS)** | aisstream.io | traffico marittimo mondiale **in streaming continuo** (con chiave gratuita); senza chiave, Digitraffic (Nord Europa) |

La **mappa nera** (Esri Dark) è quella di default; un selettore in alto a destra
cambia vista in **satellite** (Esri), **strade** (OSM) o **chiara** (Esri).

### Aggiornamento in tempo reale e persistenza

- Ogni layer è tenuto in **aggiornamento continuo**: un interruttore *master*
  accende/spegne il flusso, uno slider fissa la cadenza (5–60 s) dei layer in
  movimento (navi, voli, ISS, satelliti); gli altri si ri-verificano al loro
  ritmo.
- L'ultima risposta di ogni feed è **memorizzata in IndexedDB** e la mappa viene
  disegnata da lì: all'apertura rivedi **subito** l'ultimo stato (anche offline).
- Le **navi** usano un **flusso WebSocket permanente** lato backend, con
  sottoscrizione mondiale, che **accumula** di continuo (lo store si popola nel
  tempo su tutti i continenti). NB: la rete *gratuita* di aisstream vive di
  ricevitori volontari, quindi alcune aree (es. Golfo Persico) restano scoperte:
  per coprirle serve una **chiave AIS satellitare a pagamento**, che ognuno può
  inserire nelle Impostazioni (mai distribuita).
- I **satelliti** sono propagati dai TLE **nel browser** con `satellite.js`
  (nessun WebGL): niente carico sul backend e movimento fluido.
- **Mappa offline**: le tile viste online vengono salvate in **IndexedDB** e
  riproposte senza rete; dalle Impostazioni puoi **precaricare il mondo a basso
  zoom** (poche centinaia di tile) e **svuotare la cache**. Utile su una distro
  spesso offline, senza incorporare immagini nella ISO.

### Altri strumenti

- **GEOINT**: dato un IP o un dominio, HORUS lo geolocalizza sulla mappa
  (ipwho.is) e ne raccoglie porte aperte, CVE e hostname da Shodan InternetDB
  (keyless). La query parte dal tuo IP o da Tor.
- **Ricerca per area**: disegni un riquadro e ottieni voli (OpenSky) e terremoti
  (USGS) di quell'area.
- **Dossier e fascicoli d'indagine**: ogni ricognizione, GEOINT, SOCMINT,
  correlazione o ricerca per area confluisce in un **fascicolo** con metadati
  (titolo, analista, obiettivo), **statistiche** per tipo e provenienza dello
  scan (Tor/IP) per ogni voce. Si salva come **report HTML autonomo** — con
  intestazione, **mini-mappa** dei punti, **tabella coordinate**, **timeline**
  ordinata, sezioni per tipo e il **grafo relazioni** incorporato — più una copia
  **JSON** re-importabile, in `~/NexusSec-loot/horus/`. Il fascicolo è un oggetto
  **persistente e ri-editabile**: dall'elenco "Dossier salvati" (o dal pannello
  **Fascicoli** del Centro Correlazioni) lo **riapri dentro HORUS**, ne rivedi i
  punti sulla mappa, **aggiungi altre informazioni** e **aggiorni lo stesso
  fascicolo**; puoi anche **chiuderlo** (torni alla vista normale) o **eliminarlo**.
  Puoi allegare **schermate** di ciò che vedi (pulsante «+ Schermata») ed
  esportare gli indicatori in **CSV** e **STIX 2.1**, il fascicolo in **PDF** o un
  **bundle ZIP** completo (HTML + JSON + CSV + STIX + schermate).
- **Grafo relazioni** (Centro Correlazioni → *Grafo*): trasforma le voci del
  fascicolo in un **grafo** — nodi = entità (IP, domini, email, username, ASN,
  luoghi) e archi = **legami dedotti** (identificatore condiviso fra voci diverse,
  vicinanza geografica, finestra temporale). Layout *force-directed* e rendering
  SVG **senza dipendenze**; nodi trascinabili, esportabile in SVG.
- **Ticker news** in basso, con un **catalogo di fonti mondiali raggruppate per
  zona** (Italia, Europa, Nord America, America Latina, Russia, Cina, Medio
  Oriente, Asia/Pacifico, Oceania, Africa) selezionabili dal pannello
  Impostazioni, più feed RSS personalizzati, aggregati **in parallelo** e ordinati
  per data. La **ricerca a 360°** interroga anche **GDELT** (database mondiale di
  notizie, keyless) oltre a Google News, per una copertura multi-lingua che i soli
  RSS non raggiungono. Include una **modalità lettura** (estrae e mostra pulito
  l'articolo, anche se il sito vieta l'incorporamento) con **traduzione al volo in
  italiano** (Google keyless, instradata dal proxy/Tor), opzionale e ricordata.
- **Finestre trascinabili**: lettore news, video, Centro Correlazioni e Grafo si
  spostano dall'header e ricordano la posizione.
- **Ricognizione** (dal tuo IP / Tor): esegue **solo strumenti in whitelist** già
  presenti, con l'obiettivo **validato per tipo** e passato come lista di
  argomenti (mai a una shell): `whois`, `dig`, `nmap`, `maigret`, `h8mail`,
  `holehe`, `subfinder`, `theHarvester`. I mancanti si installano on-demand.
- **Telefono**: PhoneInfoga avviato on-demand e mostrato in iframe.

### Come è fatto

- **Python GTK3 + WebKit2** (stesso stack di `nxs-browser`, già nella base:
  nessuna dipendenza nuova). Frontend **Leaflet** vendorizzato nell'overlay —
  2D e non WebGL, perché lo stack grafico della live gira in software rendering.
- Un **backend locale** legato a **`127.0.0.1`** fa da proxy ai feed (aggira la
  CORS e, se Tor è su, instrada le richieste sul suo circuito) e tiene aperto il
  flusso AIS. Il traffico browser↔backend resta su loopback (non serve HTTPS lì);
  i feed esterni sono **sempre HTTPS**.
- Librerie vendorizzate nell'overlay (offline-ready): Leaflet, `satellite.js`,
  PySocks (Tor). Nessuna CDN a runtime.

## Build (richiede Alpine)

La build dell'ISO va fatta **su Alpine** (`abuild` + `mkimage.sh`). Passi
completi in [`build-alpine/README.md`](build-alpine/README.md):

1. `make wallpaper` — genera gli sfondi per profilo (PIL, emblema + monogramma NXS).
2. `make check` — sintassi Python + validazione JSON (CI, ovunque).
3. `abuild -r` nei `aports/*` — compila `nexussec-base` + `sec-profile-*`.
4. `mkimage.sh --profile nexussec` — costruisce `out/nexussec-*.iso` (~150-200 MB),
   iniettando l'apkovl generato da `build-alpine/genapkovl-nexussec.sh`.
5. Test: `qemu-system-x86_64 -m 2048 -cdrom out/nexussec-*.iso -boot d`.

### Immagini, architetture e release

- **ISO x86_64** (PC/laptop Intel/AMD, BIOS + UEFI): l'immagine di riferimento.
- **ISO ARM64 (aarch64)** — **solo-UEFI**. Fa boot dove c'è un firmware **UEFI
  ARM standard**: VM ARM con QEMU/EDK2, **UTM/Parallels su Mac Apple Silicon**,
  e hardware ARM con UEFI conforme (SBSA). **Non** fa boot sugli SBC (Raspberry
  Pi & co.), che usano un boot proprietario e vogliono un'immagine per SD.
  Su Mac Apple Silicon oggi gira **in VM**, non sul bare-metal (un boot nativo
  richiederebbe l'approccio Asahi — voce di roadmap).
- **Immagine microSD per Raspberry Pi 4/5** (`nexussec-rpi-*.img.gz`) — nuovo
  formato per gli SBC ARM: usa il boot Raspberry Pi (kernel `linux-rpi` +
  firmware GPU) con i pacchetti e l'apkovl NexusSec. Si scrive su microSD con
  `dd` / Raspberry Pi Imager / balenaEtcher. Build: `build-alpine/build-sd-rpi.sh`
  (profilo `mkimg.nexussec-rpi.sh`). **Disponibile al download** nella release
  più recente, insieme alle due ISO. ⚠️ Costruita col metodo diskless ufficiale
  Alpine ma **da validare su hardware reale** (nessun RPi in sviluppo): trattala
  come una *beta* finché non arriva conferma sul campo.
- **Policy release**: sulle GitHub Releases si tiene allegata **solo l'immagine
  più recente per ciascun formato** (ISO x86_64, ISO aarch64 e immagine microSD
  RPi), per contenere lo spazio; le **note di ogni versione** restano
  consultabili nello storico delle release anche senza gli allegati.

## Layout repository

```
NexusSec-OS/
├── overlay/                         # payload della live (apkovl)
│   ├── usr/local/bin/nxs-*          # launcher: panel, profile, tool, browser...
│   ├── usr/local/lib/nxs_cc/        # pannello + Centro di Controllo (GTK3)
│   ├── usr/local/lib/nxs_profiles/  # model + isolation(apk/podman/pip) + selector + cli
│   ├── usr/local/share/nexussec/    # profiles.json + repo.json
│   ├── home/nexus/                  # .xinitrc, .config/openbox, .themes, sfondi
│   └── etc/local.d/nexussec.start   # init runtime (OpenRC 'local')
├── aports/                          # APKBUILD: nexussec-base + sec-profile-*
├── build-alpine/                    # genapkovl + profilo mkimage + README build
├── build/make-wallpaper.sh          # sfondi per profilo
├── Makefile                         # wallpaper / check / apkovl / iso / clean
└── docs/ROADMAP.md
```

## Stato

- Base **Alpine** (musl/apk/OpenRC); barra/CC/selettore **Python GTK3**.
- **4 profili** operativi con sfondo + accent + menu dinamici.
- Tool **on-demand** con tre metodi: **apk**, **container Podman** (per
  Metasploit & co.), **pip/pipx**; **sandbox attiva di default** (bubblewrap per
  apk/pip, namespace Podman per i container; eccezione per i tool privilegiati).
- Catalogo allineato per categoria a **Kali/Parrot**.
- Build via `abuild` + `mkimage` (scaffold completo; richiede Alpine).
- **TinyCore rimosso** (deb2tcz, apt-shim, pipeline `.tcz`/isolinux): superato.
- **Agente AI Python** al cuore del sistema: prossimo step.
