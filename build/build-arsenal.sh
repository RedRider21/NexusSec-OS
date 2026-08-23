#!/bin/sh
# build-arsenal.sh - compila e FIRMA gli 8 pacchetti tool con la chiave STABILE
# di NexusSecOS-Arsenal e genera l'APKINDEX, copiandoli in docs/x86_64/ del repo
# arsenal (radice di GitHub Pages). Da rieseguire quando cambia un APKBUILD.
#
# La chiave privata stabile sta in build-alpine/arsenal-keys/ (SOLO locale, MAI
# pubblicata). La pubblica e' gia' nel repo (docs/) e nell'overlay della live.
set -eu
SRC="$(cd "$(dirname "$0")/.." && pwd)"
ARS="${ARS:-$SRC/../NexusSecOS-Arsenal}"
OUT="$ARS/docs/x86_64"
KEYDIR="$SRC/build-alpine/arsenal-keys"

[ -f "$KEYDIR/nexussecos-arsenal.rsa" ] || { echo "ERRORE: chiave privata assente in $KEYDIR"; exit 1; }
mkdir -p "$OUT"

podman run --rm \
  -v "$SRC:/work" -v "$OUT:/out" -v "$KEYDIR:/keys:ro" \
  alpine:edge sh -ec '
  cat >/etc/apk/repositories <<EOF
http://dl-cdn.alpinelinux.org/alpine/edge/main
http://dl-cdn.alpinelinux.org/alpine/edge/community
http://dl-cdn.alpinelinux.org/alpine/edge/testing
EOF
  apk update -q
  apk add -q alpine-sdk abuild build-base file >/dev/null 2>&1

  # Chiave di firma STABILE dellarsenal (no keygen: usiamo la nostra).
  mkdir -p /root/.abuild
  cp /keys/nexussecos-arsenal.rsa /root/.abuild/
  cp /keys/nexussecos-arsenal.rsa.pub /root/.abuild/
  chmod 600 /root/.abuild/nexussecos-arsenal.rsa
  echo "PACKAGER=\"NexusSec <deplano.d@gmail.com>\"" > /root/.abuild/abuild.conf
  echo "PACKAGER_PRIVKEY=/root/.abuild/nexussecos-arsenal.rsa" >> /root/.abuild/abuild.conf
  cp /root/.abuild/nexussecos-arsenal.rsa.pub /etc/apk/keys/

  export REPODEST=/root/packages
  export TAR_OPTIONS="--no-same-owner --no-same-permissions"

  for t in dmitry foremost medusa chkrootkit rkhunter bulk-extractor; do
    echo "=== build $t ==="
    mkdir -p /root/arsenal/$t
    cp /work/aports/$t/APKBUILD /root/arsenal/$t/
    ( cd /root/arsenal/$t && abuild -F checksum && abuild -F -r ) \
      || { echo "### FAIL $t"; exit 1; }
  done

  echo "=== indice firmato ==="
  ls -1 /root/packages/arsenal/x86_64/
  cp -a /root/packages/arsenal/x86_64/. /out/
  echo "=== pubblicati in /out ==="
  ls -1 /out/
'
echo "Fatto: pacchetti firmati in $OUT"
