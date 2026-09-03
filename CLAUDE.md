# NexusSec OS — istruzioni per Claude

Distro Linux live x86_64 per la **cybersecurity**, basata su **Alpine Linux**
(musl, `apk`, OpenRC). Desktop **Openbox** con **pannello e Centro di Controllo
nativi in Python (GTK3)** — la barra Python e' riusata dal precedente progetto
TinyCore. Specializzazione a **profili dinamici** (Pen Testing, Forensics,
OSINT, Web): ogni profilo e' un **meta-pacchetto apk** `sec-profile-*`; i tool
pesanti girano in **container Podman**; sandbox leggera con **bubblewrap**.

> Storia: il progetto nasce come clone TinyCore; e' stato **migrato ad Alpine**.
> Tutto cio' che era TinyCore (`deb2tcz`, shim `apt`, `.tcz`, isolinux, utente
> `tc`) e' stato rimosso. Non reintrodurlo.

L'obiettivo finale resta incapsulare un **agente AI Python** al cuore del
sistema (non ancora presente). Tutto deve restare **minimale, estetico, a basso
consumo**.

## Lingua e stile

- Contenuti user-visible (README, menu, log, messaggi) in **italiano** con
  accenti corretti. Commenti nei sorgenti in italiano informale.
- **i18n** (`nxs_i18n`): l'italiano e' la lingua SORGENTE (chiavi in
  `strings/it.json`); traduzioni in en/fr/es/de. Le stringhe UI nuove vanno
  aggiunte come chiave `it` + traduzioni e usate via `t("chiave")` (fallback
  lingua->en->it->chiave: non rompe mai la UI). Lingua attiva in
  `~/.config/nxs/lang`, cambiabile da menu (voce Lingua) o `nxs-lang set`.
- UI **flat**, niente emoji nei file salvo richiesta. Palette: `#050a14`
  (sfondo), `#0a1a26` (pannello), `#00e5ff` (accent), `#c8f5ff` (testo),
  `#5a8a9a` (tenue), `#1a3a52` (bordi), `#ff5a8a` (allarme). L'accent puo'
  cambiare col profilo (vedi sotto).

## Architettura

```
NexusSec-OS/
├── overlay/                         # payload iniettato nella live (apkovl)
│   ├── usr/local/bin/nxs-*          # launcher shell (panel, profile, tool, browser, ...)
│   ├── usr/local/lib/nxs_cc/        # pannello (panel.py) + Centro di Controllo (GTK3)
│   ├── usr/local/lib/nxs_i18n/      # i18n condiviso (t(), strings/{it,en,fr,es,de}.json)
│   ├── usr/local/lib/nxs_profiles/  # model, isolation, selector, cli
│   ├── usr/local/share/nexussec/    # profiles.json + repo.json
│   ├── home/nexus/                  # .xinitrc, .config/openbox/{rc,autostart,menu}, .themes, sfondi
│   └── etc/local.d/nexussec.start   # init runtime (servizio OpenRC 'local')
├── aports/                          # APKBUILD: nexussec-base + sec-profile-{pentest,forensics,osint,web}
├── build-alpine/                    # genapkovl-nexussec.sh + mkimg.nexussec.sh + README build
├── build/make-wallpaper.sh          # sfondi per profilo (ImageMagick)
└── Makefile                         # wallpaper / check / apkovl / iso / clean
```

## Sistema profili (nxs_profiles) — il cuore

Pacchetto Python **senza dipendenze GTK in model/isolation/cli** (importabili da
CLI e pannello); solo `selector.py` usa GTK.

