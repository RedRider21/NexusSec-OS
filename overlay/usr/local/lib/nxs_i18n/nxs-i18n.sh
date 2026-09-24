# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
# nxs-i18n.sh - traduzioni per gli script shell (da sorgiare con ".").
#
#   nxs_t CHIAVE "testo italiano di riserva"
#
# Stampa il testo nella lingua attiva (~/.config/nxs/lang) usando nxs_i18n. Se
# Python o il modulo mancano, o la chiave non esiste, stampa il testo di
# riserva: lo script non si rompe mai. Per i valori variabili la chiave usa
# %s e lo script fa:  printf "$(nxs_t chiave '... %s ...')" "$valore"
nxs_t() {
  PYTHONPATH="/usr/local/lib${PYTHONPATH:+:$PYTHONPATH}" python3 -c '
import sys
try:
    from nxs_i18n import t
    s = t(sys.argv[1])
    print(sys.argv[2] if s == sys.argv[1] else s)
except Exception:
    print(sys.argv[2])' "$1" "${2:-$1}" 2>/dev/null || printf '%s\n' "${2:-$1}"
}
