#!/bin/sh
# build-sd-rpi.sh - costruisce l'immagine microSD NexusSec per Raspberry Pi 4/5.
#
# Perche' non la ISO: gli SBC non fanno boot da ISO UEFI. Il Raspberry Pi ha un
# boot proprietario (la GPU legge una FAT32: bootcode/start*.elf -> kernel). Qui
# usiamo il collaudato boot 'rpi' di Alpine (kernel linux-rpi + firmware) con i
# pacchetti e l'apkovl di NexusSec, e lo impacchettiamo in un .img.gz flashabile
# con dd / Raspberry Pi Imager / balenaEtcher.
#
# Unico requisito host: podman (o docker). Output: out/nexussec-rpi-*.img.gz
#
#   ./build-alpine/build-sd-rpi.sh
#
# NB (onesto): build "alla cieca" - nessun RPi in sviluppo. E' costruita col
# metodo diskless ufficiale Alpine, ma va VALIDATA su hardware reale. Vedi la
# voce 7 della roadmap in CLAUDE.md.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/out"

ARCH=aarch64
PODMAN_ARCH=arm64
LOG="$ROOT/out/build-sd-rpi.log"
CNAME="nexussec-build-sd-rpi"
# Margine libero della FAT32 oltre al contenuto (per apk/cache/persistenza lbu).
PART_SLACK_PCT="${NXS_SD_SLACK:-40}"
MIN_IMG_MB="${NXS_SD_MIN_MB:-2048}"
: > "$LOG"

if command -v podman >/dev/null 2>&1; then RT=podman
elif command -v docker >/dev/null 2>&1; then RT=docker
else echo "ERRORE: serve podman o docker."; exit 1; fi
echo "[host] runtime: $RT | target: Raspberry Pi ($ARCH/$PODMAN_ARCH) | container: $CNAME"
echo "[host] build ARM emulata (binfmt qemu-aarch64): piu' lenta. Segui: tail -f $LOG"

