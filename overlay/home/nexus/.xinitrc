#!/bin/sh
# NexusSec - avvio sessione X (Alpine + startx).
# Layout tastiera italiano, poi sessione Openbox.
setxkbmap it 2>/dev/null || true
exec openbox-session
