#!/bin/sh
# Collauda gli APKBUILD dei tool C in alpine:edge, da ROOT con abuild -F
# (come la build reale: niente fakeroot/tar-chmod). Per ognuno: checksum + build.
# Salva gli APKBUILD con sha512 calcolato per i PASS.
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"

podman run --rm -v "$REPO:/work" alpine:edge sh -ec '
  cat >/etc/apk/repositories <<EOF
http://dl-cdn.alpinelinux.org/alpine/edge/main
http://dl-cdn.alpinelinux.org/alpine/edge/community
http://dl-cdn.alpinelinux.org/alpine/edge/testing
EOF
  apk update -q
  # Toolchain BASE identica a build-in-container.sh: solo alpine-sdk/abuild/
  # build-base (+file). TUTTO il resto (autoconf, *-dev, linux-headers, flex...)
  # DEVE arrivare dalle makedepends via "abuild -r", cosi verifichiamo davvero
  # la completezza delle dipendenze invece di mascherarle (niente apostrofi qui).
  for p in alpine-sdk abuild build-base file; do
    apk add -q "$p" >/dev/null 2>&1 || echo "  (dep mancante, ignoro: $p)"
  done

  export PACKAGER="NexusSec <build@nexussec.local>"
  export REPODEST=/root/packages
  # podman rootless: tar non puo ripristinare perm/owner durante unpack.
  export TAR_OPTIONS="--no-same-owner --no-same-permissions"
  abuild-keygen -an >/dev/null 2>&1
  cp /root/.abuild/*.rsa.pub /etc/apk/keys/ 2>/dev/null || true

  RESULT=""
  for t in dmitry foremost dirb medusa chkrootkit rkhunter scalpel bulk-extractor; do
    echo "============================================================"
    echo ">>> BUILD $t"
    # Compilo nel FS del container (non nel bind-mount /work: root non riesce a
    # chmod sui file di proprieta host -> unpack failed).
    mkdir -p /root/b/$t; cp /work/aports/$t/APKBUILD /root/b/$t/
    cd /root/b/$t
    # checksum con retry: il download da GitHub a volte fallisce e NON e un
    # errore di build (cosi non lo confondo con un fallimento di compilazione).
    cks=
    for c in 1 2 3; do
      abuild -F checksum 2>&1 && { cks=1; break; }
      echo "  (checksum tentativo $c fallito, riprovo tra 5s)"; sleep 5
    done
    if [ -n "$cks" ] && abuild -F -r 2>&1; then
      echo "### PASS $t"; RESULT="$RESULT PASS:$t"
      cp /root/b/$t/APKBUILD /work/aports/$t/APKBUILD   # salva con sha512
    else
      echo "### FAIL $t"; RESULT="$RESULT FAIL:$t"
    fi
  done
  echo "============================================================"
  echo "RIEPILOGO:$RESULT"
'
