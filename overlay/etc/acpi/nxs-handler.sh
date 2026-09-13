#!/bin/sh
# nxs-handler.sh - gestione eventi ACPI (chiamato da acpid, come root).
#
# La live non ha logind: qui gestiamo gli eventi hardware "a mano".
#   - chiusura coperchio -> blocca lo schermo della sessione X dell'utente;
#   - tasto di accensione -> spegnimento PULITO (nxs-shutdown fa lbu commit).
#
# acpid gira da root: per agire sulla sessione grafica dell'utente 'nexus'
# eseguiamo il comando come lui, con DISPLAY/XAUTHORITY della sessione startx.
KIND="${1:-}"; shift 2>/dev/null || true
EVENT="$*"

U=nexus
run_x() {  # esegue "$@" nella sessione X dell'utente
  su "$U" -c "DISPLAY=:0 XAUTHORITY=/home/$U/.Xauthority $*" 2>/dev/null || true
}

case "$KIND" in
  lid)
    # blocca solo alla CHIUSURA (non alla riapertura)
    case "$EVENT" in
      *close*) run_x nxs-screensaver ;;
    esac
    ;;
  power)
    # spegnimento pulito; se nxs-shutdown non c'e', poweroff diretto
    if command -v nxs-shutdown >/dev/null 2>&1; then
      run_x nxs-shutdown poweroff || poweroff
    else
      poweroff
    fi
    ;;
esac
exit 0