CID=$("$RT" run -d --replace --name "$CNAME" --arch="$PODMAN_ARCH" \
  -e NXS_ARCH="$ARCH" -e PART_SLACK_PCT="$PART_SLACK_PCT" -e MIN_IMG_MB="$MIN_IMG_MB" \
  --privileged -v "$ROOT:/work" -w /work alpine:edge sh -ec '
  exec >>/work/out/build-sd-rpi.log 2>&1
  set -eu
  echo "[ctr] installo toolchain di build..."
  cat >/etc/apk/repositories <<REPOS
http://dl-cdn.alpinelinux.org/alpine/edge/main
http://dl-cdn.alpinelinux.org/alpine/edge/community
http://dl-cdn.alpinelinux.org/alpine/edge/testing
REPOS
  apk update
  # mtools: popola la FAT32 SENZA loop-mount (funziona in container rootless).
  # dosfstools: mkfs.vfat. util-linux: sfdisk (tabella MBR). + toolchain meta.
  apk add alpine-sdk abuild git xorriso squashfs-tools mkinitfs grub grub-efi \
      dosfstools mtools util-linux e2fsprogs python3 alpine-conf doas fakeroot \
      xz gzip tar

  echo "[ctr] chiave di firma STABILE (Arsenal committato)..."
  export PACKAGER="NexusSec <deplano.d@gmail.com>"
  mkdir -p /root/.abuild /etc/apk/keys
  cp /work/build-alpine/arsenal-keys/nexussecos-arsenal.rsa \
     /work/build-alpine/arsenal-keys/nexussecos-arsenal.rsa.pub /root/.abuild/
  chmod 600 /root/.abuild/nexussecos-arsenal.rsa
  export REPODEST=/root/packages
  printf "PACKAGER_PRIVKEY=/root/.abuild/nexussecos-arsenal.rsa\nREPODEST=/root/packages\n" \
     > /root/.abuild/abuild.conf
  cp /root/.abuild/nexussecos-arsenal.rsa.pub /etc/apk/keys/

  echo "[ctr] compilo i meta-pacchetti NexusSec (repo locale)..."
  # Solo i META (veloci): tool C (dmitry/foremost/...) restano on-demand.
  mkdir -p /root/nexussec
  cp -a /work/aports/* /root/nexussec/
  for p in nexussec-base nexussec-firmware sec-profile-pentest \
           sec-profile-forensics sec-profile-osint sec-profile-web; do
    ( cd /root/nexussec/$p && abuild -F -d ) || { echo "[ctr] BUILD FALLITA: $p"; exit 1; }
  done
  echo "[ctr] pacchetti pronti:"; find /root/packages -name "*.apk" | head

  echo "[ctr] clono aports ufficiali (per mkimage + profilo rpi)..."
  cloned=
  for url in https://gitlab.alpinelinux.org/alpine/aports.git \
             https://github.com/alpinelinux/aports.git; do
    for attempt in 1 2 3; do
      if git clone --depth=1 "$url" /root/aports 2>&1; then cloned=1; break; fi
      echo "[ctr] clone fallito ($url, tent. $attempt), riprovo..."; rm -rf /root/aports; sleep 10
    done
    [ -n "$cloned" ] && break
  done
  [ -n "$cloned" ] || { echo "[ctr] ERRORE: impossibile clonare aports."; exit 1; }
  cp /work/build-alpine/mkimg.nexussec-rpi.sh /root/aports/scripts/
  cp /work/build-alpine/genapkovl-nexussec.sh /root/aports/scripts/
  # compat apk-tools 3: --no-chown vietato da root
  sed -i "s/ --no-chown//g" /root/aports/scripts/mkimage.sh
  # firmware ridotto (come per la ISO): niente 400MB di blob GPU/Intel
  sed -i "s/ linux-firmware / nexussec-firmware /" /root/aports/scripts/mkimg.base.sh

  echo "[ctr] preparo overlay con repo nexussec incorporato..."
  rm -rf /tmp/ovl; cp -a /work/overlay /tmp/ovl
  mkdir -p /tmp/ovl/var/lib/nexussec-repo /tmp/ovl/etc/apk/keys
  cp -a /root/packages/nexussec/. /tmp/ovl/var/lib/nexussec-repo/
  cp /root/.abuild/*.rsa.pub /tmp/ovl/etc/apk/keys/

  echo "[ctr] mkimage (profilo nexussec-rpi -> tar.gz diskless)..."
  export PACKAGER_PUBKEY="$(ls /root/.abuild/*.rsa.pub | head -1)"
  export NXS_OVERLAY=/tmp/ovl NXS_OUT=/work/out
  cd /root/aports/scripts
  sh ./mkimage.sh --profile nexussec_rpi \
     --outdir /work/out --arch "$NXS_ARCH" \
     --repository http://dl-cdn.alpinelinux.org/alpine/edge/main \
     --repository http://dl-cdn.alpinelinux.org/alpine/edge/community \
     --repository http://dl-cdn.alpinelinux.org/alpine/edge/testing \
     --repository /root/packages/nexussec

  TGZ=$(ls -t /work/out/nexussec-rpi-*.tar.gz 2>/dev/null | head -1)
  [ -n "$TGZ" ] || { echo "[ctr] ERRORE: tar.gz rpi non prodotto"; exit 1; }
  echo "[ctr] tar.gz: $TGZ"

  # --- Impacchetto il tar.gz in un .img flashabile (FAT32, no loop-mount) ----
  echo "[ctr] estraggo e costruisco la microSD image..."
  rm -rf /tmp/sdroot; mkdir -p /tmp/sdroot
  tar -xzf "$TGZ" -C /tmp/sdroot
  # abilito SSH-less? no. Aggiungo usercfg.txt utile se assente (UART on).
  [ -f /tmp/sdroot/usercfg.txt ] || printf "enable_uart=1\n" > /tmp/sdroot/usercfg.txt

  USED_KB=$(du -sk /tmp/sdroot | cut -f1)
  PART_KB=$(( USED_KB + USED_KB * PART_SLACK_PCT / 100 ))
  MIN_KB=$(( MIN_IMG_MB * 1024 ))
  # la partizione parte a 1 MiB (2048 settori); totale = min(garantito) o calcolato
  [ "$PART_KB" -lt "$((MIN_KB - 1024))" ] && PART_KB=$((MIN_KB - 1024))
  # allineo la partizione a 4 MiB
  PART_KB=$(( (PART_KB + 4095) / 4096 * 4096 ))
  echo "[ctr] contenuto ${USED_KB}KB -> partizione FAT32 ${PART_KB}KB"

  # 1) partizione FAT32 popolata via mtools (niente mount)
  rm -f /tmp/part.img /tmp/disk.img
  truncate -s "${PART_KB}K" /tmp/part.img
  mkfs.vfat -F 32 -n NEXUSSEC /tmp/part.img
  export MTOOLS_SKIP_CHECK=1
  # copio TUTTO il contenuto (file e cartelle) nella radice della FAT32
  for entry in /tmp/sdroot/* /tmp/sdroot/.[!.]*; do
    [ -e "$entry" ] || continue
    mcopy -s -i /tmp/part.img "$entry" ::
  done

  # 2) disco con MBR: 1 partizione FAT32 (tipo 0x0c, LBA) a settore 2048, bootable
  DISK_KB=$(( PART_KB + 1024 ))          # + 1 MiB per la tabella/allineamento
  truncate -s "${DISK_KB}K" /tmp/disk.img
  echo "start=2048, type=c, bootable" | sfdisk /tmp/disk.img
  dd if=/tmp/part.img of=/tmp/disk.img bs=512 seek=2048 conv=notrunc status=none

  VER=$(basename "$TGZ" | sed -E "s/nexussec-rpi-(.*)-aarch64\.tar\.gz/\1/")
  OUT="/work/out/nexussec-rpi-${VER}-aarch64.img"
  mv /tmp/disk.img "$OUT"
  echo "[ctr] comprimo $OUT.gz ..."
  gzip -f -9 "$OUT"
  echo "[ctr] FATTO."
  ls -lh /work/out/nexussec-rpi-*.img.gz
')
echo "[host] container avviato: $CID"
echo "[host] segui con: tail -f out/build-sd-rpi.log   |   podman logs -f $CNAME"
echo "[host] a fine build: out/nexussec-rpi-*.img.gz -> scrivi su microSD con"
echo "       dd/Raspberry Pi Imager/balenaEtcher, poi inserisci nel RPi 4/5."
