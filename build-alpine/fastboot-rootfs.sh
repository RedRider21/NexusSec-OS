#!/bin/sh
# fastboot-rootfs.sh - costruisce il ROOT GIA' INSTALLATO di NexusSec e lo
# comprime in un squashfs (nxs-rootfs.squashfs). Eseguito DENTRO il container di
# build DOPO la compilazione dei meta-pacchetti e la preparazione di /tmp/ovl.
#
# Sposta al BUILD-TIME cio' che la live faceva ad OGNI boot (apk add di ~500MB
# in RAM, i famosi ~30s): al boot l'init monta questo squashfs read-only +
# overlay tmpfs -> avvio in pochi secondi, come le altre distro.
#
# Uso:  sh fastboot-rootfs.sh [/percorso/out/nxs-rootfs.squashfs]
set -eu

ROOTFS=/tmp/nxs-rootfs
OUT="${1:-/work/out/nxs-rootfs.squashfs}"
KEYS=/etc/apk/keys
APORTS_SCRIPTS=/root/aports/scripts

REPO_MAIN="http://dl-cdn.alpinelinux.org/alpine/edge/main"
REPO_COMM="http://dl-cdn.alpinelinux.org/alpine/edge/community"
REPO_TEST="http://dl-cdn.alpinelinux.org/alpine/edge/testing"
REPO_NXS="/root/packages/nexussec"

rm -rf "$ROOTFS"; mkdir -p "$ROOTFS"

echo "[fastboot] apk install del root completo (alpine-base + nexussec-base)..."
apk add --root "$ROOTFS" --initdb --keys-dir "$KEYS" \
    --repository "$REPO_MAIN" --repository "$REPO_COMM" \
    --repository "$REPO_TEST" --repository "$REPO_NXS" \
    alpine-base nexussec-base openssl

# --- config runtime: riusiamo genapkovl (inittab autologin, hosts, doas,
#     overlay/, world, ...) MA SENZA sovrascrivere passwd/group/shadow: quelli
#     li ha gia' creati apk (root + utenti di SERVIZIO come messagebus per dbus,
#     polkitd, ecc.). Sovrascriverli farebbe fallire dbus & co. ------------------
echo "[fastboot] applico la config (overlay) nel root, esclusi passwd/group/shadow..."
( cd /tmp && NXS_OVERLAY=/tmp/ovl sh "$APORTS_SCRIPTS/genapkovl-nexussec.sh" nexussec )
tar -xzf /tmp/nexussec.apkovl.tar.gz -C "$ROOTFS" \
    --exclude=etc/passwd --exclude=etc/group --exclude=etc/shadow

# --- utente nexus + gruppi + password vuote + SERVIZI, dentro il chroot (cosi'
#     preserviamo gli utenti di servizio di apk e usiamo rc-update nativo) -------
echo "[fastboot] utente/gruppi/servizi via chroot..."
cp -f /etc/resolv.conf "$ROOTFS"/etc/resolv.conf 2>/dev/null || true
chroot "$ROOTFS" /bin/sh -eu <<'CHROOT'
adduser -D -h /home/nexus -s /bin/sh -u 1000 nexus 2>/dev/null || true
for g in wheel video input audio cdrom dialout netdev kvm tty usb; do
    addgroup nexus "$g" 2>/dev/null || true
done
passwd -d root 2>/dev/null || true
passwd -d nexus 2>/dev/null || true
# servizi standard di boot (nel prebuilt li impostiamo noi: nessun init live)
for s in devfs dmesg mdev hwdrivers modloop; do rc-update add "$s" sysinit 2>/dev/null || true; done
for s in modules sysctl hostname bootmisc syslog hwclock; do rc-update add "$s" boot 2>/dev/null || true; done
for s in mount-ro killprocs savecache; do rc-update add "$s" shutdown 2>/dev/null || true; done
for s in firstboot local dbus udev udev-trigger networking cgroups; do rc-update add "$s" default 2>/dev/null || true; done
CHROOT

# --- repositories per apk a RUNTIME (sec-profile-* offline dal repo locale nel
#     root; tool veri online da edge) ---
mkdir -p "$ROOTFS"/etc/apk "$ROOTFS"/etc/apk/keys "$ROOTFS"/var/cache/misc
cat > "$ROOTFS"/etc/apk/repositories <<EOF
$REPO_MAIN
$REPO_COMM
$REPO_TEST
/var/lib/nexussec-repo
EOF
cp "$KEYS"/*.pub "$ROOTFS"/etc/apk/keys/ 2>/dev/null || true
cp "$KEYS"/*.pub "$ROOTFS"/var/cache/misc/ 2>/dev/null || true

# fstab minimale (il root e' gestito dall'init via overlay)
[ -f "$ROOTFS"/etc/fstab ] || printf 'tmpfs /tmp tmpfs nosuid,nodev 0 0\n' > "$ROOTFS"/etc/fstab

echo "[fastboot] mksquashfs (zstd)..."
rm -f "$OUT"
mksquashfs "$ROOTFS" "$OUT" -comp zstd -Xcompression-level 19 -b 262144 -noappend
echo "[fastboot] root pre-costruito:"; ls -lh "$OUT"
du -sh "$ROOTFS" 2>/dev/null || true
