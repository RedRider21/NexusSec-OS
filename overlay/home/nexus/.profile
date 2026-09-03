# NexusSec - profilo shell utente 'nexus'.
# I tool installati via pip (pipx) finiscono in ~/.local/bin: lo mettiamo nel
# PATH PRIMA di startx, cosi' lo ereditano la sessione X, il pannello e i tool
# lanciati dal menu (altrimenti i tool pip risultano "non trovati").
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) PATH="$HOME/.local/bin:$PATH"; export PATH ;;
esac

# Prompt commutabile: busybox ash legge $ENV a ogni shell interattiva. Lo
# esportiamo QUI (prima di startx) cosi' lo ereditano X, i terminali e le shell
# figlie -> il prompt scelto (nxs-prompt) vale ovunque. bash usa invece ~/.bashrc
# (che sorgia lo stesso shrc). Vedi ~/.config/nxs/shrc.
export ENV="$HOME/.config/nxs/shrc"

# XDG_RUNTIME_DIR per PipeWire/WirePlumber (la live non ha logind/elogind).
# La dir /run/user/<uid> la crea local.d (di proprieta' nexus). Lo esportiamo
# qui, PRIMA di startx, cosi' X, il pannello e i tool audio lo ereditano.
export XDG_RUNTIME_DIR="/run/user/$(id -u)"

# Avvia la sessione grafica sulla prima console. Se X FALLISCE, NON va in loop:
# mostra l'errore di Xorg + stato driver/DRM e lascia una shell (diagnostica).
if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
  # Persistenza CIFRATA (LUKS): se presente e non ancora sbloccata, chiedi la
  # passphrase QUI (tty interattiva) prima di startx. Se assente, non fa nulla.
  command -v nxs-unlock-data >/dev/null 2>&1 && nxs-unlock-data login
  startx
  ec=$?
  # X uscito pulito (logout): torna alla shell senza allarmi.
  [ "$ec" = "0" ] && exec /bin/sh
  clear
  echo "=================================================================="
  echo " NexusSec: avvio grafico (startx) FALLITO  [codice $ec]"
  echo "=================================================================="
  echo "--- Errori Xorg (/var/log/Xorg.0.log) ---------------------------"
  grep -E "\(EE\)|\(WW\)|no screens|Cannot|Fatal|Failed|modeset|vmware|vbox|fbdev|vesa" \
       /var/log/Xorg.0.log 2>/dev/null | tail -30
  echo "--- /dev/dri (KMS/DRM) ------------------------------------------"
  ls -l /dev/dri 2>/dev/null || echo "  NESSUN /dev/dri -> il modulo DRM non si e' caricato"
  echo "--- moduli DRM caricati -----------------------------------------"
  lsmod 2>/dev/null | grep -iE "drm|vmwgfx|vboxvideo|qxl|bochs" || echo "  (nessun modulo drm)"
  echo "--- driver video Xorg installati --------------------------------"
  ls /usr/lib/xorg/modules/drivers/ 2>/dev/null
  echo "=================================================================="
  echo " Riprova grafica:  startx        Spegni:  poweroff"
  echo " (manda uno screenshot di questa schermata)"
  echo "=================================================================="
  exec /bin/sh
fi
