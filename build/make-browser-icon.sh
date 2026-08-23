#!/bin/sh
# Genera l'icona di NexusSec Browser (PNG multi-size) nel tema icone NexusSec-Core.
# PNG e non SVG: su questo stack (gdk-pixbuf senza librsvg affidabile) gli SVG
# di tema spesso non si renderizzano. Stile flat Nebula: globo cyan su navy.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
THEME="$ROOT/rootfs-overlay/usr/local/share/icons/NexusSec-Core"
SIZES="16 22 24 32 48 64 128 256"

command -v convert >/dev/null 2>&1 || { echo "serve ImageMagick (convert)"; exit 1; }

TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
M=256

# Globo: disco navy con bordo cyan + meridiani/paralleli. Master 256px.
{
  echo "fill #07131f stroke #00e5ff stroke-width 9 circle $((M/2)),$((M/2)) $((M/2)),18"
  echo "fill none stroke #00e5ff stroke-width 5"
  echo "ellipse $((M/2)),$((M/2)) 46,110 0,360"
  echo "line 22,$((M/2)) 234,$((M/2))"
  echo "line 52,86 204,86"
  echo "line 52,170 204,170"
  echo "fill #aef6ff stroke none"
  echo "path 'M 150,54 L 110,140 L 134,140 L 120,202 L 168,116 L 140,116 Z'"
} > "$TMP/globe.mvg"

convert -size ${M}x${M} xc:none -draw "@$TMP/globe.mvg" "$TMP/master.png"

for s in $SIZES; do
  dir="$THEME/apps/$s"
  mkdir -p "$dir"
  convert "$TMP/master.png" -resize ${s}x${s} "$dir/nxs-browser.png"
done

# Copia anche come fallback assoluto (Icon= con path o pixmaps).
mkdir -p "$THEME/../../pixmaps" 2>/dev/null || true
cp "$THEME/apps/48/nxs-browser.png" "$ROOT/rootfs-overlay/usr/local/share/pixmaps/nxs-browser.png" 2>/dev/null || {
  mkdir -p "$ROOT/rootfs-overlay/usr/local/share/pixmaps"
  cp "$THEME/apps/48/nxs-browser.png" "$ROOT/rootfs-overlay/usr/local/share/pixmaps/nxs-browser.png"
}

echo "[icon] nxs-browser PNG generati in $THEME/apps/{$SIZES}"
