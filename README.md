# NexusSecOS-Arsenal

Vetrina, download e **repository pacchetti** di **NexusSec OS** — distro Linux
live x86_64 per la **cybersecurity**, basata su Alpine (musl · apk · OpenRC),
desktop Openbox con pannello e Centro di Controllo nativi in Python (GTK3) e
**profili operativi dinamici** (Pen Testing · Digital Forensics · OSINT · Web).

L'idea: la copertura di strumenti di Kali/Parrot, ma con ISO molto più piccola e
tool **on-demand** (apk · container Podman · pip), ciascuno in **sandbox**.

## Download ISO

L'immagine ISO (~0.5 GB, boot BIOS+EFI) è pubblicata nella sezione
**[Releases](../../releases)** (i file ISO superano il limite del repository git,
quindi sono allegati come *release asset*).

In VirtualBox: VM Linux 64-bit, ≥ 2 GB RAM (3–4 GB se usi i container
Forensics/Web), boot dall'ISO.

## Screenshot

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

I pacchetti compilati per NexusSec OS non presenti nei repo Alpine (es. `dmitry`,
`foremost`, `dirb`, `medusa`, `chkrootkit`, `rkhunter`, `scalpel`,
`bulk-extractor`) sono firmati e serviti via **GitHub Pages**:

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
apk add dirb scalpel foremost
```

Su NexusSec OS questo è **già configurato**: la chiave è in `/etc/apk/keys/` e il
repo è aggiunto all'avvio, quindi `nxs-tool install <tool>` li scarica da qui.

## Catalogo strumenti — da dove arriva ogni programma

Tutti gli strumenti sono **on-demand**: si scaricano dal canale indicato al primo uso (`nxs-tool install <nome>` o le procedure guidate). I repo APT di Kali/Parrot non si usano direttamente (sono `.deb` glibc, incompatibili con Alpine/musl): si consumano via **container**. Totale: 65 strumenti.

**Per canale:** Alpine (apk): 33 · Container (Podman): 11 · Arsenal (NexusSec): 8 · PyPI (pipx): 6 · Kali rolling (container): 4 · Git (pipx): 2 · Git (clone): 1

### Ricognizione

| Programma | Canale | Fonte |
|---|---|---|
| `enum4linux` | Git (pipx) | `git+https://github.com/cddmp/enum4linux-ng.git` |
| `masscan` | Alpine (apk) | repo Alpine main/community/testing · `apk:masscan` |
| `nmap` | Alpine (apk) | repo Alpine main/community/testing · `apk:nmap` |
| `smbmap` | PyPI (pipx) | `pypi:smbmap` |

### OSINT

| Programma | Canale | Fonte |
|---|---|---|
| `amass` | Container (Podman) | `docker.io/caffix/amass:latest` |
| `dmitry` | Arsenal (NexusSec) | GitHub Pages `NexusSecOS-Arsenal` · `apk:dmitry` |
| `dnsenum` | Alpine (apk) | repo Alpine main/community/testing · `apk:dnsenum` |
| `dnsrecon` | Alpine (apk) | repo Alpine main/community/testing · `apk:dnsrecon` |
| `fierce` | PyPI (pipx) | `pypi:fierce` |
| `holehe` | PyPI (pipx) | `pypi:holehe` |
| `metagoofil` | Git (clone) | `https://github.com/opsdisk/metagoofil.git` |
| `recon-ng` | Alpine (apk) | repo Alpine main/community/testing · `apk:recon-ng` |
| `sherlock` | Container (Podman) | `docker.io/sherlock/sherlock:latest` |
| `shodan` | Alpine (apk) | repo Alpine main/community/testing · `apk:py3-shodan` |
| `spiderfoot` | Kali rolling (container) | `kalilinux/kali-rolling` · `apt:spiderfoot` |
| `subfinder` | Container (Podman) | `docker.io/projectdiscovery/subfinder:latest` |
| `sublist3r` | PyPI (pipx) | `pypi:sublist3r` |
| `theharvester` | Container (Podman) | `ghcr.io/laramies/theharvester:latest` |
| `whois` | Alpine (apk) | repo Alpine main/community/testing · `apk:whois` |

### Web

