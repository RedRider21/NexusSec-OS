#!/bin/sh
# write-usb.sh - scrive in sicurezza una ISO NexusSec su chiavetta USB e verifica
# che la copia sia identica byte-per-byte (confronto SHA256 rileggendo il device).
#
# Uso:
#   sudo ./build-alpine/write-usb.sh [ISO] [DEVICE]
#     ISO     percorso della .iso (default: la piu' recente in out/)
#     DEVICE  device a blocchi INTERO, es. /dev/sda (NON una partizione /dev/sda1)
#
# Senza DEVICE mostra i dischi RIMOVIBILI rilevati e lo chiede.
# Note importanti (imparate sul campo):
#   - si usa oflag=sync conv=fsync, NON oflag=direct (fallisce sui dispositivi UAS)
#   - la verifica svuota le cache (drop_caches) per leggere davvero dal device
set -eu

# --- root ---
if [ "$(id -u)" != 0 ]; then
  echo "Servono i privilegi di root. Rilancia con:  sudo $0 $*" >&2
  exit 1
fi

# --- risoluzione ISO ---
ISO="${1:-}"
if [ -z "$ISO" ]; then
  ISO="$(ls -1t out/alpine-nexussec-*-x86_64.iso 2>/dev/null | head -1 || true)"
  [ -n "$ISO" ] || { echo "Nessuna ISO trovata in out/. Passala come 1o argomento." >&2; exit 1; }
fi
[ -f "$ISO" ] || { echo "ISO non trovata: $ISO" >&2; exit 1; }
ISO_SIZE="$(stat -c %s "$ISO")"

# --- risoluzione DEVICE ---
DEV="${2:-}"
if [ -z "$DEV" ]; then
  echo "Dischi RIMOVIBILI rilevati:"
  # RM=1 -> rimovibile; mostra nome, dimensione, modello
  lsblk -dno NAME,SIZE,RM,MODEL 2>/dev/null | awk '$3==1{printf "  /dev/%s  %s  %s\n",$1,$2,$4}'
  echo
  printf "Device di destinazione (es. /dev/sda): "
  read -r DEV
fi

# --- controlli di sicurezza ---
[ -b "$DEV" ] || { echo "«$DEV» non e' un device a blocchi." >&2; exit 1; }
case "$DEV" in
  *[0-9]) echo "«$DEV» sembra una PARTIZIONE. Indica il disco INTERO (es. /dev/sda)." >&2; exit 1;;
esac
# non scrivere sul disco che ospita la root del sistema
ROOTSRC="$(findmnt -no SOURCE / 2>/dev/null || true)"
case "$ROOTSRC" in
  "$DEV"|"$DEV"[0-9]*) echo "RIFIUTO: «$DEV» ospita la root del sistema in uso." >&2; exit 1;;
esac
RM="$(lsblk -dno RM "$DEV" 2>/dev/null || echo 0)"
MODEL="$(lsblk -dno MODEL "$DEV" 2>/dev/null || true)"
SIZE="$(lsblk -dno SIZE "$DEV" 2>/dev/null || true)"

echo
echo "  ISO     : $ISO  ($(numfmt --to=iec "$ISO_SIZE" 2>/dev/null || echo "$ISO_SIZE byte"))"
echo "  DEVICE  : $DEV  [$MODEL $SIZE]  rimovibile=$([ "$RM" = 1 ] && echo si || echo NO)"
echo
if [ "$RM" != 1 ]; then
  echo "ATTENZIONE: $DEV NON risulta rimovibile: potrebbe essere un disco interno!"
fi
echo "TUTTI I DATI su $DEV verranno CANCELLATI."
printf "Per continuare scrivi in maiuscolo SI: "
read -r ANS
[ "$ANS" = "SI" ] || { echo "Annullato."; exit 1; }

# --- smonta eventuali partizioni montate del device ---
for P in $(lsblk -lno NAME "$DEV" 2>/dev/null | tail -n +2); do
  umount "/dev/$P" 2>/dev/null || true
done

# --- scrittura ---
echo ">> Scrittura in corso (non staccare la chiavetta)..."
dd if="$ISO" of="$DEV" bs=4M oflag=sync conv=fsync status=progress
sync

# --- verifica: rileggi ISO_SIZE byte dal device e confronta lo SHA256 ---
echo ">> Svuoto le cache e verifico..."
sync
echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
ISO_SHA="$(sha256sum "$ISO" | awk '{print $1}')"
DEV_SHA="$(head -c "$ISO_SIZE" "$DEV" | sha256sum | awk '{print $1}')"
echo "   ISO    : $ISO_SHA"
echo "   DEVICE : $DEV_SHA"
if [ "$ISO_SHA" = "$DEV_SHA" ]; then
  echo ">> OK: la chiavetta e' identica alla ISO. Avviabile."
  exit 0
else
  echo ">> ERRORE: gli hash NON coincidono. Riscrivere la chiavetta." >&2
  exit 2
fi
