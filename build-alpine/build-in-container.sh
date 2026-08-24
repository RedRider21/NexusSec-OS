#!/bin/sh
# build-in-container.sh - costruisce l'ISO NexusSec dentro un container Alpine.
# Unico requisito sull'host: podman OPPURE docker. Produce out/nexussec-*.iso.
#
# Avvia il container in DETACHED (-d) cosi' la build sopravvive alla chiusura
# della shell/sessione (la gestisce conmon). Tutto l'output va in out/build.log
# (bind mount). Esegue tutto come root nel container (abuild -F): niente su/doas.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/out"

# Architettura target: 1o argomento o env NXS_ARCH, default x86_64.
#   ./build-in-container.sh            -> x86_64 (BIOS+EFI)
#   ./build-in-container.sh aarch64    -> ARM 64 (solo UEFI)
ARCH="${1:-${NXS_ARCH:-x86_64}}"
case "$ARCH" in
  x86_64)  PODMAN_ARCH=amd64 ;;
  aarch64) PODMAN_ARCH=arm64 ;;
  *) echo "ERRORE: arch non supportata: $ARCH (usa x86_64 o aarch64)"; exit 1 ;;
esac
LOG="$ROOT/out/build-$ARCH.log"
CNAME="nexussec-build-$ARCH"
: > "$LOG"

if command -v podman >/dev/null 2>&1; then RT=podman
elif command -v docker >/dev/null 2>&1; then RT=docker
else echo "ERRORE: serve podman o docker."; exit 1; fi
echo "[host] runtime: $RT | arch: $ARCH ($PODMAN_ARCH) | container: $CNAME"
# Su host x86_64 la build aarch64 gira EMULATA (binfmt qemu-aarch64): piu' lenta.

