#!/bin/sh
# Harness di test tool dentro la live NexusSec. Scrive su /mnt/share.
# Usa il VERO comando utente: nxs-tool install <tool>, poi verifica
# presenza nel PATH ed esecuzione (flag versione/help con timeout).
SH=/mnt/share
OUT="$SH/results.txt"
LOG="$SH/install.log"
: > "$OUT"; : > "$LOG"

say() { echo "$@" | tee -a "$OUT"; }

say "=== NexusSec tool test  $(date) ==="
say "RAM: $(free -m 2>/dev/null | awk '/Mem:/{print $2\"MB tot, \"$7\"MB avail\"}')"
say "disco /: $(df -h / | awk 'NR==2{print $2\" tot, \"$4\" liberi (\"$5\" usato)\"}')"
say "--- rete ---"
if wget -q -T8 -O- http://dl-cdn.alpinelinux.org/alpine/edge/main/x86_64/APKINDEX.tar.gz >/dev/null 2>&1; then
  say "rete APK: OK (raggiungo dl-cdn.alpinelinux.org)"
else
  say "rete APK: FAIL (no internet?) -> i test install falliranno"
fi
say "repo configurati:"; grep -v '^#' /etc/apk/repositories 2>/dev/null | sed 's/^/    /' | tee -a "$OUT"
doas apk update >>"$LOG" 2>&1 && say "apk update: OK" || say "apk update: FAIL"

probe() {  # $1=bin -> stampa PATH e VER
  if ! command -v "$1" >/dev/null 2>&1; then echo "no -"; return; fi
  for fl in --version -V --help -h version; do
    if timeout 8 "$1" $fl >/dev/null 2>&1; then echo "si si"; return; fi
  done
  echo "si -"   # nel PATH ma nessun flag standard ha risposto 0
}

run_group() {  # $1=label  $2=listfile
  say ""; say "===== $1 ====="
  say "$(printf '%-16s %-9s %-7s %-7s' TOOL INSTALL PATH ESEGUE)"
  ok=0; tot=0
  while read t b; do
    [ -z "$t" ] && continue
    tot=$((tot+1))
    echo "######## $t ($b) ########" >> "$LOG"
    if nxs-tool install "$t" >>"$LOG" 2>&1; then ins=OK; else ins=FAIL; fi
    set -- $(probe "$b"); pth=$1; ver=$2
    [ "$ins" = OK ] && [ "$pth" = si ] && ok=$((ok+1))
    say "$(printf '%-16s %-9s %-7s %-7s' "$t" "$ins" "$pth" "$ver")"
    say "  spazio: $(df -h / | awk 'NR==2{print $4\" liberi\"}')"
  done < "$2"
  say "----- $1: $ok/$tot install+PATH OK -----"
}

run_group "APK (38)" "$SH/apk_tools.txt"

# PIP: pipx puo' essere lento/assente; timeout per-tool gestito da nxs-tool.
if command -v pipx >/dev/null 2>&1 || command -v pip3 >/dev/null 2>&1; then
  run_group "PIP (12)" "$SH/pip_tools.txt"
else
  say ""; say "===== PIP ====="; say "pipx/pip assenti: installo pipx..."
  doas apk add pipx >>"$LOG" 2>&1 && run_group "PIP (12)" "$SH/pip_tools.txt" || say "pipx non installabile"
fi

# CONTAINER: solo verifica meccanismo (no pull di massa: RAM/tmpfs). Provo 1 pull leggero.
say ""; say "===== CONTAINER (meccanismo) ====="
if command -v podman >/dev/null 2>&1; then
  say "podman: presente"
  T=$(head -1 "$SH/container_tools.txt" | awk '{print $1}')
  I=$(head -1 "$SH/container_tools.txt" | awk '{print $2}')
  say "pull di prova: $T ($I)"
  if timeout 180 nxs-tool install "$T" >>"$LOG" 2>&1; then say "  pull $T: OK"; else say "  pull $T: FAIL/timeout (vedi install.log)"; fi
  say "  (gli altri container non pullati: tmpfs 4GB)"
else
  say "podman: ASSENTE (apk add podman)"
fi

say ""; say "RAM finale: $(free -m 2>/dev/null | awk '/Mem:/{print $7\"MB avail\"}')"
say "=== FINE ==="
sync
