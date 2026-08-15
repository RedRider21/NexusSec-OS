# NexusSecOS-Arsenal

Vetrina, download e **repository pacchetti** di **NexusSec OS** — distro Linux
live x86_64 per la **cybersecurity**, basata su Alpine (musl · apk · OpenRC),
desktop Openbox con pannello e Centro di Controllo nativi in Python (GTK3) e
**profili operativi dinamici** (Pen Testing · Digital Forensics · OSINT · Web).

L'idea: la copertura di strumenti di Kali/Parrot, ma con ISO molto più piccola e
tool **on-demand** (apk · container Podman · pip), ciascuno in **sandbox**.

Include un **browser integrato stealth**: di default naviga in modo **anonimo**
(traffico via **Tor**, IP nascosto) e **senza lasciare tracce** locali
(cookie/cronologia/cache solo in RAM), con **interruttore** in barra per passare
al volo alla navigazione normale. Interfaccia a schede con **preferiti** (mostra
la **favicon** reale dei siti, anche nella barra laterale ridotta) e **tema
scuro** coerente con l'ambiente NexusSec.

## Procedure guidate (Wizard)

Oltre ai tool singoli, NexusSec include **procedure guidate**: catene di
strumenti **orchestrate** che trasformano un'operazione complessa in pochi clic.
Non sostituiscono l'esperienza dell'esperto — la **incapsulano** in flussi
ripetibili, versatili e trasparenti. Ogni procedura (Pentest di rete, OSINT su
dominio, Scan web, Forensics) si configura al volo dall'interfaccia:

- **Modalità** (intensità): *Leggero* / *Approfondito* — regola profondità e
  ampiezza (es. porte comuni vs tutte le porte, crawl minimo vs esteso).
- **Opzioni** a spunta: attivi/disattivi singole fasi (rilevamento OS, script
  vulnerabilità NSE, UDP, enumerazione SMB, WAF, ...), con il **conteggio degli
  step** aggiornato in tempo reale.
- **Stealth ON/OFF** (mostrato solo dove ha senso): dove praticabile instrada i
  tool **via Tor** (torsocks/proxychains) per nascondere l'IP, con **esito
  onesto per step** — *via Tor* / *non anonimizzabile (pacchetti raw)* / *gira in
  container* / *locale*. Niente false promesse: se Tor non è disponibile, gli
  step anonimizzabili vengono **saltati** per non esporre l'IP reale.
- **Catena dati**: l'output di un tool diventa l'input del successivo
  (es. *ping sweep → estrai host vivi → scansiona solo quelli*), con salto
  automatico degli step il cui input è vuoto.

Risultati e log finiscono in `~/NexusSec-loot/`. È incluso un **costruttore
grafico** per creare **wizard personalizzati** (scegli i tool dal catalogo,
definisci modalità, opzioni, comportamento stealth per step e la catena dati)
che si aggiungono all'elenco **senza scrivere codice**.

## Documentazione

- **[Manuale utente](docs/manuale.html)** — avvio, profili, menu, metodi dei tool,
  procedure guidate, browser stealth, persistenza e comandi CLI.
