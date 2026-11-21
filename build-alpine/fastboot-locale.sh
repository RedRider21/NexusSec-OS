#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
# fastboot-locale.sh - converte una ISO NexusSec nel formato FAST-BOOT, tutto
# IN LOCALE e SENZA RETE (container con --network none, nessun download).
#
# Normale: a ogni avvio la live installa in RAM ~595 pacchetti presi da apks/
# (circa 2 minuti, ~1,5 GB di RAM occupati). Fast-boot: il sistema e' GIA'
# installato in nxs-rootfs.squashfs; l'init lo monta in sola lettura + uno
# strato tmpfs per le modifiche (overlay). Misurato il 2026-11-21: squashfs
# 309 MB contro 374 MB di apks/ -> la ISO DIMAGRISCE.
#
#   1. estrae apks/<arch> dalla ISO (i pacchetti ci sono gia')
#   2. li installa in una cartella eseguendo gli script dei pacchetti, in un
#      container della STESSA architettura (alpine:3.22 amd64 / alpine:edge
#      arm64 emulato), con --network none
#   3. applica l'apkovl NexusSec (overlay), crea l'utente nexus, sfoltisce le
#      traduzioni
#   4. squashfs zstd -> nxs-rootfs.squashfs
#   5. initramfs: ACCODA un piccolo cpio con l'init patchato
#      (fastboot-init-patch.py). Il kernel scompatta gli archivi in sequenza e
#      l'ultimo "init" vince: il resto dell'initramfs resta identico (nodi di
#      device compresi, che da utente non si potrebbero ricreare)
#   6. xorriso -boot_image any replay: toglie apks/, aggiunge lo squashfs,
#      sostituisce l'initramfs. L'avvio ibrido (MBR+GPT, El Torito BIOS/EFI)
#      viene RIPRODOTTO identico (codice MBR verificato byte per byte).
#
# Uso:  build-alpine/fastboot-locale.sh ISO_IN APKOVL ISO_OUT ARCH [CARTELLA_LAVORO]
#   APKOVL = nexussec.apkovl.tar.gz gia' generato per quella arch (overlay +
#            var/lib/nexussec-repo), vedi README > remaster.
# Richiede: podman (immagini alpine gia' presenti), mksquashfs, cpio, gzip,
# .tools/xorriso.sh. Spazio temporaneo ~2,5 GB, cancellato alla fine.
set -eu

ISO="$1"; OVL="$2"; OUT="$3"; ARCH="$4"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
W="${5:-$(mktemp -d)}"
XORRISO="$REPO/.tools/xorriso.sh"
case "$ARCH" in
  x86_64)  IMG=docker.io/library/alpine:3.22; PARCH=amd64 ;;
  aarch64) IMG=docker.io/library/alpine:edge; PARCH=arm64 ;;
  *) echo "arch non supportata: $ARCH" >&2; exit 2 ;;
esac
[ -x "$XORRISO" ] || { echo "manca $XORRISO" >&2; exit 2; }
[ "$(podman image inspect "$IMG" --format '{{.Architecture}}' 2>/dev/null)" = "$PARCH" ] \
  || { echo "immagine $IMG ($PARCH) non presente in locale: non la scarico." >&2; exit 2; }

mkdir -p "$W"
echo "[fastboot] cartella di lavoro: $W"

echo "[fastboot] 1/6 estraggo i pacchetti dalla ISO..."
rm -rf "$W/repo" "$W/nxsrepo"; mkdir -p "$W/repo" "$W/nxsrepo"
"$XORRISO" -osirrox on -indev "$ISO" -extract /apks "$W/repo/apks" >/dev/null 2>&1
tar xzf "$OVL" -C "$W/nxsrepo" var/lib/nexussec-repo
cp "$OVL" "$W/apkovl.tar.gz"
# gruppi di nexus dall'apkovl (stessa lista della live normale)
GRUPPI="$(tar xzOf "$OVL" etc/group | awk -F: '$4 ~ /(^|,)nexus(,|$)/ {print $1}' | tr '\n' ' ')"

