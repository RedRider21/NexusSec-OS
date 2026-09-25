#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
# prova-xephyr.sh - il desktop NexusSec in una FINESTRA (Xephyr), senza ISO.
#
# Apre Xephyr sul desktop dell'host e ci fa girare dentro la sessione NexusSec
# (Openbox, pannello, icone, menu, browser, Centro di Controllo...) da un
# container Alpine (immagine build/prova/Containerfile). Il codice arriva
# DIRETTAMENTE dalla cartella del progetto, in sola lettura: si modifica un
# file, si riavvia l'app (o "Riavvia Openbox" dal menu, o si rilancia lo
# script) e si vede subito il risultato. La ISO serve solo per il collaudo
# finale (boot, driver, servizi, rete, audio: qui NON ci sono).
#
#   build/prova-xephyr.sh              avvia (home nuova, come al primo boot)
#   build/prova-xephyr.sh --tieni      avvia conservando la home di prova
#   build/prova-xephyr.sh --stop       chiude finestra e container
#   NXS_PROVA_SIZE=1600x900 build/prova-xephyr.sh   dimensione finestra
#
# La home di prova e' una COPIA di overlay/home/nexus in una cartella
# temporanea: la sessione non scrive mai nei file del progetto.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DISP="${NXS_PROVA_DISPLAY:-:5}"
N="${DISP#:}"
SIZE="${NXS_PROVA_SIZE:-1366x768}"
CNAME=nxs-prova
IMG=localhost/nxs-prova
HOMEP="${XDG_RUNTIME_DIR:-/tmp}/nxs-prova-home"

ferma() {
  podman rm -f "$CNAME" >/dev/null 2>&1 || true
  pkill -f "Xephyr $DISP " 2>/dev/null || true
}

case "${1:-}" in
  --stop) ferma; echo "prova chiusa"; exit 0 ;;
esac

# --arch esplicita: dopo le build aarch64 il tag alpine:edge locale puo' essere
# quello ARM, e tutto girerebbe emulato (lentissimo)
ARCH="$(uname -m)"; case "$ARCH" in x86_64) PARCH=amd64 ;; aarch64) PARCH=arm64 ;; *) PARCH="$ARCH" ;; esac
if ! podman image exists "$IMG" || \
   [ "$(podman image inspect -f '{{.Architecture}}' "$IMG" 2>/dev/null)" != "$PARCH" ]; then
  podman build -q --arch "$PARCH" --pull -t "$IMG" \
    -f "$ROOT/build/prova/Containerfile" "$ROOT/build/prova"
fi

ferma
if [ "${1:-}" != "--tieni" ] || [ ! -d "$HOMEP" ]; then
  rm -rf "$HOMEP"
  mkdir -p "$HOMEP"
  cp -a "$ROOT/overlay/home/nexus/." "$HOMEP/"
  find "$HOMEP" -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
fi

Xephyr "$DISP" -screen "$SIZE" -resizeable -ac -no-host-grab \
  -title "NexusSec (prova in finestra)" >/dev/null 2>&1 &
i=0; while [ ! -S "/tmp/.X11-unix/X$N" ] && [ $i -lt 50 ]; do sleep 0.1; i=$((i+1)); done

# seccomp=unconfined: gdk-pixbuf recente carica le immagini con glycin, che le
# isola in una sandbox bwrap (namespace utente); il filtro seccomp predefinito
# di podman la blocca e pannello/icone si piantano al primo SVG. Solo per la
# prova: sulla ISO la sandbox funziona normalmente.
# /usr/local e i font dal progetto (sola lettura): modifiche visibili al volo.
# Stato del profilo in /etc/sec_os (scrivibile nel container, non nel progetto).
podman run -d --rm --name "$CNAME" --arch "$PARCH" --user 1000:1000 --userns=keep-id \
  --shm-size=512m \
  --security-opt seccomp=unconfined --security-opt label=disable \
  -e DISPLAY="$DISP" -e HOME=/home/nexus -e USER=nexus \
  -e XDG_RUNTIME_DIR=/tmp/xdg -e NO_AT_BRIDGE=1 \
  -e WEBKIT_DISABLE_COMPOSITING_MODE=1 -e PYTHONDONTWRITEBYTECODE=1 \
  -v /tmp/.X11-unix:/tmp/.X11-unix -v /etc/localtime:/etc/localtime:ro \
  -v "$ROOT/overlay/usr/local:/usr/local:ro" \
  -v "$ROOT/overlay/usr/share/fonts/nexussec:/usr/share/fonts/nexussec:ro" \
  -v "$HOMEP:/home/nexus" \
  "$IMG" sh -c '
    mkdir -p /tmp/xdg; chmod 700 /tmp/xdg
    fc-cache -f >/dev/null 2>&1
    setxkbmap it 2>/dev/null
    # le stesse variabili della live (lingua, prompt, PATH): la parte startx
    # di .profile gira solo su tty1, qui non scatta
    . /home/nexus/.profile >/dev/null 2>&1 </dev/null
    export XDG_RUNTIME_DIR=/tmp/xdg
    exec dbus-run-session -- openbox-session' >/dev/null

echo "Desktop NexusSec in prova sulla finestra Xephyr ($DISP, $SIZE)."
echo "Chiudi con: build/prova-xephyr.sh --stop"