CID=$("$RT" run -d --replace --name "$CNAME" --arch="$PODMAN_ARCH" \
  -e NXS_ARCH="$ARCH" -e NXS_EPOCH="${NXS_EPOCH:-}" \
  -e NXS_FASTBOOT="${NXS_FASTBOOT:-}" --privileged \
  -v "$ROOT:/work" -w /work alpine:edge sh -ec '
  exec >>/work/out/build-$NXS_ARCH.log 2>&1
  set -eu
  echo "[ctr] installo toolchain di build..."
  # main+community+testing: alcune makedepends dei tool C (es. re2-dev) stanno
  # in testing. Riscrivo i repository per averli tutti e tre su edge.
  cat >/etc/apk/repositories <<REPOS
http://dl-cdn.alpinelinux.org/alpine/edge/main
http://dl-cdn.alpinelinux.org/alpine/edge/community
http://dl-cdn.alpinelinux.org/alpine/edge/testing
REPOS
  apk update
  # Boot: EFI = grub-efi; BIOS = isolinux (pacchetto syslinux). grub-bios NON
  # serve (mkimage usa isolinux per il BIOS El Torito).
  # syslinux (boot BIOS/El Torito) esiste SOLO su x86: su aarch64 l ISO e
  # solo-UEFI (grub-efi arm64-efi), quindi lo omettiamo (assente nel repo ARM).
  BOOTPKGS=
  [ "$NXS_ARCH" = x86_64 ] && BOOTPKGS=syslinux
  apk add alpine-sdk abuild build-base git xorriso squashfs-tools \
      mkinitfs grub grub-efi dosfstools mtools python3 \
      alpine-conf doas fakeroot $BOOTPKGS

  echo "[ctr] chiave di firma STABILE (Arsenal committato, non casuale)..."
  # PERCHE non abuild-keygen -an: quello generava una chiave NUOVA ad ogni build,
  # cosi il repo Arsenal online (firmato una volta) restava UNTRUSTED per la live
  # (la .pub spedita non combaciava). Usiamo la coppia stabile committata in
  # build-alpine/arsenal-keys/: la stessa .pub e gia nelloverlay/etc/apk/keys,
  # quindi media-repo, overlay e Arsenal online sono tutti coerenti e fidati.
  export PACKAGER="NexusSec <deplano.d@gmail.com>"
  mkdir -p /root/.abuild /etc/apk/keys
  cp /work/build-alpine/arsenal-keys/nexussecos-arsenal.rsa \
     /work/build-alpine/arsenal-keys/nexussecos-arsenal.rsa.pub /root/.abuild/
  chmod 600 /root/.abuild/nexussecos-arsenal.rsa
  # REPODEST esplicito: l abuild recente di edge usa come default
  # $HOME/.local/share/abuild (non piu /root/packages), rompendo i percorsi
  # attesi sotto (find/cp/--repository). Lo fissiamo per essere deterministici
  # sia in env sia in abuild.conf (autoritativo).
  export REPODEST=/root/packages
  printf "PACKAGER_PRIVKEY=/root/.abuild/nexussecos-arsenal.rsa\nREPODEST=/root/packages\n" \
     > /root/.abuild/abuild.conf
  cp /root/.abuild/nexussecos-arsenal.rsa.pub /etc/apk/keys/

  echo "[ctr] compilo i meta-pacchetti (repo locale nexussec)..."
  mkdir -p /root/nexussec
  cp -a /work/aports/* /root/nexussec/
  for p in nexussec-base nexussec-firmware sec-profile-pentest \
           sec-profile-forensics sec-profile-osint sec-profile-web; do
    ( cd /root/nexussec/$p && abuild -F -d ) || { echo "[ctr] BUILD FALLITA: $p"; exit 1; }
  done

  # Tool C non presenti in Alpine, compilati come piccoli .apk del repo nexussec
  # (a runtime nxs-tool fa apk add dal repo sul media). abuild -r installa da se
  # le makedepends. NON fatale: un tool che non compila resta on-demand via
  # container/pip, quindi proseguo con un avviso invece di abortire la ISO.
  # podman rootless: tar non puo ripristinare perm/owner durante unpack.
  export TAR_OPTIONS="--no-same-owner --no-same-permissions"
  for p in dmitry foremost medusa chkrootkit rkhunter bulk-extractor; do
    [ -d /root/nexussec/$p ] || continue
    ( cd /root/nexussec/$p && abuild -F checksum && abuild -F -r ) \
      || echo "[ctr] ATTENZIONE: tool non compilato (resta on-demand): $p"
  done
  echo "[ctr] pacchetti pronti:"; find /root/packages -name "*.apk"

  echo "[ctr] clono aports ufficiali per mkimage (retry + mirror)..."
  cloned=
  for url in https://gitlab.alpinelinux.org/alpine/aports.git \
             https://github.com/alpinelinux/aports.git \
             https://gitlab.alpinelinux.org/alpine/aports.git; do
    for attempt in 1 2 3; do
      if git clone --depth=1 "$url" /root/aports 2>&1; then cloned=1; break; fi
      echo "[ctr] clone fallito ($url, tent. $attempt), riprovo..."; rm -rf /root/aports; sleep 10
    done
    [ -n "$cloned" ] && break
  done
  [ -n "$cloned" ] || { echo "[ctr] ERRORE: impossibile clonare aports (rete)."; exit 1; }
  cp /work/build-alpine/mkimg.nexussec.sh     /root/aports/scripts/
  cp /work/build-alpine/genapkovl-nexussec.sh /root/aports/scripts/

  # Compat apk-tools 3 (alpine:edge): "--no-chown" e ora alias di "--usermode",
  # vietato da root. mkimage gira qui da root -> rimuovo il flag (initdb root ok).
  sed -i "s/ --no-chown//g" /root/aports/scripts/mkimage.sh

  # Riduzione dimensione ISO: il meta "linux-firmware" tira TUTTI i blob (GPU
  # inclusi, ~400MB) e -intel da solo 122MB. Lo sostituiamo nel modloop (xz,
  # efficiente) col nostro meta "nexussec-firmware" (token CORTO, evita il
  # limite 255 char sul nome-dir della sezione): solo firmware WIRELESS comuni
  # da pentest (Atheros/Realtek/Broadcom/MediaTek), niente Intel ne GPU.
  sed -i "s/ linux-firmware / nexussec-firmware /" /root/aports/scripts/mkimg.base.sh

  # --- Modloop ZSTD (boot piu veloce da USB) -------------------------------
  # Il modloop (squashfs coi moduli kernel) e montato in loop dal media e letto
  # ON-DEMAND al boot. Alpine lo comprime in XZ (update-kernel di alpine-conf,
  # riga "mksquashfs ... -comp xz"): ottimo rapporto ma decompressione LENTA in
  # CPU -> su chiavetta lenta / CPU deboli rallenta il "Mounting boot media" e i
  # primi accessi ai moduli. ZSTD liv.19 decomprime ~35% piu veloce a parita di
  # dimensione (test reale: xz 289MB/1.74s vs zstd 298MB/1.13s, block 256K).
  # GOTCHA (imparato, non re-derivare): update-kernel passa anche $mksfs =
  # "-Xbcj x86" (o arm), che e un filtro SOLO-XZ: con -comp zstd mksquashfs
  # ABORTA ("unrecognised option -Xbcj"). Quindi PRIMA svuotiamo mksfs (togliamo
  # -Xbcj per ogni arch), POI cambiamo il compressore. Il kernel lts ha
  # CONFIG_SQUASHFS_ZSTD=y (verificato), quindi il modloop zstd e montabile e
  # NON serve toccare lo initramfs (stesso squashfs.ko).
  UK=/usr/sbin/update-kernel
  sed -i "s/mksfs=\"-Xbcj[^\"]*\"/mksfs=/g" "$UK"
  sed -i "s/-comp xz /-comp zstd -Xcompression-level 19 -b 262144 /" "$UK"
  echo "[ctr] update-kernel: modloop -> $(grep -oE -- "-comp [a-z]+" "$UK" | head -1)"

  echo "[ctr] preparo overlay con repo nexussec incorporato..."
  # Overlay temporaneo = overlay del repo + repo apk locale (meta sec-profile-*)
  # + chiave pubblica per fidarsi dei nostri .apk a runtime. Cosi la live puo
  # fare "apk add sec-profile-*" anche offline (i tool veri arrivano da edge).
  rm -rf /tmp/ovl; cp -a /work/overlay /tmp/ovl
  mkdir -p /tmp/ovl/var/lib/nexussec-repo /tmp/ovl/etc/apk/keys
  cp -a /root/packages/nexussec/. /tmp/ovl/var/lib/nexussec-repo/
  cp /root/.abuild/*.rsa.pub /tmp/ovl/etc/apk/keys/

  # Data del nome ISO (SOURCE_DATE_EPOCH): se passato NXS_EPOCH lo forziamo,
  # cosi la ISO puo essere datata a un giorno preciso indipendentemente dall ora
  # UTC di build (mkimage usa questo epoch per il YYMMDD del nome).
  if [ -n "$NXS_EPOCH" ]; then export SOURCE_DATE_EPOCH="$NXS_EPOCH"; fi

  # --- FAST-BOOT (opt-in NXS_FASTBOOT=1): root GIA installato in squashfs -----
  # Sposta al build-time linstallazione desktop che la live faceva ad ogni boot
  # (~30s in RAM). Patcha linit dellinitramfs perche monti nxs-rootfs.squashfs
  # (ro) + overlay tmpfs, e costruisce quel squashfs. La build normale resta
  # invariata quando NXS_FASTBOOT non e 1.
  if [ "$NXS_FASTBOOT" = 1 ]; then
    echo "[ctr] FAST-BOOT: patch init dellinitramfs..."
    python3 /work/build-alpine/fastboot-init-patch.py /usr/share/mkinitfs/initramfs-init
    echo "[ctr] FAST-BOOT: costruzione root pre-installato (squashfs)..."
    sh /work/build-alpine/fastboot-rootfs.sh /work/out/nxs-rootfs.squashfs
  fi

  echo "[ctr] mkimage..."
  # La live deve FIDARSI del repo firmato sul media: passiamo la nostra pubkey
  # a mkimage (la copia in APKROOT/etc/apk/keys e firma indice del media).
  # NB: niente apostrofi in questo blocco (e tra apici singoli per podman).
  export PACKAGER_PUBKEY="$(ls /root/.abuild/*.rsa.pub | head -1)"
  export NXS_OVERLAY=/tmp/ovl NXS_OUT=/work/out
  cd /root/aports/scripts
  sh ./mkimage.sh --profile nexussec \
     --outdir /work/out --arch "$NXS_ARCH" \
     --repository http://dl-cdn.alpinelinux.org/alpine/edge/main \
     --repository http://dl-cdn.alpinelinux.org/alpine/edge/community \
     --repository http://dl-cdn.alpinelinux.org/alpine/edge/testing \
     --repository /root/packages/nexussec

  # FAST-BOOT: inietta il root pre-costruito nella ROOT del media (xorriso
  # preservando El Torito BIOS+EFI e MBR ibrido). Linit lo trova come
  # /media/*/nxs-rootfs.squashfs e ci monta sopra loverlay.
  if [ "$NXS_FASTBOOT" = 1 ]; then
    iso=$(ls -t /work/out/alpine-nexussec-*-"$NXS_ARCH".iso | head -1)
    if [ -f /work/out/nxs-rootfs.squashfs ] && [ -n "$iso" ]; then
      echo "[ctr] inietto nxs-rootfs.squashfs in $iso"
      xorriso -indev "$iso" -outdev "$iso".new -boot_image any replay \
        -map /work/out/nxs-rootfs.squashfs /nxs-rootfs.squashfs \
        && mv "$iso".new "$iso"
      rm -f /work/out/nxs-rootfs.squashfs
    fi
  fi

  # SPLASH VERA: inietta fbsplash.ppm nella ROOT del media. Linit dellinitramfs
  # (KOPT_splash attivo di default) lo trova come /media/*/fbsplash.ppm e lancia
  # `fbsplash -T 16` -> immagine sul framebuffer per TUTTO il boot, poi X-splash
  # animata identica -> desktop. Stesso xorriso replay del fast-boot (preserva
  # El Torito BIOS+EFI e MBR ibrido). Sempre attivo (non gated da NXS_FASTBOOT).
  iso=$(ls -t /work/out/alpine-nexussec-*-"$NXS_ARCH".iso | head -1)
  if [ -f /work/build-alpine/fbsplash.ppm ] && [ -n "$iso" ]; then
    echo "[ctr] inietto fbsplash.ppm (splash nativa) in $iso"
    xorriso -indev "$iso" -outdev "$iso".new -boot_image any replay \
      -map /work/build-alpine/fbsplash.ppm /fbsplash.ppm \
      && mv "$iso".new "$iso"
  else
    echo "[ctr] ATTENZIONE: fbsplash.ppm assente, splash nativa NON iniettata"
  fi

  echo "[ctr] FATTO. ISO in /work/out:"
  ls -lh /work/out/*.iso
')
echo "[host] container avviato: $CID"
echo "[host] segui con: tail -f out/build-$ARCH.log   |   podman logs -f $CNAME"
