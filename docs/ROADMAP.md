# Roadmap NexusSec Desktop

> NOTA (migrazione): la base e' passata da **TinyCore ad Alpine Linux**
> (musl/apk/OpenRC). Le fasi 0-5 qui sotto erano relative al motore TinyCore
> (deb2tcz) e sono **superate**. Stato attuale e build in README.md /
> build-alpine/README.md. Sintesi per la parte Alpine nella "Fase 6" in fondo.


## Fase 0 — Scaffold (✅ in corso)

- Struttura repo, Makefile, script `fetch-base.sh` e `build-iso.sh`
- Overlay rootfs con Openbox + tint2 + autostart
- Shim `apt` -> `deb2tcz`
- Skeleton Python `deb2tcz` (cli, repo, deps, converter, installer)

## Fase 1 — MVP desktop (solo TCZ ufficiali)

Obiettivo: ISO bootabile in QEMU che apre Openbox in <10s da CD.

Acceptance:
- `make iso && make test-qemu` -> desktop visibile
- Click destro mostra menu Openbox
- `xterm` funziona
- `pcmanfm` apre la home

Rischi:
- `bootlocal.sh` → `startx` come `tc` può fallire se Xorg manca dipendenze.
  Plan B: `bootsync.sh` con `cde` flag.

## Fase 2 — `deb2tcz` v0 single-package

Obiettivo: convertire un pacchetto leaf di test (es. `hello`) e installarlo.

Acceptance:
- `deb2tcz update-index` scarica `bookworm/main/binary-amd64/Packages.gz`
- `deb2tcz install hello --dry-run` mostra il piano
- `deb2tcz install hello` produce `hello.tcz`, lo carica con `tce-load`,
  e `/usr/bin/hello` funziona

## Fase 3 — Risoluzione dipendenze + cache

- Grafo Depends ricorsivo (già abbozzato in `deps.py`)
- Cache `~/.cache/deb2tcz/{index,debs,tcz}`
- Mappa alias `DEB_TO_TCZ_ALIAS` ampliata (almeno: gtk, qt5, glib, x11)

Acceptance:
- `deb2tcz install geany` converte solo i .deb non già coperti da TCZ
- Seconda install di geany è no-op (cache hit)

## Fase 4 — Hardening conversioni

- Filtro pacchetti `systemd*`, `snapd`, `*-systemd-helpers`
- Esecuzione selettiva di postinst sicuri:
  `update-mime-database`, `update-desktop-database`, `gtk-update-icon-cache`
- Strip di `/usr/share/{doc,man,info}` per ridurre dimensione
- Rilevazione skew glibc (warning se `Depends: libc6 (>= X)` con X troppo nuovo)

## Fase 5 — Esperienza apt-like

- `apt install/remove/search/show/update/list --installed` completi
- Suggerimenti se un pacchetto ha alias TCZ ufficiale ("usa `tce-load -i gtk3`")
- Output colorato + progress bar conversione
- Logging in `/var/log/deb2tcz.log`

## Fase 6 — Profili operativi di sicurezza (✅ base implementata)

NexusSec come distro cybersecurity modulare: profili dinamici che adattano menu
e sfondo, e isolamento dei tool con bubblewrap (no Docker, troppo pesante per
una live in RAM).

Implementato:
- `nxs_profiles` (model/isolation/selector/cli), `profiles.json` + `repo.json`
  in `/usr/local/share/nexussec/`.
- Selettore grafico `nxs-profile` (4 profili: Pen Testing, Forensics, OSINT,
  Web + Base): imposta profilo e **sfondo inerente**.
- Sfondi per profilo generati da `make-wallpaper.sh` (colore + filigrana).
- Menu del pannello **dinamico**: solo i tool del profilo, click -> terminale
  con `nxs-tool launch <tool>` (installa-se-serve + esegue).
- `nxs-tool`: install/run/launch dei tool; binari `static` eseguiti **isolati
  con bwrap** in `/opt/sec_os/`.

Da rifinire:
- Popolare gli `install.url` dei tool `static` in `repo.json`.
- Accent del **tema GTK** per profilo (ora cambia solo lo sfondo).
- `nxs-profile &` nell'autostart Openbox al primo boot.
- Persistenza dei tool scaricati (`/opt/sec_os`) su installazione a disco.

## Fase 7 — Distribuzione

- ISO firmata, hybrid USB-bootable
- Branding (sfondo desktop, splash isolinux)
- Documentazione utente in `docs/USER.md`
- Build CI (GitHub Actions): lint Python + costruzione ISO + boot smoke test in QEMU

## Note tecniche aperte

- **Persistenza**: Tiny Core ricostruisce `/etc` e `/home` da `mydata.tgz` ad
  ogni boot. Le configurazioni applicative installate via deb2tcz devono
  finire nel `.tcz` (read-only) o essere copiate in `/etc/skel`.
- **Compositor**: `picom` su VM senza GPU dedicata può causare tearing;
  prevedere flag `--no-compositor` nel boot menu.
- **Display manager**: per ora `startx` da bootlocal. Se serve login
  multiutente valutare `slim` (TCZ esiste).
