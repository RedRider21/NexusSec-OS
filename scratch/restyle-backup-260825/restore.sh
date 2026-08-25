#!/bin/sh
# Ripristino del restyle badge (2026-08-25): riporta i file allo stato pre-restyle.
cd "$(dirname "$0")/../.." || exit 1
set -e
cp -v scratch/restyle-backup-260825/lib_nxs_cc/common.py overlay/usr/local/lib/nxs_cc/common.py
cp -v scratch/restyle-backup-260825/lib_nxs_cc/panel.py overlay/usr/local/lib/nxs_cc/panel.py
cp -v scratch/restyle-backup-260825/lib_nxs_profiles/model.py overlay/usr/local/lib/nxs_profiles/model.py
cp -v scratch/restyle-backup-260825/build/make-wallpaper.py build/make-wallpaper.py
cp -v scratch/restyle-backup-260825/backgrounds/*.png overlay/home/nexus/.themes/NexusSec-Core/backgrounds/
echo "RIPRISTINO COMPLETATO. Ricostruire l'ISO per applicare."
