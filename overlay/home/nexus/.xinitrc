#!/bin/sh
# NexusSec - avvio sessione X (Alpine + startx).
# Layout tastiera italiano, poi sessione Openbox.
setxkbmap it 2>/dev/null || true
# Avvia un D-Bus di SESSIONE per tutta la sessione desktop: serve ai servizi
# "session" come obexd (invio/ricezione file Bluetooth via OBEX), che altrimenti
# non si attivano. dbus-run-session esporta DBUS_SESSION_BUS_ADDRESS a Openbox e
# a tutti i figli (pannello, app). Fallback: se non disponibile, avvio diretto.
if command -v dbus-run-session >/dev/null 2>&1; then
  exec dbus-run-session -- openbox-session
fi
exec openbox-session