- **[Copertura dell'arsenale](docs/copertura-arsenale.html)** — confronto riga per
  riga con `kali-linux-everything` / `parrot-tools-full`.

## Download ISO

L'immagine ISO (~0.5 GB, boot BIOS+EFI) è pubblicata nella sezione
**[Releases](../../releases)** (i file ISO superano il limite del repository git,
quindi sono allegati come *release asset*).

In VirtualBox: VM Linux 64-bit, ≥ 2 GB RAM (3–4 GB se usi i container
Forensics/Web), boot dall'ISO.

## Screenshot

All'avvio una **splashscreen flat** con barra di caricamento accompagna la
preparazione del desktop:

![splash](screenshots/splash.png)

Desktop reali della live (QEMU/KVM). Cambiando profilo cambiano **sfondo,
accent del pannello e tema delle icone** (anche cartelle e browser).

| Base | Pen Testing |
|---|---|
| ![base](screenshots/desktop-base.png) | ![pentest](screenshots/desktop-pentest.png) |

| Digital Forensics | OSINT | Web Pentest |
|---|---|---|
| ![forensics](screenshots/desktop-forensics.png) | ![osint](screenshots/desktop-osint.png) | ![web](screenshots/desktop-web.png) |

Menu start con ricerca, strumenti raggruppati per categoria e stato installato:

| Menu (Base) | Menu (Pen Testing) |
|---|---|
| ![menu-base](screenshots/menu-base.png) | ![menu-pentest](screenshots/menu-pentest.png) |

## Repository pacchetti (apk)

I pacchetti compilati per NexusSec OS non presenti nei repo Alpine (`dmitry`,
`foremost`, `medusa`, `chkrootkit`, `rkhunter`, `bulk-extractor`) sono firmati e
serviti via **GitHub Pages**:

```
https://dplusos21.github.io/NexusSecOS-Arsenal/
```

Per usarlo su un sistema Alpine/NexusSec:

```sh
# 1) fidati della chiave pubblica del repo
wget -O /etc/apk/keys/nexussecos-arsenal.rsa.pub \
  https://dplusos21.github.io/NexusSecOS-Arsenal/nexussecos-arsenal.rsa.pub

# 2) aggiungi il repo
echo "https://dplusos21.github.io/NexusSecOS-Arsenal" >> /etc/apk/repositories

# 3) aggiorna e installa
apk update
apk add foremost medusa bulk-extractor
```

Su NexusSec OS questo è **già configurato**: la chiave è in `/etc/apk/keys/` e il
repo è aggiunto all'avvio, quindi `nxs-tool install <tool>` li scarica da qui.

## Catalogo strumenti e confronto con Kali / Parrot

Catalogo **curato**: **127 strumenti**, uno o piu' per ogni fase operativa, scelti tra i migliori/piu' efficienti ed evitando i doppioni superati (es. un solo fork di *foremost*, *ffuf*/*feroxbuster* al posto dei vecchi dir-buster). Tutti **on-demand** (`nxs-tool install <nome>` o le procedure guidate); fonti verificate vive (0 rotte).

**Copertura:** 127/127 strumenti fanno parte dell'arsenale di **Kali** e **Parrot** — il catalogo e' costruito apposta come sottoinsieme del loro set. La differenza non e' *quali* strumenti, ma **come**: NexusSec li scarica **al bisogno** su una ISO di **~0.5 GB** (Kali ~4 GB, Parrot ~5-6 GB), ciascuno in sandbox.

> **Arsenale esteso (on-demand):** oltre a questo nucleo curato, il catalogo
> completo conta ora **443 strumenti** su 16 categorie (incluse **Crypto/Stego**
> e **Hardware/SDR**). I ~300 tool aggiuntivi sono raggiunti al volo tramite il
> **container Kali condiviso** (`kali-rolling`): compaiono gia' nei menu e, al
> primo avvio, vengono installati ed eseguiti. Rispetto ai metapacchetti
> `kali-linux-everything` / `parrot-tools-full` la copertura sugli strumenti
> reali e' **153/154** — le uniche voci escluse sono librerie Python o CLI di
> base (non programmi da menu). Confronto completo, riga per riga, in fondo a
> questa sezione e nella vista HTML [`docs/copertura-arsenale.html`](docs/copertura-arsenale.html).

Legenda canale: **Alpine apk** = pacchetto nativo Alpine · **Arsenal** = .apk compilato da noi (GitHub Pages) · **Container** / **Kali (container)** = Podman (immagine upstream o `kali-rolling`) · **PyPI** / **Git** = pipx. Kali/Parrot: ✓ = incluso nell'arsenale.

| # | Programma | Funzione | Canale NexusSec | Kali | Parrot |
|---|---|---|---|---|---|
| | **Ricognizione / Scanning** (14) | | | | |
| 1 | `arp-scan` | Discovery host su LAN via ARP | Alpine apk | ✓ | ✓ |
| 2 | `autorecon` | Ricognizione multi-thread automatica (orchestratore) | PyPI | ✓ | ✓ |
| 3 | `enum4linux` | Enumerazione SMB/Windows | Git (pipx) | ✓ | ✓ |
| 4 | `fping` | Ping parallelo di molti host/range | Alpine apk | ✓ | ✓ |
| 5 | `hping3` | Generatore/analizzatore pacchetti TCP/IP | Alpine apk | ✓ | ✓ |
| 6 | `masscan` | Scanner di porte ad altissima velocita' | Alpine apk | ✓ | ✓ |
| 7 | `naabu` | Port scanner veloce (ProjectDiscovery) | Alpine apk | ✓ | ✓ |
| 8 | `nbtscan` | Scanner nomi NetBIOS | Alpine apk | ✓ | ✓ |
| 9 | `netdiscover` | Discovery host ARP attivo/passivo | Alpine apk | ✓ | ✓ |
| 10 | `nmap` | Scanner di rete e porte | Alpine apk | ✓ | ✓ |
| 11 | `onesixtyone` | Brute-force community string SNMP (via Kali rolling) | Kali (container) | ✓ | ✓ |
| 12 | `sipvicious` | Audit di sistemi SIP/VoIP (via Kali rolling) | Kali (container) | ✓ | ✓ |
| 13 | `smbmap` | Enumerazione share SMB | PyPI | ✓ | ✓ |
| 14 | `snmpwalk` | Interrogazione/enumerazione SNMP | Alpine apk | ✓ | ✓ |
| | **OSINT** (12) | | | | |
| 15 | `amass` | Mappatura attack surface / sottodomini | Container | ✓ | ✓ |
| 16 | `dmitry` | Deepmagic info gathering (whois/porte/sub) | Arsenal | ✓ | ✓ |
| 17 | `dnsrecon` | Enumerazione DNS | Alpine apk | ✓ | ✓ |
| 18 | `holehe` | Account associati a una email | PyPI | ✓ | ✓ |
| 19 | `metagoofil` | Estrazione metadati da documenti pubblici (script: clone + venv dedicato) | Git | ✓ | ✓ |
| 20 | `recon-ng` | Framework web recon (OSINT) | Alpine apk | ✓ | ✓ |
| 21 | `sherlock` | Username su social (container) | Container | ✓ | ✓ |
| 22 | `shodan` | CLI Shodan | Alpine apk | ✓ | ✓ |
| 23 | `spiderfoot` | Automazione OSINT (via Kali rolling: l'immagine spiderfoot/spiderfoot non esiste piu') | Kali (container) | ✓ | ✓ |
| 24 | `subfinder` | Scoperta sottodomini passiva | Container | ✓ | ✓ |
| 25 | `theharvester` | Email/sottodomini da fonti pubbliche. Container ufficiale upstream (override entrypoint: l'EP di default e' il server REST) | Container | ✓ | ✓ |
| 26 | `whois` | Interrogazione WHOIS | Alpine apk | ✓ | ✓ |
| | **Web application** (18) | | | | |
| 27 | `burpsuite` | Burp Suite Community (via Kali rolling: nessuna immagine OCI ufficiale) | Kali (container) | ✓ | ✓ |
| 28 | `commix` | Command injection exploiter | PyPI | ✓ | ✓ |
| 29 | `dalfox` | Scanner XSS | Container | ✓ | ✓ |
| 30 | `feroxbuster` | Brute-force contenuti web (Rust, ricorsivo) via Kali rolling: l'immagine ghcr epi052 non esiste piu' | Kali (container) | ✓ | ✓ |
| 31 | `ffuf` | Fuzzer web veloce | Alpine apk | ✓ | ✓ |
| 32 | `gobuster` | Brute force dir/dns/vhost | Alpine apk | ✓ | ✓ |
| 33 | `httrack` | Copia offline di interi siti web | Alpine apk | ✓ | ✓ |
| 34 | `joomscan` | Scanner di vulnerabilita' Joomla (via Kali rolling) | Kali (container) | ✓ | ✓ |
| 35 | `nikto` | Scanner vulnerabilita' web server | Alpine apk | ✓ | ✓ |
| 36 | `nuclei` | Scanner basato su template | Alpine apk | ✓ | ✓ |
| 37 | `sqlmap` | SQL injection automatico | Alpine apk | ✓ | ✓ |
| 38 | `sslscan` | Analisi configurazione SSL/TLS | Alpine apk | ✓ | ✓ |
| 39 | `wafw00f` | Rileva i WAF | PyPI | ✓ | ✓ |
| 40 | `wapiti` | Scanner di vulnerabilita' web black-box (via Kali rolling) | Kali (container) | ✓ | ✓ |
| 41 | `weevely` | Web shell PHP stealth + gestione (via Kali rolling) | Kali (container) | ✓ | ✓ |
| 42 | `whatweb` | Fingerprinting tecnologie web | Container | ✓ | ✓ |
| 43 | `wpscan` | Scanner WordPress (container) | Container | ✓ | ✓ |
| 44 | `zaproxy` | OWASP ZAP - scanner sicurezza web | Alpine apk | ✓ | ✓ |
| | **Exploitation / Post-exploit** (9) | | | | |
| 45 | `beef-xss` | Framework di exploitation del browser (via Kali rolling) | Kali (container) | ✓ | ✓ |
| 46 | `bloodhound-python` | Ingestor Python di BloodHound (raccolta dati Active Directory) | PyPI | ✓ | ✓ |
| 47 | `evil-winrm` | Shell WinRM per Windows (immagine mantenuta da ParrotSec) | Container | ✓ | ✓ |
| 48 | `exploitdb` | Exploit-DB + searchsploit (ricerca exploit offline, via Kali rolling) | Kali (container) | ✓ | ✓ |
| 49 | `impacket` | Script Impacket (secretsdump/psexec/... via Kali rolling) | Kali (container) | ✓ | ✓ |
| 50 | `metasploit` | Framework di exploit (container Rapid7) | Container | ✓ | ✓ |
| 51 | `netexec` | CrackMapExec successore (SMB/LDAP/WinRM). Immagine mantenuta da ParrotSec (entrypoint nxc) | Container | ✓ | ✓ |
| 52 | `routersploit` | Framework di exploit per dispositivi embedded/router (via Kali rolling) | Kali (container) | ✓ | ✓ |
| 53 | `set` | Social-Engineer Toolkit (via Kali rolling) | Kali (container) | ✓ | ✓ |
| | **Password / Hash** (8) | | | | |
| 54 | `cewl` | Wordlist dai contenuti di un sito (via Kali rolling) | Kali (container) | ✓ | ✓ |
| 55 | `crunch` | Generatore di wordlist (via Kali rolling) | Kali (container) | ✓ | ✓ |
| 56 | `fcrackzip` | Crack di ZIP protetti (via Kali rolling) | Kali (container) | ✓ | ✓ |
| 57 | `hashcat` | Cracking hash GPU/CPU | Alpine apk | ✓ | ✓ |
| 58 | `hashid` | Identifica il tipo di hash (via Kali rolling) | Kali (container) | ✓ | ✓ |
| 59 | `john` | John the Ripper: cracking hash | Alpine apk | ✓ | ✓ |
| 60 | `ophcrack` | Crack password Windows con rainbow table (via Kali rolling) | Kali (container) | ✓ | ✓ |
| 61 | `pdfcrack` | Recupero password di PDF | Alpine apk | ✓ | ✓ |
| | **Brute force online** (5) | | | | |
| 62 | `crowbar` | Brute-force per RDP/SSH/OpenVPN (via Kali rolling) | Kali (container) | ✓ | ✓ |
| 63 | `hydra` | Brute force login multi-protocollo | Alpine apk | ✓ | ✓ |
| 64 | `medusa` | Brute-forcer login paralleli | Arsenal | ✓ | ✓ |
| 65 | `ncrack` | Brute-force di autenticazioni di rete (via Kali rolling) | Kali (container) | ✓ | ✓ |
| 66 | `patator` | Brute-forcer modulare multi-servizio (via Kali rolling) | Kali (container) | ✓ | ✓ |
| | **Sniffing / MITM** (13) | | | | |
| 67 | `bettercap` | MITM e attacchi di rete | Alpine apk | ✓ | ✓ |
| 68 | `dnschef` | Proxy DNS per MITM/redirect (via Kali rolling) | Kali (container) | ✓ | ✓ |
| 69 | `driftnet` | Estrae immagini dal traffico di rete (via Kali rolling) | Kali (container) | ✓ | ✓ |
| 70 | `dsniff` | Suite sniffing password/credenziali (via Kali rolling) | Kali (container) | ✓ | ✓ |
| 71 | `ettercap` | Suite MITM | Alpine apk | ✓ | ✓ |
| 72 | `mitmproxy` | Proxy HTTP/HTTPS interattivo (MITM) | Alpine apk | ✓ | ✓ |
| 73 | `netsniff-ng` | Toolkit sniffing/networking zero-copy (via Kali rolling) | Kali (container) | ✓ | ✓ |
| 74 | `ngrep` | grep sul traffico di rete | Alpine apk | ✓ | ✓ |
| 75 | `responder` | LLMNR/NBT-NS/MDNS poisoner | Alpine apk | ✓ | ✓ |
| 76 | `sslsplit` | MITM trasparente su SSL/TLS (via Kali rolling) | Kali (container) | ✓ | ✓ |
| 77 | `tcpdump` | Cattura pacchetti da CLI | Alpine apk | ✓ | ✓ |
| 78 | `tshark` | Wireshark da riga di comando | Alpine apk | ✓ | ✓ |
| 79 | `wireshark` | Analizzatore di protocolli di rete (GUI) | Alpine apk | ✓ | ✓ |
| | **Wireless** (8) | | | | |
| 80 | `aircrack-ng` | Audit Wi-Fi | Alpine apk | ✓ | ✓ |
| 81 | `cowpatty` | Crack di PSK WPA/WPA2 (via Kali rolling) | Kali (container) | ✓ | ✓ |
| 82 | `kismet` | Rilevatore/sniffer di reti wireless | Alpine apk | ✓ | ✓ |
| 83 | `mdk4` | Stress/attacco su reti Wi-Fi 802.11 (via Kali rolling) | Kali (container) | ✓ | ✓ |
| 84 | `pixiewps` | Attacco WPS offline (Pixie Dust) | Alpine apk | ✓ | ✓ |
| 85 | `reaver` | Attacco WPS su router Wi-Fi (via Kali rolling) | Kali (container) | ✓ | ✓ |
| 86 | `wifiphisher` | Attacchi di phishing/rogue-AP su Wi-Fi (via Kali rolling) | Kali (container) | ✓ | ✓ |
| 87 | `wifite` | Automazione attacchi wireless (WEP/WPA/WPS) | Git (pipx) | ✓ | ✓ |
| | **Reverse engineering** (10) | | | | |
| 88 | `apktool` | Reverse/rebuild di APK Android (via Kali rolling) | Kali (container) | ✓ | ✓ |
| 89 | `binutils` | objdump/readelf/nm: analisi binari | Alpine apk | ✓ | ✓ |
| 90 | `flare-floss` | Estrazione stringhe offuscate da malware (FLARE FLOSS) | PyPI | ✓ | ✓ |
| 91 | `gdb` | Debugger GNU | Alpine apk | ✓ | ✓ |
| 92 | `ghidra` | Suite di reverse engineering (NSA) | Alpine apk | ✓ | ✓ |
| 93 | `jadx` | Decompilatore Dalvik/APK -> Java | Alpine apk | ✓ | ✓ |
| 94 | `ltrace` | Traccia chiamate di libreria | Alpine apk | ✓ | ✓ |
| 95 | `pev` | Toolkit di analisi di eseguibili PE | Alpine apk | ✓ | ✓ |
| 96 | `radare2` | Framework di reverse engineering | Alpine apk | ✓ | ✓ |
| 97 | `strace` | Traccia le system call | Alpine apk | ✓ | ✓ |
| | **Digital forensics** (21) | | | | |
| 98 | `autopsy` | Front-end forense (via Kali rolling: l'immagine sleuthkit/autopsy non esiste piu') | Kali (container) | ✓ | ✓ |
| 99 | `binwalk` | Analisi/carving firmware | Alpine apk | ✓ | ✓ |
| 100 | `bulk-extractor` | Estrazione feature (email/URL/cc) da immagini | Arsenal | ✓ | ✓ |
| 101 | `chkrootkit` | Rilevazione rootkit (locale) | Arsenal | ✓ | ✓ |
| 102 | `clamav` | Antivirus | Alpine apk | ✓ | ✓ |
| 103 | `dc3dd` | dd forense patchato (DC3) con log/hash (via Kali rolling) | Kali (container) | ✓ | ✓ |
| 104 | `dcfldd` | dd forense con hashing on-the-fly (via Kali rolling) | Kali (container) | ✓ | ✓ |
| 105 | `ddrescue` | Copia/recupero dati da dischi danneggiati | Alpine apk | ✓ | ✓ |
| 106 | `exiftool` | Lettura/scrittura metadati | Alpine apk | ✓ | ✓ |
| 107 | `extundelete` | Recupero file cancellati da ext3/ext4 | Alpine apk | ✓ | ✓ |
| 108 | `foremost` | File carving per signature | Arsenal | ✓ | ✓ |
| 109 | `ghex` | Editor esadecimale grafico (GTK) | Alpine apk | ✓ | ✓ |
| 110 | `guymager` | Imager forense grafico (via Kali rolling) | Kali (container) | ✓ | ✓ |
| 111 | `hexedit` | Editor esadecimale da terminale | Alpine apk | ✓ | ✓ |
| 112 | `rkhunter` | Rootkit Hunter (scansione integrita') | Arsenal | ✓ | ✓ |
| 113 | `sleuthkit` | The Sleuth Kit: file system forensics | Alpine apk | ✓ | ✓ |
| 114 | `steghide` | Steganografia | Alpine apk | ✓ | ✓ |
| 115 | `stegseek` | Crack steghide ultra-veloce (container: mhash assente in Alpine) | Container | ✓ | ✓ |
| 116 | `testdisk` | Recupero partizioni/file (con photorec) | Alpine apk | ✓ | ✓ |
| 117 | `volatility3` | Analisi memoria RAM (Volatility 3) | Alpine apk | ✓ | ✓ |
| 118 | `yara` | Pattern matching malware | Alpine apk | ✓ | ✓ |
| | **Anonimato** (4) | | | | |
| 119 | `macchanger` | Cambia l'indirizzo MAC dell'interfaccia | Alpine apk | ✓ | ✓ |
| 120 | `proxychains-ng` | Instrada connessioni TCP via proxy/Tor | Alpine apk | ✓ | ✓ |
| 121 | `tor` | Rete di anonimizzazione (onion routing) | Alpine apk | ✓ | ✓ |
| 122 | `torsocks` | Fa passare un'applicazione attraverso Tor | Alpine apk | ✓ | ✓ |
| | **Pivoting / Tunneling** (3) | | | | |
| 123 | `ncat` | Netcat di Nmap (con TLS/proxy) | Alpine apk | ✓ | ✓ |
| 124 | `netcat` | Coltellino svizzero TCP/UDP (bind/reverse shell) | Alpine apk | ✓ | ✓ |
| 125 | `socat` | Relay bidirezionale multiprotocollo (tunnel/pivot) | Alpine apk | ✓ | ✓ |
| | **Analisi vulnerabilita'** (1) | | | | |
| 126 | `lynis` | Audit di hardening/sicurezza del sistema | Alpine apk | ✓ | ✓ |
| | **Reporting** (1) | | | | |
| 127 | `cherrytree` | Note gerarchiche per report/appunti di pentest | Alpine apk | ✓ | ✓ |

> Presenza in Kali cross-verificata sull'indice `Packages` di `kali-rolling` unito alla base Debian *bookworm* (su cui Kali e Parrot 6 sono costruiti) e alla lista ufficiale `kali.org/tools`; Parrot importa l'intero arsenale Kali oltre alla base Debian, quindi la copertura coincide.


### Copertura completa dell'arsenale Kali / Parrot

Confronto riga per riga della tabella metapacchetti `kali-linux-everything` /
`parrot-tools-full` con il catalogo NexusSec (443 tool). Metodo su NexusSec:
`apk` nativo Alpine · `kali` container Kali condiviso · `pip` (pipx) · `ctr`
container Podman · `git` clone+venv.

<details>
<summary><b>Mostra la tabella comparativa completa</b> (154 strumenti)</summary>

| Strumento | Kali | Parrot | NexusSec | Come su NexusSec |
|---|:--:|:--:|:--:|---|
| **Information Gathering** | | | | |
| `0trace` | ✅ | ✅ | ✅ | `kali` |
| `2ping` | ✅ | ✅ | ✅ | `kali` |
| `aadict` | ✅ | ✅ | lib | _libreria/CLI di base_ |
| `aardwolf` | ✅ | ✅ | lib | _libreria/CLI di base_ |
| `aesedb` | ✅ | ✅ | lib | _libreria/CLI di base_ |
| `afflib-tools` | ✅ | ✅ | ✅ | `kali` |
| `afl++` | ✅ | ✅ | ✅ | `kali` |
| `aiocmd` | ✅ | ✅ | lib | _libreria/CLI di base_ |
| `aioconsole` | ✅ | ✅ | lib | _libreria/CLI di base_ |
| `aiohttp-apispec` | ✅ | ✅ | lib | _libreria/CLI di base_ |
| `aiomultiprocess` | ✅ | ✅ | lib | _libreria/CLI di base_ |
| `aiosmb` | ✅ | ✅ | lib | _libreria/CLI di base_ |
| `aiowinreg` | ✅ | ✅ | lib | _libreria/CLI di base_ |
| `aircrack-ng` | ✅ | ✅ | ✅ | `apk` |
| `airgeddon` | ✅ | ✅ | ✅ | `kali` |
| `altdns` | ✅ | ✅ | ✅ | `kali` |
| `amap` | ✅ | ✅ | ✅ | `kali` |
| `amass` | ✅ | ✅ | ✅ | `ctr` |
| `arpwatch` | ✅ | ✅ | ✅ | `kali` |
| `arjun` | ✅ | ✅ | ✅ | `kali` |
| `assetfinder` | ✅ | ✅ | ✅ | `kali` |
| `autorecon` | ✅ | ✅ | ✅ | `pip` |
| `bettercap` | ✅ | ✅ | ✅ | `apk` |
| `bluelog` | ✅ | ✅ | ✅ | `kali` |
| `bluesnarfer` | ✅ | ✅ | ✅ | `kali` |
| `btscanner` | ✅ | ✅ | ✅ | `kali` |
| `blueranger` | ✅ | ✅ | ✅ | `kali` |
| `burpsuite` | ✅ | ✅ | ✅ | `kali` |
| `caido` | ✅ | ✅ | ✅ | `kali` |
| `caido-cli` | ✅ | ✅ | ✅ | `kali` · incluso in caido |
| `crlfuzz` | ✅ | ✅ | ✅ | `kali` |
| `davtest` | ✅ | ✅ | ✅ | `kali` |
| `dirb` | ✅ | ✅ | ✅ | `kali` |
| `dirbuster` | ✅ | ✅ | ✅ | `kali` |
| `dirsearch` | ✅ | ✅ | ✅ | `kali` |
| `dmitry` | ✅ | ✅ | ✅ | `apk` |
| `dnsenum` | ✅ | ✅ | ✅ | `kali` |
| `dnsmap` | ✅ | ✅ | ✅ | `kali` |
| `dnsrecon` | ✅ | ✅ | ✅ | `apk` |
| `dnstracer` | ✅ | ✅ | ✅ | `kali` |
| `dnswalk` | ✅ | ✅ | ✅ | `kali` |
| `emailharvester` | ✅ | ✅ | ✅ | `kali` |
| `email2phonenumber` | ✅ | ✅ | ✅ | `kali` |
| `feroxbuster` | ✅ | ✅ | ✅ | `kali` |
| `ffuf` | ✅ | ✅ | ✅ | `apk` |
| `findomain` | ✅ | ✅ | ✅ | `kali` |
| `gobuster` | ✅ | ✅ | ✅ | `apk` |
| `gospider` | ✅ | ✅ | ✅ | `kali` |
| `heartleech` | ✅ | ✅ | ✅ | `kali` |
| `instaloader` | ✅ | ✅ | ✅ | `kali` |
| `joomscan` | ✅ | ✅ | ✅ | `kali` |
| `kismet` | ✅ | ✅ | ✅ | `apk` |
| `lbd` | ✅ | ✅ | ✅ | `kali` |
| `legion` | ✅ | ✅ | ✅ | `kali` |
| `linkedin2username` | ✅ | ✅ | ✅ | `kali` |
| `massdns` | ✅ | ✅ | ✅ | `kali` |
| `metagoofil` | ✅ | ✅ | ✅ | `git` |
| `nmap` | ✅ | ✅ | ✅ | `apk` |
| `nikto` | ✅ | ✅ | ✅ | `apk` |
| `nuclei` | ✅ | ✅ | ✅ | `apk` |
| `owasp-mantra-ff` | ✅ | ✅ | ✅ | `kali` |
| `parsero` | ✅ | ✅ | ✅ | `kali` |
| `paros` | ✅ | ✅ | ✅ | `kali` |
| `photon` | ✅ | ✅ | ✅ | `kali` |
| `recon-ng` | ✅ | ✅ | ✅ | `apk` |
| `sherlock` | ✅ | ✅ | ✅ | `ctr` |
| `skipfish` | ✅ | ✅ | ✅ | `kali` |
| `sparrow-wifi` | ✅ | ✅ | ✅ | `kali` |
| `spiderfoot` | ✅ | ✅ | ✅ | `kali` |
| `spiderfoot-cli` | ✅ | ✅ | ✅ | `kali` · incluso in spiderfoot |
| `subfinder` | ✅ | ✅ | ✅ | `ctr` |
| `sublist3r` | ✅ | ✅ | ✅ | `kali` |
| `sstimap` | ✅ | ✅ | ✅ | `kali` |
| `subjack` | ✅ | ✅ | ✅ | `kali` |
| `theHarvester` | ✅ | ✅ | ✅ | `ctr` |
| `tinja` | ✅ | ✅ | ✅ | `kali` |
| `tookie-osint` | ✅ | ✅ | ✅ | `kali` |
| `unicornscan` | ✅ | ✅ | ✅ | `kali` |
| `uniscan-gui` | ✅ | ✅ | ✅ | `kali` |
| `urlcrazy` | ✅ | ✅ | ✅ | `kali` |
| `uro` | ✅ | ✅ | ✅ | `kali` |
| `wapiti` | ✅ | ✅ | ✅ | `kali` |
| `wash` | ✅ | ✅ | ✅ | `kali` |
| `watobo` | ✅ | ✅ | ✅ | `kali` |
| `wcvs` | ✅ | ✅ | ✅ | `kali` |
| `webscarab` | ✅ | ✅ | ✅ | `kali` |
| `whatweb` | ✅ | ✅ | ✅ | `ctr` |
| `wfuzz` | ✅ | ✅ | ✅ | `kali` |
| `wpprobe` | ✅ | ✅ | ✅ | `kali` |
| `wpscan` | ✅ | ✅ | ✅ | `ctr` |
| `zenmap` | ✅ | ✅ | ✅ | `kali` |
| `zaproxy` | ✅ | ✅ | ✅ | `apk` |
| **Vulnerability Analysis** | | | | |
| `CAT` | ✅ | ✅ | ✅ | `kali` |
| `gvm-start` | ✅ | ✅ | — |  |
| `openvas` | ✅ | ✅ | ✅ | `kali` · incluso in gvm |
| `sqlmap` | ✅ | ✅ | ✅ | `apk` |
| **Web Application Analysis** | | | | |
| `armitage` | ✅ | ✅ | ✅ | `kali` |
| `beef-xss` | ✅ | ✅ | ✅ | `kali` |
| `burpsuite` | ✅ | ✅ | ✅ | `kali` |
| `commix` | ✅ | ✅ | ✅ | `pip` |
| `crackmapexec` | ✅ | ✅ | ✅ | `kali` |
| `empire` | ✅ | ✅ | ✅ | `kali` |
| `metasploit-framework` | ✅ | ✅ | ✅ | `kali` |
| `msfpc` | ✅ | ✅ | ✅ | `kali` |
| `set` | ✅ | ✅ | ✅ | `kali` |
| `setoolkit` | ✅ | ✅ | ✅ | `kali` |
| **Password Attacks** | | | | |
| `cewl` | ✅ | ✅ | ✅ | `kali` |
| `crunch` | ✅ | ✅ | ✅ | `kali` |
| `hashcat` | ✅ | ✅ | ✅ | `apk` |
| `hydra` | ✅ | ✅ | ✅ | `apk` |
| `john` | ✅ | ✅ | ✅ | `apk` |
| `medusa` | ✅ | ✅ | ✅ | `apk` |
| `ncrack` | ✅ | ✅ | ✅ | `kali` |
| `patator` | ✅ | ✅ | ✅ | `kali` |
| `thc-hydra` | ✅ | ✅ | ✅ | `apk` · incluso in hydra |
| **Wireless Attacks** | | | | |
| `asleap` | ✅ | ✅ | ✅ | `kali` |
| `aircrack-ng` | ✅ | ✅ | ✅ | `apk` |
| `airgeddon` | ✅ | ✅ | ✅ | `kali` |
| `bettercap` | ✅ | ✅ | ✅ | `apk` |
| `bluelog` | ✅ | ✅ | ✅ | `kali` |
| `bluesnarfer` | ✅ | ✅ | ✅ | `kali` |
| `btscanner` | ✅ | ✅ | ✅ | `kali` |
| `blueranger` | ✅ | ✅ | ✅ | `kali` |
| `fang` | ✅ | ✅ | ✅ | `kali` |
| `kismet` | ✅ | ✅ | ✅ | `apk` |
| `sparrow-wifi` | ✅ | ✅ | ✅ | `kali` |
| `spooftooph` | ✅ | ✅ | ✅ | `kali` |
| `ubertooth-util` | ✅ | ✅ | ✅ | `kali` · incluso in ubertooth |
| `wash` | ✅ | ✅ | ✅ | `kali` |
| **Reverse Engineering** | | | | |
| `edb-debugger` | ✅ | ✅ | ✅ | `kali` |
| `ghidra` | ✅ | ✅ | ✅ | `apk` |
| `radare2` | ✅ | ✅ | ✅ | `apk` |
| `retdec` | ✅ | ✅ | ✅ | `kali` |
| `rizin` | ✅ | ✅ | ✅ | `kali` |
| **Exploitation Tools** | | | | |
| `armitage` | ✅ | ✅ | ✅ | `kali` |
| `beef-xss` | ✅ | ✅ | ✅ | `kali` |
| `commix` | ✅ | ✅ | ✅ | `pip` |
| `crackmapexec` | ✅ | ✅ | ✅ | `kali` |
| `empire` | ✅ | ✅ | ✅ | `kali` |
| `evil-winrm` | ✅ | ✅ | ✅ | `ctr` |
| `metasploit-framework` | ✅ | ✅ | ✅ | `kali` |
| `msfpc` | ✅ | ✅ | ✅ | `kali` |
| `set` | ✅ | ✅ | ✅ | `kali` |
| `setoolkit` | ✅ | ✅ | ✅ | `kali` |
| **Sniffing & Spoofing** | | | | |
| `arpspoof` | ✅ | ✅ | ✅ | `kali` |
| `bettercap` | ✅ | ✅ | ✅ | `apk` |
| `dsniff` | ✅ | ✅ | ✅ | `kali` |
| `ettercap` | ✅ | ✅ | ✅ | `apk` |
| `macchanger` | ✅ | ✅ | ✅ | `apk` |
| `msgsnarf` | ✅ | ✅ | ✅ | `kali` |
| `urlsnarf` | ✅ | ✅ | ✅ | `kali` |
| `webspy` | ✅ | ✅ | ✅ | `kali` |
| **Post Exploitation** | | | | |
| `bloodhound` | ✅ | ✅ | ✅ | `kali` |
| `crackmapexec` | ✅ | ✅ | ✅ | `kali` |
| `evil-winrm` | ✅ | ✅ | ✅ | `ctr` |
| `mimikatz` | ✅ | ✅ | ✅ | `kali` |
| `powersploit` | ✅ | ✅ | ✅ | `kali` |
| **Forensics** | | | | |
| `autopsy` | ✅ | ✅ | ✅ | `kali` |
| `bulk_extractor` | ✅ | ✅ | ✅ | `apk` |
| `foremost` | ✅ | ✅ | ✅ | `apk` |
| `rekall` | ✅ | ✅ | ✅ | `kali` |
| `sleuthkit` | ✅ | ✅ | ✅ | `apk` |
| `volatility` | ✅ | ✅ | ✅ | `apk` · incluso in volatility3 |
| **Reporting Tools** | | | | |
| `cherrytree` | ✅ | ✅ | ✅ | `apk` |
| `cutycapt` | ✅ | ✅ | ✅ | `kali` |
| `freemind` | ✅ | ✅ | ✅ | `kali` |
| `recordmydesktop` | ✅ | ✅ | ✅ | `kali` |
| **Hardware Hacking** | | | | |
| `arduino` | ✅ | ✅ | ✅ | `kali` |
| `gtkterm` | ✅ | ✅ | ✅ | `kali` |
| `minicom` | ✅ | ✅ | ✅ | `kali` |
| `rfcat` | ✅ | ✅ | ✅ | `kali` |
| `simtrace` | ✅ | ✅ | ✅ | `kali` |
| **Cryptography & Steganography** | | | | |
| `cryptcat` | ✅ | ✅ | ✅ | `kali` |
| `gpa` | ✅ | ✅ | ✅ | `kali` |
| `openssl` | ✅ | ✅ | lib | _libreria/CLI di base_ |
| `outguess` | ✅ | ✅ | ✅ | `kali` |
| `seahorse` | ✅ | ✅ | ✅ | `kali` |
| `stegcracker` | ✅ | ✅ | ✅ | `kali` |
| `steghide` | ✅ | ✅ | ✅ | `apk` |
| `veracrypt` | ✅ | ✅ | ✅ | `kali` |
| **Social Engineering** | | | | |
| `set` | ✅ | ✅ | ✅ | `kali` |
| `setoolkit` | ✅ | ✅ | ✅ | `kali` |
| **Fuzzing** | | | | |
| `afl++` | ✅ | ✅ | ✅ | `kali` |
| `honggfuzz` | ✅ | ✅ | ✅ | `kali` |
| `libfuzzer` | ✅ | ✅ | lib | _libreria/CLI di base_ |
| **VoIP** | | | | |
| `sipvicious` | ✅ | ✅ | ✅ | `kali` |
| `voiper` | ✅ | ✅ | ✅ | `kali` |
| **RFID / NFC** | | | | |
| `libnfc` | ✅ | ✅ | ✅ | `kali` |
| `rfcat` | ✅ | ✅ | ✅ | `kali` |
| **SDR (Software Defined Radio)** | | | | |
| `gnuradio` | ✅ | ✅ | ✅ | `kali` |
| `gqrx` | ✅ | ✅ | ✅ | `kali` |
| `hackrf` | ✅ | ✅ | ✅ | `kali` |
| **Windows Resources** | | | | |
| `mimikatz` | ✅ | ✅ | ✅ | `kali` |
| `powersploit` | ✅ | ✅ | ✅ | `kali` |

</details>

## Licenza

I pacchetti mantengono le licenze dei rispettivi progetti upstream. Gli script e
i materiali di NexusSec OS sono rilasciati dal progetto NexusSec.
