#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
# collect-sources.sh - raccoglie i SORGENTI CORRISPONDENTI dei pacchetti che
# NexusSec compila e pubblica nel proprio repository apk (GitHub Pages).
#
# Perche': chi distribuisce un binario GPL deve rendere disponibile il suo
# sorgente. La ricetta (APKBUILD) e le patch stanno nel repo, ma il sorgente
# originale e' ospitato da terzi e puo' sparire: qui se ne fa una copia da
# pubblicare ACCANTO ai binari, verificata col checksum della ricetta.
#
#   build/collect-sources.sh DESTINAZIONE      es. docs/sources (branch main)
#
# Per ogni pacchetto crea DESTINAZIONE/<pkg>-<ver>-r<rel>/ con: il tarball
# originale, APKBUILD, eventuali patch e SHA512SUMS; piu' un index.html.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:?uso: build/collect-sources.sh DESTINAZIONE}"
PKGS="bulk-extractor chkrootkit dirb dmitry foremost medusa rkhunter scalpel"
mkdir -p "$DEST"

indice="$DEST/index.html"
{
  echo '<!doctype html><meta charset="utf-8"><title>NexusSec OS - sorgenti</title>'
  echo '<h1>Sorgenti dei pacchetti compilati da NexusSec OS</h1>'
  echo '<p>Sorgenti corrispondenti ai binari del repository apk di NexusSec,'
  echo 'con la ricetta di compilazione (APKBUILD) e le eventuali patch.'
  echo 'Corresponding sources for the binaries in the NexusSec apk repository.</p><ul>'
} > "$indice"

for p in $PKGS; do
  ab="$ROOT/aports/$p/APKBUILD"
  [ -f "$ab" ] || { echo "manca $ab" >&2; exit 1; }
  # variabili della ricetta in una subshell (l'APKBUILD e' shell)
  eval "$(sh -c ". '$ab' >/dev/null 2>&1; printf 'pkgver=%s\npkgrel=%s\nlicense=%s\n' \"\$pkgver\" \"\$pkgrel\" \"\$license\"")"
  dir="$DEST/$p-$pkgver-r$pkgrel"
  mkdir -p "$dir"
  cp "$ab" "$dir/APKBUILD"
  # file locali della ricetta (patch, sorgenti nostri)
  # solo i file TRACCIATI da git (niente avanzi di compilazione src/ pkg/)
  git -C "$ROOT" ls-files "aports/$p" | while read -r f; do
    case "$(basename "$f")" in APKBUILD) ;; *) cp "$ROOT/$f" "$dir/" ;; esac
  done
  # sorgenti remoti: voce "nome::url" oppure solo url
  sh -c ". '$ab' >/dev/null 2>&1; for s in \$source; do echo \"\$s\"; done" | while read -r s; do
    case "$s" in *://*) ;; *) continue ;; esac
    nome="${s%%::*}"; url="${s#*::}"
    [ "$nome" = "$s" ] && nome="$(basename "$url")"
    if [ ! -f "$dir/$nome" ]; then
      echo "[*] $p: scarico $url"
      curl -fsSL --retry 3 -o "$dir/$nome" "$url"
    fi
  done
  # verifica con gli sha512 della ricetta
  sh -c ". '$ab' >/dev/null 2>&1; printf '%s\n' \"\$sha512sums\"" | sed '/^$/d' > "$dir/SHA512SUMS"
  ( cd "$dir" && sha512sum -c SHA512SUMS >/dev/null ) \
    && echo "[ok] $p $pkgver: sorgente verificato" \
    || { echo "[!!] $p: checksum NON corrispondente" >&2; exit 1; }
  echo "<li><a href=\"$p-$pkgver-r$pkgrel/\">$p $pkgver-r$pkgrel</a> — $license</li>" >> "$indice"
done
echo '</ul>' >> "$indice"
echo "Sorgenti raccolti in $DEST"
