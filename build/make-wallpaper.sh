#!/bin/sh
# Genera gli sfondi NexusSec. Dalla v2 la grafica e' prodotta da PIL
# (build/make-wallpaper.py): stile HUD sci-fi con emblema tematico diverso per
# profilo (mirino, lente+impronta, globo, ...), honeycomb, rete di nodi e glow.
# Questo wrapper resta come entry point storico.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "$ROOT/build/make-wallpaper.py"