- **model.py** — carica `profiles.json`/`repo.json` da
  `/usr/local/share/nexussec/`; profilo attivo in `/etc/sec_os/state.json`
  (fallback `~/.config/nxs/profile`). `activate_profile(key, clean_previous)`:
  `apk add --no-cache sec-profile-<key>` (+ opzionale `apk del` del precedente),
  poi applica **sfondo** (feh) e **accent** (scrive `~/.config/nxs/accent.css`,
  caricato da `nxs_cc.common.apply_css`). `apply_current()` riapplica sfondo+accent
  all'avvio senza reinstallare. Percorsi override via env (`NXS_PREFIX`,
  `NXS_STATE`, `NXS_CONF_DIR`, `NXS_BG_DIR`) per test su host.
- **isolation.py** — per ogni tool sceglie il `method` (repo.json):
  - `apk` : `apk add` (+ sandbox bwrap se `NXS_ISOLATE=1`);
  - `container` : **Podman** (`podman pull` / `podman run --rm -it -v ~/NexusSec-loot:/loot [--net host] [--entrypoint X]`); per Metasploit, ZAP, WPScan, Volatility3, ...;
  - `pip` : `pipx install` (fallback `pip --user --break-system-packages`);
  - `git` : `git clone` + venv dedicato + launcher in `~/.local/bin` (tool che NON
    sono pacchetti PyPI, es. metagoofil; campi `git`,`entry`,`bin`);
  - `kali` : esegue dentro `kalilinux/kali-rolling` (`apt install` + `podman commit
    localhost/nxs-kali-<tool>`); canale Debian mantenuto per i tool Kali non
    disponibili come apk su musl (campo opz. `apt`). NB: i repo APT Parrot/Kali
    NON si usano direttamente (.deb glibc incompatibili con musl) ma via container.
  `install/run/launch/uninstall/is_installed`. `launch` = installa-se-serve +
  esegue in foreground (per girare in terminale). **Verifica fonti**:
  `python3 build/nxs-sources-check.py` controlla che ogni link sia vivo e genera
  `build/SOURCES.txt` (esce !=0 se rotto: usabile in CI periodica).
- **selector.py** — GTK3, riusa il CSS di `nxs_cc.common`. Schede profilo +
  spunta "Pulisci profilo precedente". Su Applica: `activate_profile` e riavvia
  il pannello.
- **cli.py** — backend di `nxs-tool` (`profile`/`apply`/`profiles`/`list`/
  `install`/`run`/`launch`/`uninstall`).

Dati: `profiles.json` (4 profili + base: accent, wallpaper, icon, meta, tools)
e `repo.json` (catalogo: category, method, apk/image/pip, bin, description).
Set di tool allineato per categoria a Kali/Parrot.

Integrazione pannello (`nxs_cc/panel.py`): import "morbido" di
`nxs_profiles.model` (try/except). Il menu start mostra "Profilo: <Nome>
(cambia)" -> `nxs-profile`, poi una voce per tool che apre
`lxterminal -e "nxs-tool launch <tool>"` (**stringa singola** dopo `-e`, niente
`sh -c` annidato).

## Sfondi per profilo

