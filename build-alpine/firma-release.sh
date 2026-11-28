#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
# firma-release.sh AAMMGG - firma GPG delle immagini di una release (2026-11-28).
#
# Come Kali/Parrot/Tails: si firma il file delle impronte SHA256SUMS-AAMMGG.txt
# (firma staccata, testo ASCII .asc). Chi scarica verifica PRIMA la firma
# (il file delle impronte e' davvero nostro) e POI le impronte (le immagini
# sono quelle). Chiave: "NexusSec OS Release Signing Key"
#   AFA3 88D5 E411 BE57 5422  1E12 C3C4 D5BF A5DD A9BE
# La privata sta in privato/firma/gnupg (MAI in git); la pubblica in
# docs/nexussec-release-key.asc (sito) e allegata a ogni release.
set -eu
[ $# -eq 1 ] || { echo "uso: $0 AAMMGG" >&2; exit 2; }
R="$(cd "$(dirname "$0")/.." && pwd)"
export GNUPGHOME="$R/privato/firma/gnupg"
FPR=AFA388D5E411BE5754221E12C3C4D5BFA5DDA9BE
SUMS="$R/out/SHA256SUMS-$1.txt"
[ -f "$SUMS" ] || { echo "manca $SUMS" >&2; exit 1; }
gpg --batch --yes --local-user "$FPR" --armor --detach-sign --output "$SUMS.asc" "$SUMS"
gpg --export --armor "$FPR" > "$R/out/nexussec-release-key.asc"
gpg --verify "$SUMS.asc" "$SUMS"
echo "firmato: $SUMS.asc (+ out/nexussec-release-key.asc)"
