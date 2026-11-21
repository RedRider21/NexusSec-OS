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

# --- cartella del repo, indipendente dalla directory da cui si lancia ---
SCRIPT_DIR=$(cd "$(dirname "$0")" 2>/dev/null && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." 2>/dev/null && pwd)

# --- risoluzione ISO (interattiva) ---
ISO="${1:-}"
if [ -n "$ISO" ] && [ ! -f "$ISO" ]; then
  echo "ISO indicata non trovata: $ISO" >&2
  ISO=""
fi
if [ -z "$ISO" ]; then
  # cerca in: <repo>/out, ./out, . (deduplica mantenendo l'ordine per data)
  OLDIFS=$IFS; IFS='
'
  set --
  # Ordine: piu' recenti prima, ma quelle dell'architettura di QUESTO PC in
  # testa (prima x86_64 e aarch64 della stessa data comparivano in ordine
  # casuale e con INVIO si poteva scrivere quella sbagliata).
  HOSTARCH="$(uname -m)"
  LIST="$(ls -1t "$REPO_ROOT"/out/alpine-nexussec-*.iso ./out/alpine-nexussec-*.iso ./*.iso 2>/dev/null)"
  for f in $(printf '%s\n' "$LIST" | grep -- "-$HOSTARCH\.iso$"; printf '%s\n' "$LIST" | grep -v -- "-$HOSTARCH\.iso$"); do
    dup=0
    for g in "$@"; do [ "$g" = "$f" ] && dup=1 && break; done
    [ "$dup" = 0 ] && set -- "$@" "$f"
  done
  IFS=$OLDIFS
  if [ "$#" -eq 1 ]; then
    ISO="$1"
    echo "ISO trovata: $ISO"
  elif [ "$#" -gt 1 ]; then
    echo "ISO disponibili:"
    i=0
    for f in "$@"; do
      i=$((i+1))
      case "$f" in *-"$HOSTARCH".iso) nota="  <- adatta a questo PC ($HOSTARCH)" ;; *) nota="" ;; esac
      printf "  %d) %s  (%s)%s\n" "$i" "$f" "$(numfmt --to=iec "$(stat -c %s "$f")" 2>/dev/null || echo '?')" "$nota"
    done
    printf "Scegli il numero [1]: "
    read -r SEL
    [ -n "$SEL" ] || SEL=1
    case "$SEL" in
      *[!0-9]*|"") echo "Scelta non valida." >&2; exit 1;;
    esac
    [ "$SEL" -ge 1 ] && [ "$SEL" -le "$#" ] || { echo "Numero fuori intervallo." >&2; exit 1; }
    ISO=$(eval "echo \${$SEL}")
  fi
fi
# ultima spiaggia: chiedi il percorso a mano finche' non e' valido (o vuoto=annulla)
while [ -z "${ISO:-}" ] || [ ! -f "$ISO" ]; do
  echo "Nessuna ISO trovata automaticamente (cercata in $REPO_ROOT/out)."
  printf "Incolla il percorso della ISO (vuoto = annulla): "
  read -r ISO
  [ -n "$ISO" ] || { echo "Annullato."; exit 1; }
done
ISO_SIZE="$(stat -c %s "$ISO")"

# --- risoluzione DEVICE ---
DEV="${2:-}"
if [ -z "$DEV" ]; then
  echo "Dischi RIMOVIBILI / USB rilevati:"
  # RM=1 (rimovibile) OPPURE collegato via USB: molte chiavette/SSD USB hanno RM=0
  lsblk -dpno NAME,SIZE,RM,TRAN,MODEL 2>/dev/null | awk '$3==1 || $4=="usb" {m=""; for(i=5;i<=NF;i++) m=m" "$i; printf "  %s  %s %s\n",$1,$2,m}'
  echo
  printf "Device di destinazione (es. /dev/sda): "
  read -r DEV
fi

# --- controlli di sicurezza ---
[ -b "$DEV" ] || { echo "«$DEV» non e' un device a blocchi." >&2; exit 1; }
# Il TIPO lo dice lsblk (prima si guardava se il nome finiva con un numero:
# cosi' /dev/mmcblk0 e /dev/nvme0n1, dischi interi, venivano rifiutati).
if [ "$(lsblk -dno TYPE "$DEV" 2>/dev/null)" != "disk" ]; then
  echo "«$DEV» non e' un disco intero (e' una partizione o altro). Indica il disco INTERO (es. /dev/sdb)." >&2
  exit 1
fi
# non scrivere sul disco che ospita la root del sistema
# (risale anche LUKS/LVM: con root cifrata SOURCE e' /dev/mapper/..., non il disco)
DEVREAL="$(readlink -f "$DEV")"
for MP in / /boot /boot/efi /home; do
  SRC="$(findmnt -no SOURCE "$MP" 2>/dev/null || true)"
  [ -n "$SRC" ] || continue
  for D in $(lsblk -nspo NAME,TYPE "$SRC" 2>/dev/null | awk '$2=="disk"{print $1}' | sed 's/^[^/]*//'); do
    if [ "$(readlink -f "$D")" = "$DEVREAL" ]; then
      echo "RIFIUTO: «$DEV» ospita $MP del sistema in uso." >&2; exit 1
    fi
  done
done
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
