#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
# build-arsenal.sh - compila i tool del repository apk "Arsenal" pubblicato su
# GitHub Pages (docs/<arch>/ del branch main) e ne crea l'indice FIRMATO.
#
# Perche' a parte: la ISO incorpora solo una parte di questi pacchetti (quelli
# usati dal media-repo), mentre Pages li serve TUTTI; dirb e scalpel, per
# esempio, stanno solo online. Firma con la coppia stabile di
# build-alpine/arsenal-keys/ (la stessa .pub e' nell'overlay: la live si fida).
#
#   build-alpine/build-arsenal.sh [x86_64|aarch64]
#
# Output: out/arsenal/<arch>/  (*.apk + APKINDEX.tar.gz), da copiare in
# docs/<arch>/ sul branch main. Su aarch64 gira emulato (qemu): lento, e gcc
# puo' crollare a caso -> ritentativi come in build-in-container.sh.
set -eu
ARCH="${1:-x86_64}"
case "$ARCH" in
  x86_64)  PODMAN_ARCH=amd64 ;;
  aarch64) PODMAN_ARCH=arm64 ;;
  *) echo "architettura non gestita: $ARCH" >&2; exit 2 ;;
esac
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RT="$(command -v podman || command -v docker)"
TOOLS="${NXS_ARSENAL_TOOLS:-dmitry foremost medusa chkrootkit rkhunter bulk-extractor dirb scalpel}"
mkdir -p "$ROOT/out/arsenal"
rm -rf "$ROOT/out/arsenal/$ARCH"

# Niente apostrofi nel blocco sh -ec (chiuderebbero gli apici).
"$RT" run --rm --arch="$PODMAN_ARCH" \
  -e TOOLS="$TOOLS" -e NXS_JOBS="${NXS_JOBS:-}" \
  -v "$ROOT:/work:ro" -v "$ROOT/out/arsenal:/out" \
  docker.io/library/alpine:edge sh -ec '
  # testing: serve per alcune dipendenze di build (es. tre-dev di scalpel)
  echo https://dl-cdn.alpinelinux.org/alpine/edge/testing >> /etc/apk/repositories
  apk add --no-cache alpine-sdk sudo >/dev/null
  export TAR_OPTIONS="--no-same-owner --no-same-permissions"
  export PACKAGER="NexusSec <deplano.d@gmail.com>"
  mkdir -p /root/.abuild /etc/apk/keys
  cp /work/build-alpine/arsenal-keys/nexussecos-arsenal.rsa \
     /work/build-alpine/arsenal-keys/nexussecos-arsenal.rsa.pub /root/.abuild/
  chmod 600 /root/.abuild/nexussecos-arsenal.rsa
  cp /root/.abuild/nexussecos-arsenal.rsa.pub /etc/apk/keys/
  export REPODEST=/root/packages
  printf "PACKAGER_PRIVKEY=/root/.abuild/nexussecos-arsenal.rsa\nREPODEST=/root/packages\n" \
     > /root/.abuild/abuild.conf
  [ -n "$NXS_JOBS" ] && export JOBS="$NXS_JOBS"
  mkdir -p /root/arsenal
  mancanti=""
  for p in $TOOLS; do
    cp -a /work/aports/$p /root/arsenal/
    fatto=
    for tentativo in 1 2 3; do
      if ( cd /root/arsenal/$p && abuild -F checksum && abuild -F -r ); then
        fatto=1; break
      fi
      echo "[arsenal] $p: tentativo $tentativo fallito, riprovo..."; sleep 3
    done
    [ -n "$fatto" ] || mancanti="$mancanti $p"
  done
  arch=$(apk --print-arch)
  mkdir -p /out/$arch
  cp /root/packages/arsenal/$arch/*.apk /root/packages/arsenal/$arch/APKINDEX.tar.gz /out/$arch/
  echo "[arsenal] pronti in out/arsenal/$arch:"; ls -l /out/$arch
  if [ -n "$mancanti" ]; then echo "[arsenal] NON COMPILATI:$mancanti"; exit 1; fi
'