echo "[fastboot] 2-3/6 installo il sistema (offline) e applico l'overlay..."
podman run --rm --network none --arch "$PARCH" -e GRUPPI="$GRUPPI" -e ARCH="$ARCH" \
  -v "$W":/w:Z "$IMG" sh -euc '
  R=/w/rootfs
  rm -rf "$R"; mkdir -p "$R"
  apk add --root "$R" --initdb --allow-untrusted --arch "$ARCH" \
      --repositories-file /dev/null \
      -X /w/repo/apks -X /w/nxsrepo/var/lib/nexussec-repo \
      alpine-base nexussec-base sfdisk partx openssl >/w/apk.log 2>&1 \
    || { tail -20 /w/apk.log; exit 1; }
  tail -1 /w/apk.log
  # overlay NexusSec, ma NON passwd/group/shadow: li ha creati apk (utenti di
  # servizio: messagebus, polkitd...). Sovrascriverli rompe dbus & co.
  tar xzf /w/apkovl.tar.gz -C "$R" --exclude=etc/passwd --exclude=etc/group \
      --exclude=etc/shadow
  chroot "$R" /bin/sh -c "adduser -D -h /home/nexus -s /bin/sh -u 1000 nexus 2>/dev/null || true
    for g in $GRUPPI; do addgroup nexus \$g 2>/dev/null || true; done
    passwd -d root >/dev/null 2>&1 || true; passwd -d nexus >/dev/null 2>&1 || true"
  # repository a runtime: tool on-demand da edge + repo nexussec locale
  cat > "$R"/etc/apk/repositories <<EOF
http://dl-cdn.alpinelinux.org/alpine/edge/main
http://dl-cdn.alpinelinux.org/alpine/edge/community
http://dl-cdn.alpinelinux.org/alpine/edge/testing
/var/lib/nexussec-repo
EOF
  [ -f "$R"/etc/fstab ] || printf "tmpfs /tmp tmpfs nosuid,nodev 0 0\n" > "$R"/etc/fstab
  sh "$R"/usr/local/lib/nxs-prune-locales.sh "$R" >/dev/null 2>&1 || true
  rm -rf "$R"/var/cache/apk/* 2>/dev/null || true
  du -sh "$R"
'

echo "[fastboot] 4/6 squashfs (zstd)..."
rm -f "$W/nxs-rootfs.squashfs"
podman unshare mksquashfs "$W/rootfs" "$W/nxs-rootfs.squashfs" -comp zstd \
  -Xcompression-level 19 -b 262144 -noappend -quiet -no-progress >/dev/null
ls -l "$W/nxs-rootfs.squashfs" | awk '{printf "  squashfs: %.0f MB\n", $5/1048576}'

echo "[fastboot] 5/6 initramfs: accodo l'init patchato..."
INITRD=boot/initramfs-lts
"$XORRISO" -osirrox on -indev "$ISO" -extract /$INITRD "$W/initramfs.orig" >/dev/null 2>&1
rm -rf "$W/initpatch"; mkdir -p "$W/initpatch"
( cd "$W/initpatch" && gzip -dc "$W/initramfs.orig" | cpio -i --quiet init 2>/dev/null )
python3 "$REPO/build-alpine/fastboot-init-patch.py" "$W/initpatch/init"
chmod 755 "$W/initpatch/init"
( cd "$W/initpatch" && echo init | cpio -o --quiet -H newc -R 0:0 | gzip -9n > "$W/init.cpio.gz" )
cat "$W/initramfs.orig" "$W/init.cpio.gz" > "$W/initramfs.new"

echo "[fastboot] 6/6 nuova ISO (xorriso replay: avvio identico)..."
rm -f "$OUT"
"$XORRISO" -indev "$ISO" -outdev "$OUT" -boot_image any replay \
  -rm_r /apks -- \
  -map "$W/nxs-rootfs.squashfs" /nxs-rootfs.squashfs \
  -map "$W/initramfs.new" /$INITRD \
  -map "$OVL" /nexussec.apkovl.tar.gz 2>&1 | grep -E "completed|FAILURE|SORRY" || true
ls -l "$ISO" "$OUT" | awk '{printf "  %s: %.0f MB\n", $9, $5/1048576}'

echo "[fastboot] pulizia..."
podman unshare rm -rf "$W/rootfs"
rm -rf "$W/repo" "$W/nxsrepo" "$W/initpatch" "$W/initramfs.orig" "$W/initramfs.new" \
       "$W/init.cpio.gz" "$W/nxs-rootfs.squashfs" "$W/apkovl.tar.gz" "$W/apk.log"
rmdir "$W" 2>/dev/null || true
echo "[fastboot] FATTO: $OUT"