`build/make-wallpaper.sh` genera `nebula.png` (base) +
`pentest/forensics/osint/web.png` in
`overlay/home/nexus/.themes/NexusSec-Core/backgrounds/`. **Gotcha ImageMagick**:
lo starfield usa `-threshold 99.75%` (solo lo 0.25% piu' luminoso = stella); con
`0.25%` l'immagine diventa quasi bianca.

## Avvio (Alpine)

- `genapkovl-nexussec.sh` crea l'apkovl: utente `nexus` (wheel + doas),
  autologin tty1 (inittab `agetty --autologin`), servizi OpenRC, e inietta tutto
  `overlay/`.
- `.profile` di nexus: su tty1 esegue `startx` -> `.xinitrc` -> `openbox-session`.
- autostart Openbox: `nxs-tool apply` (sfondo+accent), `pcmanfm --desktop`,
  `nxs-panel`, poi `nxs-profile` (selettore).

## Build

Su host NON-Alpine si usa **`build-alpine/build-in-container.sh`** (serve solo
podman/docker): compila i meta-pacchetti con `abuild` e crea l'ISO con
`mkimage` dentro un container `alpine:edge` **detached** (`nexussec-build`),
output in `out/`. Su Alpine si puo' usare direttamente abuild + mkimage
(vedi `build-alpine/README.md`). `make check`/`make wallpaper` girano ovunque.

Test: `qemu-system-x86_64 -m 4096 -enable-kvm -cdrom out/*.iso -boot d`
(headless: `-display none -qmp unix:...` + screendump via QMP; serve >=2-3GB
RAM perche' la live installa il desktop in tmpfs al boot).

### Gotcha build ISO (DURAMENTE imparati - non re-derivare)

- **`/etc/apk/world` nell'apkovl = cuore di tutto.** L'init dell'initramfs al
  boot installa SOLO `alpine-base` + i pacchetti in `/etc/apk/world`. La lista
  `apks=` di mkimage riempie solo il *repo sul media* (disponibilita'), NON
  decide cosa si installa. `genapkovl` DEVE scrivere `etc/apk/world` con
  `nexussec-base`, altrimenti boot minimale -> loop `can't run /sbin/agetty`.
- **Servizi base: NON scriverli a mano.** Creare `etc/.default_boot_services`
  (vuoto): l'init aggiunge il set standard, inclusi i CRITICI `modloop` (monta
  i moduli del kernel) e `hwdrivers`. Senza `modloop` -> nessun modulo -> niente
  DRM/grafica/rete. Aggiungere a mano solo gli extra in `runlevels/default`
  (local, dbus, udev, udev-trigger, networking).
- **`/home/nexus` finisce root** (il tar apkovl usa `--owner=0`): `local.d`
  fa `chown -R nexus:nexus /home/nexus` + crea `~/.local/share/xorg` ecc.,
  altrimenti Xorg/xauth non scrivono in home e startx fallisce.
- **`/etc/group` dell'apkovl SOVRASCRIVE quello di sistema**: deve essere la
  lista standard Alpine COMPLETA + `nexus` in video/input/audio/kvm/netdev/...
  (senza `video`+`input` Xorg non accede a /dev/dri e /dev/input).
- **Xorg**: `etc/X11/Xwrapper.config` con `needs_root_rights=yes` -> Xorg gira
  da root, funziona con qualsiasi driver (modesetting/vmware/qxl/vesa/fbdev) su
  VirtualBox/VMware/QEMU/HW senza logind/seatd. Driver in `nexussec-base`.
- **Boot BIOS+EFI**: il profilo (`mkimg.nexussec.sh`) DEVE settare
  `output_format="iso"` (non solo `image_ext`), altrimenti `section_syslinux`
  viene saltata e l'ISO esce SOLO-EFI (VirtualBox/SeaBIOS: "no bootable
  medium"). BIOS=isolinux (pkg `syslinux`), EFI=grub-efi. `grub-bios` NON serve.
- **alpine:edge usa apk-tools 3**: in `mkimage.sh` `--no-chown` e' alias di
  `--usermode` (vietato da root) -> il build script lo rimuove via sed.
- **Niente apostrofi** nel blocco `sh -ec '...'` di build-in-container.sh
  (chiuderebbero gli apici e farebbero "leakare" comandi sull'host).
- **Firmware**: il meta `linux-firmware` (~400MB, blob GPU) e `-intel` (122MB)
  gonfiano l'ISO. Usiamo il meta `nexussec-firmware` (subset wireless USB) nel
  MODLOOP via sed sulla sezione kernel (token CORTO: la lista finisce nel
  nome-dir della sezione, limite 255 char). ISO risultante ~725MB (0.7 GB): il salto da ~523MB e' dovuto al browser
  webkit2gtk preinstallato, non a una regressione.
- **Clone aports**: gitlab.alpinelinux.org va spesso in overload -> retry +
  mirror github.com/alpinelinux/aports nel build script.

### Gotcha pacchetti tool C in aports/ (DURAMENTE imparati, NON re-derivare)

I tool non in Alpine sono compilati come piccoli `.apk` del repo `nexussec`
(generati da `scratch/gen-apkbuilds.sh`, collaudati da `scratch/tooltest.sh`).
**Verifica le cause a monte, non a tentativi** (vedi feedback utente). Pattern
ricorrenti su **musl + gcc 15**:

- **podman rootless + tar**: non puo' ripristinare perm/owner all'unpack
  ("Operation not permitted"). Serve `export TAR_OPTIONS="--no-same-owner
  --no-same-permissions"` (gia' in build-in-container.sh e nell'harness).
  Effetto collaterale: toglie il bit exec -> `chmod +x configure` prima di
  lanciarlo per i sorgenti autotools.
- **gcc >=14 promuove a ERRORE**: implicit-function-declaration, int-conversion,
  incompatible-pointer-types, implicit-int. Declassare con `-Wno-error=...`.
- **gcc >=10 usa `-fno-common`** -> "multiple definition" di globali in header
  senza `extern`. Fix: `-fcommon` (es. dirb).
- **musl non ha le `*64` glibc** (`fopen64`...) -> `-Dfopen64=fopen` ecc.;
  `strcasestr`/`u_int` richiedono `-D_GNU_SOURCE` (+ `-include sys/types.h`);
  header glibc-only assenti (`error.h`, `sys/cdefs.h`) -> **shim** via `-I` con
  header creato al volo (es. scalpel error.h, bulk-extractor sys/cdefs.h).
- **Makefile fatti a mano IGNORANO `$CFLAGS`** dell'ambiente. Passare le flag
  sulla riga di `make` (override) o, per autotools, via `CFLAGS=... ./configure`.
  ATTENZIONE: alcune regole usano solo `${LDFLAGS}` (es. `chkdirs` di
  chkrootkit) -> i force-include vanno messi DENTRO `CC` per raggiungere OGNI
  regola. Non sovrascrivere CC se porta `-DVERSION` (foremost): appendere a
  `RAW_FLAGS` via sed.
- **OpenSSL 3**: ha RIMOSSO `SSLv2/SSLv3_client_method` e reso opaca `struct DH`
  -> patch sed dei metodi a `SSLv23` e disabilitare i moduli che accedono ai
  campi (medusa `--enable-module-vnc=no`).
- **man page non compresse**: `abuild` le rifiuta ("Found uncompressed man
  pages"). Per la live: NON installarle o `rm -rf "$pkgdir"/usr/share/man`.
- **symlink nei tarball**: tar (rootless) aborta sul chmod del link (es. medusa
  `README` -> `README.md`). Override `unpack()` con `tar --exclude=...`.
- **URL sorgente**: verificare i TAG reali via API GitHub (dmitry usa `v1.4.0`,
  non `1.3a`; chkrootkit/Magentron non ha tag -> branch `master`). Un 404 al
  checksum NON e' un errore di build: l'harness fa retry e mostra l'output.
- **mhash-dev NON esiste in Alpine** -> stegseek non e' apk: e' `container`
  (`docker.io/rickdejager/stegseek`).

### Gotcha runtime / desktop (testati su VirtualBox, non re-derivare)

- **CSS GTK3, NON GTK4**: `nxs_cc/common.py` (CSS) gira su GTK3. Proprieta'
  come `text-transform`, `letter-spacing` (e altre CSS web/GTK4) NON esistono in
  GTK3: `Gtk.CssProvider.load_from_data` SOLLEVA un'eccezione sul CSS invalido.
  Siccome `apply_css()` e' chiamata all'avvio da TUTTE le app NexusSec, un CSS
  rotto le fa crashare tutte -> niente barra, niente menu, le icone desktop non
  lanciano nulla (sintomo: sfondo+icone visibili ma nulla parte). `apply_css`
  ora avvolge il load in try/except (difensivo), ma evitare comunque proprieta'
  GTK4. Per l'uppercase usare `.upper()` in Python, non `text-transform`.
- **Xorg su VirtualBox VMSVGA**: il driver `xf86-video-vmware` va in SEGFAULT
  ("Unable to map BAR"). RIMOSSO dai depends: Xorg usa `modesetting` via
  `vmwgfx` (DRM gia' presente). Tenere vboxvideo/qxl/vesa/fbdev come alternative.
- **Xorg gira da root**: `etc/X11/Xwrapper.config` con `needs_root_rights=yes`.
- **`/etc/hosts` deve risolvere l'hostname** (`nexussec`): senza, xinit/xauth
  falliscono con `bad display name "nexussec:0"`. Lo scrive genapkovl.
- **Pannello che spariva applicando un profilo**: bug del riavvio barra. NON
  fare `sh -c "pkill -f nxs_cc.panel; ... nxs-panel"`: "nxs_cc.panel" e'
  nell'argv di quella shell e `pkill -f` la suicida. Fix: `pkill` DIRETTO (si
  auto-esclude) + launcher separato il cui argv non contiene il pattern
  (selector.py, panelcfg.py, views.py).
- **Finestre non gestibili** (no move/min/max/close): `rc.xml` deve essere il
  default Openbox COMPLETO (sezione `<mouse>` con tutti i context Frame/
  Titlebar/Close/...). Personalizzati solo theme(NexusSec-Core)/margins(bottom
  34)/desktops/keybind. Un rc.xml ridotto rompe la gestione finestre.
- **Icone desktop che chiedono "eseguire?"**: serve `~/.config/libfm/libfm.conf`
  con `[config] quick_exec=1` -> pcmanfm lancia i `.desktop` senza dialogo.
- **Sfondo non visibile**: `pcmanfm --desktop` disegna il suo sfondo SOPRA feh.
  Lo sfondo va impostato CON pcmanfm: `model.set_wallpaper` usa
  `pcmanfm --set-wallpaper ... --wallpaper-mode=stretch` (fallback feh) e in
  autostart pcmanfm parte PRIMA di `nxs-tool apply`.
- **Tool dal menu che chiudevano il terminale**: `nxs-run-tool` (wrapper) tiene
  aperto il terminale lasciando una shell dopo `nxs-tool launch`.
- **Browser**: il pacchetto Alpine NON e' `webkit2gtk` (inesistente) ma
  `webkit2gtk-4.1` (typelib WebKit2-4.1, che app.py richiede). DAL 2026.08.25 e'
  **PREINSTALLATO** (dep di `nexussec-base`, con `gst-plugins-bad`+`gst-libav`):
  NON rimuoverli. Motivo (causa a monte del "browser non parte / ci mette un
  secolo"): l'install on-demand via apk (a) NON parte OFFLINE da chiavetta (serve
  rete) e (b) online scarica ~50MB al primo avvio (lentissimo). Preinstallandolo
  l'avvio e' istantaneo e offline-ready, ed e' compilato contro la stessa base
  congelata (niente deriva di versione dell'edge rolling). Costo: ISO +~60MB,
  RAM +~220MB. I blocchi `apk add` in `nxs-browser` restano solo come fallback
  (no-op se gia' presente). Idem `nxs-player`: le sue dep gst sono ora nella base.
- **Audio: in VM va, su HW reale NO** (nessun suono ne' speaker ne' cuffie pur
  con un sink "Analog Stereo" presente). Causa a monte: mancavano `sof-firmware`
  (DSP audio dei portatili Intel/AMD moderni; senza, il kernel crea un nodo
  fantoccio che non pilota il codec) e `alsa-ucm-conf` (instradamento UCM per
  PipeWire). `sof-firmware` sta nel MODLOOP (dep di `nexussec-firmware`),
  `alsa-ucm-conf` nel root (dep di `nexussec-base`). In VM non servono (HDA
  emulata). NON rimuoverli. Lo sblocco mixer (`nxs-audio-unmute`, ALSA+wpctl con
  ritentativi, in autostart) copre l'auto-mute ma NON basta senza il firmware.

### Gotcha stile finestre / bytecode (2026-08-26, DURAMENTE imparati)

- **`.pyc` stale nell'apkovl = codice VECCHIO eseguito.** Non committare/impac-
  chettare MAI `__pycache__/*.pyc`. La build e' deterministica (SOURCE_DATE_EPOCH
  azzera i mtime): un `.pyc` obsoleto finisce con lo STESSO mtime del `.py`, e
  Python (3.10) si fida della cache ed esegue il bytecode vecchio -> le modifiche
  ai sorgenti "non si vedono" a runtime. Sintomo reale: lo stile finestre non
  cambiava mai. `genapkovl-nexussec.sh` ora ELIMINA ogni `.pyc/__pycache__`
  prima di impacchettare; `.gitignore` li esclude. Python li rigenera a runtime.
- **Decorazione finestre = TEMA OPENBOX STATICO, non generato.** La barra del
  titolo / bordo / pulsanti li disegna Openbox dal themerc
  `~/.themes/NexusSec-Core/openbox-3/themerc` (file FISSO e curato). NON
  rigenerarlo a runtime: la vecchia generazione dinamica (`write_openbox_theme`)
  era fragile e per giunta `set_window_theme` la sovrascriveva ritingendo il
  bordo con l'accent (`_OB_ACCENT_KEYS` includeva `window.active.border.color`).
  Entrambe sono ora **no-op**. Il font titolo (Chakra Petch) sta in `rc.xml`.
  La parte INTERNA delle finestre resta GTK (`window-style.css`): i 3 stili
  vetro/telaio/flat agiscono SOLO sul contenuto, non sulla decorazione.

## Vincoli (Alpine)

- **musl libc** (Alpine), **non** glibc. Attenzione ai binari pensati per glibc
  (preferire pacchetti apk o container).
- **OpenRC**, niente systemd. Servizi via `rc-update` / `/etc/local.d`.
- Pacchetti via **`apk`** (main/community/testing); privilegi via **`doas`**.
- Tool non in apk -> **container Podman** (preferito, robusto) o **pip/pipx**.
- Mantenere **minimale**, ma il pavimento reale con kernel linux-lts (modloop
  ~300MB) + desktop GTK + Podman + firmware wireless e' **~500-540MB** (scelta
  "Bilanciata"). I ~150-200MB iniziali erano una stima irrealistica per questo
  stack; solo un kernel `linux-virt` (solo VM) si avvicina a ~300MB.
- La barra/CC/selettore sono **Python GTK3**: mantenerli (richiesta esplicita).

## Sicurezza / hardening (2026-08-25)

Modello: **una immagine, due modalità**. La live resta comoda (autologin,
`doas nopass`, credenziali predefinite `nexus`/`nexus` impostate a boot da
`nexussec.start`); il sistema **installato** si irrobustisce con `nxs-harden`.

- **`nxs-harden`** (installato): `passwd`, disattiva autologin (edita
  `/etc/inittab` + `kill -HUP 1`), `doas permit persist` (con password), blocco
  VT/Zap via `/etc/X11/xorg.conf.d/50-nxs-lock.conf` (lock schermo non
  aggirabile con Ctrl+Alt+Fn). GUI: `views.open_security`.
- **`nxs-firewall`** (nftables, dep in base): inbound default-deny, outbound
  libero; attivo a boot (`nxs-firewall boot` in `nexussec.start`), opt-out con
  `/etc/nxs/firewall.disabled`; porte in `/etc/nxs/firewall.allow`. GUI:
  `open_firewall`. NB pentest: per METTERSI IN ASCOLTO serve `allow`/`off`.
- **LUKS persistenza** (dep `cryptsetup`): `nxs-persist` opzione cifra
  (LUKS2 label **NXSCRYPT**); non si monta a boot (serve passphrase) →
  `nxs-unlock-data login` chiamato da `~/.profile` PRIMA di `startx`.
  Setup post-mount condiviso in `/usr/local/lib/nxs-persist-setup.sh` (sorgiato
  da `nexussec.start` e `nxs-unlock-data`).
- **`nxs-users`** (list/passwd/add/del): password **via stdin** (mai in argv).
  GUI `open_users`. **WiFi** PSK idem via stdin + `wpa_passphrase` (niente
  password in `ps`).
- **Pin container per digest**: `isolation._image` usa `image@<digest>` se
  repo.json ha `digest` (opt-in per-tool; NON pinnare kali-rolling in blocco:
  romperebbe il modello rolling).
- **`nxs-ai-sandbox`**: wrapper bubblewrap per il futuro agente AI (root ro,
  home isolata, `--unshare-net` di default).
- GUI privilegiate: le azioni sensibili (utenti/harden/persist) girano in un
  **terminale** (`_run_priv_term`), così `doas` può chiedere la password quando
  il sistema è hardenizzato; sul live (nopass) sono immediate.

## Cosa NON fare

- Non reintrodurre TinyCore: `deb2tcz`, shim `apt`, `.tcz`, `tce-load`,
  isolinux, utente `tc`, `bootlocal.sh`.
- Non usare Docker: l'isolamento a container e' **Podman**.
- Non gonfiare la live: i tool sono **on-demand**, non preinstallati.
- I `depends` dei meta-pacchetti devono usare **nomi di pacchetti apk reali**
  (validare disponibilita' in community/testing); i tool container/pip NON vanno
  nei meta-pacchetti (li gestisce `nxs-tool`).

## Roadmap

1. Migrazione a base **Alpine** (FATTO): apk + OpenRC + Podman/bwrap.
2. Profili dinamici + sfondi + accent + menu (FATTO).
3. Catalogo tool allineato a Kali/Parrot (FATTO).
4. Build `abuild` + `mkimage` (scaffold FATTO; ISO da costruire su Alpine).
5. Persistenza tool (con chiavetta NXSDATA) — FATTO per la live: `~/.local`
   (pip/pipx/git) via bind mount; tool `apk` registrati in
   `/var/nxs-data/tool-state/apk-tools` (hook in `isolation.install`) e
   reinstallati OFFLINE dalla cache al boot (`nxs_persist_reinstall_tools`,
   background); container/kali gia' persistenti (storage Podman). Tutto GATED su
   NXSDATA montato: live nuda invariata. CLI: `nxs-tool persisted|forget`.
6. **Agente AI Python** al cuore del sistema (prossimo step,
   `overlay/usr/local/lib/nxs-ai/`).
7. **Immagine SD per SBC (Raspberry Pi 4/5)** — la ISO aarch64 e' SOLO-UEFI e non
   fa boot sugli SBC (U-Boot / boot proprietario, non UEFI standard). Serve un
   formato diverso: immagine per **scheda SD** con la partizione FAT32 di boot del
   RPi (bootcode/firmware + kernel + initramfs) e il rootfs Alpine + apkovl/overlay
   NexusSec. Scaffold: `build-alpine/build-sd-rpi.sh` (genera `out/nexussec-rpi-*.img.gz`).
   DA TESTARE su hardware reale (build "alla cieca", nessun RPi in sviluppo).
8. **Immagine installabile per Mac Apple Silicon (bare metal, non solo VM)** —
   sessione futura: oggi su M1/M2/M3 si avvia solo in VM (UTM/Parallels); un boot
   nativo richiederebbe l'approccio Asahi (m1n1 + device tree + kernel patchato).
   Da valutare fattibilita' e portata.