| Programma | Canale | Fonte |
|---|---|---|
| `burpsuite` | Kali rolling (container) | `kalilinux/kali-rolling` · `apt:burpsuite` |
| `commix` | PyPI (pipx) | `pypi:commix` |
| `dalfox` | Container (Podman) | `ghcr.io/hahwul/dalfox:latest` |
| `dirb` | Arsenal (NexusSec) | GitHub Pages `NexusSecOS-Arsenal` · `apk:dirb` |
| `feroxbuster` | Kali rolling (container) | `kalilinux/kali-rolling` · `apt:feroxbuster` |
| `ffuf` | Alpine (apk) | repo Alpine main/community/testing · `apk:ffuf` |
| `gobuster` | Alpine (apk) | repo Alpine main/community/testing · `apk:gobuster` |
| `nikto` | Alpine (apk) | repo Alpine main/community/testing · `apk:nikto` |
| `nuclei` | Alpine (apk) | repo Alpine main/community/testing · `apk:nuclei` |
| `sqlmap` | Alpine (apk) | repo Alpine main/community/testing · `apk:sqlmap` |
| `sslscan` | Alpine (apk) | repo Alpine main/community/testing · `apk:sslscan` |
| `wafw00f` | PyPI (pipx) | `pypi:wafw00f` |
| `wfuzz` | Container (Podman) | `ghcr.io/xmendez/wfuzz:latest` |
| `whatweb` | Container (Podman) | `docker.io/secsi/whatweb:latest` |
| `wpscan` | Container (Podman) | `docker.io/wpscanteam/wpscan:latest` |
| `zaproxy` | Alpine (apk) | repo Alpine main/community/testing · `apk:zaproxy` |

### Exploit

| Programma | Canale | Fonte |
|---|---|---|
| `metasploit` | Container (Podman) | `docker.io/metasploitframework/metasploit-framework:latest` |
| `netexec` | Container (Podman) | `docker.io/parrotsec/netexec:latest` |

### Password

| Programma | Canale | Fonte |
|---|---|---|
| `hashcat` | Alpine (apk) | repo Alpine main/community/testing · `apk:hashcat` |
| `john` | Alpine (apk) | repo Alpine main/community/testing · `apk:john` |

### Brute force

| Programma | Canale | Fonte |
|---|---|---|
| `hydra` | Alpine (apk) | repo Alpine main/community/testing · `apk:hydra` |
| `medusa` | Arsenal (NexusSec) | GitHub Pages `NexusSecOS-Arsenal` · `apk:medusa` |

### Sniffing/MITM

| Programma | Canale | Fonte |
|---|---|---|
| `bettercap` | Alpine (apk) | repo Alpine main/community/testing · `apk:bettercap` |
| `ettercap` | Alpine (apk) | repo Alpine main/community/testing · `apk:ettercap` |
| `responder` | Alpine (apk) | repo Alpine main/community/testing · `apk:responder` |
| `tcpdump` | Alpine (apk) | repo Alpine main/community/testing · `apk:tcpdump` |
| `tshark` | Alpine (apk) | repo Alpine main/community/testing · `apk:tshark` |
| `wireshark` | Alpine (apk) | repo Alpine main/community/testing · `apk:wireshark` |

### Wireless

| Programma | Canale | Fonte |
|---|---|---|
| `aircrack-ng` | Alpine (apk) | repo Alpine main/community/testing · `apk:aircrack-ng` |
| `wifite` | Git (pipx) | `git+https://github.com/derv82/wifite2.git` |

### Forensics

| Programma | Canale | Fonte |
|---|---|---|
| `autopsy` | Kali rolling (container) | `kalilinux/kali-rolling` · `apt:autopsy` |
| `binwalk` | Alpine (apk) | repo Alpine main/community/testing · `apk:binwalk` |
| `bulk-extractor` | Arsenal (NexusSec) | GitHub Pages `NexusSecOS-Arsenal` · `apk:bulk-extractor` |
| `chkrootkit` | Arsenal (NexusSec) | GitHub Pages `NexusSecOS-Arsenal` · `apk:chkrootkit` |
| `clamav` | Alpine (apk) | repo Alpine main/community/testing · `apk:clamav-scanner` |
| `ddrescue` | Alpine (apk) | repo Alpine main/community/testing · `apk:ddrescue` |
| `exiftool` | Alpine (apk) | repo Alpine main/community/testing · `apk:exiftool` |
| `foremost` | Arsenal (NexusSec) | GitHub Pages `NexusSecOS-Arsenal` · `apk:foremost` |
| `rkhunter` | Arsenal (NexusSec) | GitHub Pages `NexusSecOS-Arsenal` · `apk:rkhunter` |
| `scalpel` | Arsenal (NexusSec) | GitHub Pages `NexusSecOS-Arsenal` · `apk:scalpel` |
| `sleuthkit` | Alpine (apk) | repo Alpine main/community/testing · `apk:sleuthkit` |
| `steghide` | Alpine (apk) | repo Alpine main/community/testing · `apk:steghide` |
| `stegseek` | Container (Podman) | `docker.io/rickdejager/stegseek:latest` |
| `testdisk` | Alpine (apk) | repo Alpine main/community/testing · `apk:testdisk` |
| `volatility3` | Alpine (apk) | repo Alpine main/community/testing · `apk:volatility3` |
| `yara` | Alpine (apk) | repo Alpine main/community/testing · `apk:yara` |


## Licenza

I pacchetti mantengono le licenze dei rispettivi progetti upstream. Gli script e
i materiali di NexusSec OS sono rilasciati dal progetto NexusSec.
