#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
# nxs-prune-locales.sh [ROOT] - tiene solo le traduzioni delle 5 lingue di
# NexusSec (it, en, fr, es, de) in ROOT/usr/share/locale.
#
# I pacchetti *-lang di Alpine (gtk, webkit, glib, pcmanfm, ...) contengono
# TUTTE le lingue: ~55 MB, che sulla live finirebbero in RAM (i pacchetti si
# installano in tmpfs a ogni avvio). Sfoltiti ne restano ~3 MB. Si usa sia
# all'avvio (nexussec.start) sia a build-time (fastboot-rootfs.sh).
R="${1:-}"
D="$R/usr/share/locale"
[ -d "$D" ] || exit 0
for d in "$D"/*/; do
	n="$(basename "$d")"
	case "$n" in
		it|it_*|it@*|en|en_*|en@*|fr|fr_*|fr@*|es|es_*|es@*|de|de_*|de@*) ;;
		*) rm -rf "$d" ;;
	esac
done
