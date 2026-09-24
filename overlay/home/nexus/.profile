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

# Lingua interfaccia (scelta con nxs-lang, salvata in ~/.config/nxs/lang):
# esportata QUI prima di startx cosi' pcmanfm/desktop e le app che leggono i
# file .desktop scelgono i Name[xx]/Comment[xx] della lingua giusta. I messaggi
# propri di NexusSec passano da nxs_i18n (indipendente); LANGUAGE/LANG servono
# ai .desktop e alle app di terze parti. Cambiando lingua a runtime il pannello
# si riaggiorna subito; le icone del desktop seguono al prossimo login.
_nxslang="$(cat "$HOME/.config/nxs/lang" 2>/dev/null || echo it)"
case "$_nxslang" in
  en) export LANGUAGE=en LANG=en_US.UTF-8 ;;
  fr) export LANGUAGE=fr LANG=fr_FR.UTF-8 ;;
  es) export LANGUAGE=es LANG=es_ES.UTF-8 ;;
  de) export LANGUAGE=de LANG=de_DE.UTF-8 ;;
  *)  export LANGUAGE=it LANG=it_IT.UTF-8 ;;
esac
# Menu del tasto destro di Openbox nella stessa lingua (solo se e' ancora
# quello di serie: le modifiche dell'utente non si toccano).
command -v nxs-lang >/dev/null 2>&1 && nxs-lang sync-menu >/dev/null 2>&1 || true

# Avvia la sessione grafica sulla prima console. Se X FALLISCE, NON va in loop:
# mostra l'errore di Xorg + stato driver/DRM e lascia una shell (diagnostica).
if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
  # Persistenza CIFRATA (LUKS): se presente e non ancora sbloccata, chiedi la
  # passphrase QUI (tty interattiva) prima di startx. Se assente, non fa nulla.
  command -v nxs-unlock-data >/dev/null 2>&1 && nxs-unlock-data login
  # Sessione grafica in LOOP: se al logout (uscita pulita di startx) il LOGIN
  # GRAFICO e' attivo (/etc/nxs/greeter.on), riavviamo la sessione X -> si
  # ritorna al GREETER (come un display manager), invece di cadere sulla shell.
  # Senza greeter: comportamento classico della live (shell dopo il logout).
  while :; do
    startx
    ec=$?
    [ "$ec" = "0" ] || break                 # X fallito -> diagnostica sotto
    if [ -f /etc/nxs/greeter.on ]; then
      sleep 1                                 # anti-spin, poi torna al greeter
      continue
    fi
    exec /bin/sh                              # logout senza greeter -> shell
  done
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
