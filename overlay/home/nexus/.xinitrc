#!/bin/sh
# NexusSec - avvio sessione X (Alpine + startx).
# Layout tastiera italiano, poi sessione Openbox.
setxkbmap it 2>/dev/null || true

# RIENTRO DOPO IL LOGOUT: il login grafico va mostrato PRIMA del desktop, come
# fa un display manager vero. Prima partiva tutta la sessione (pannello, icone,
# Openbox) e il login le veniva messo sopra: per un attimo si rivedeva il desktop
# completo e il login sembrava una finestra finta. Ora qui c'e' solo X nudo:
# sfondo del profilo sulla finestra radice (niente nero), poi nxs-greeter; il
# desktop si costruisce solo dopo la password giusta. Il flag lo crea .profile
# al logout e lo rimuove l'autostart (che cosi' salta splash/benvenuto/selettore).
RELOGIN_FLAG="${XDG_RUNTIME_DIR:-/tmp}/nxs-relogin"
if [ -f "$RELOGIN_FLAG" ] && command -v nxs-greeter >/dev/null 2>&1; then
  sfondo="$(python3 -c 'import sys; sys.path.insert(0, "/usr/local/lib")
from nxs_profiles import model; print(model.wallpaper_path())' 2>/dev/null)"
  [ -f "$sfondo" ] && command -v feh >/dev/null 2>&1 && \
    feh --no-fehbg --bg-fill "$sfondo" 2>/dev/null
  nxs-greeter
  rc=$?
  # 3 = scelto Riavvia/Spegni: il sistema si sta fermando, non aprire il desktop.
  if [ "$rc" = "3" ]; then
    sleep 60
    exit 0
  fi
  # 0 = accesso riuscito. Qualsiasi altro codice (greeter guasto) -> si apre
  # comunque la sessione: meglio che restare chiusi fuori dal proprio sistema.
fi

# Avvia un D-Bus di SESSIONE per tutta la sessione desktop: serve ai servizi
# "session" come obexd (invio/ricezione file Bluetooth via OBEX), che altrimenti
# non si attivano. dbus-run-session esporta DBUS_SESSION_BUS_ADDRESS a Openbox e
# a tutti i figli (pannello, app). Fallback: se non disponibile, avvio diretto.
if command -v dbus-run-session >/dev/null 2>&1; then
  exec dbus-run-session -- openbox-session
fi
exec openbox-session
