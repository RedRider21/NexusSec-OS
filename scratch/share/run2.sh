#!/bin/sh
# Re-test mirato: pip (12) + bin apk corretti + wireshark.
SH=/mnt/share
OUT="$SH/results2.txt"; LOG="$SH/install2.log"
: > "$OUT"; : > "$LOG"
say() { echo "$@" | tee -a "$OUT"; }

say "=== RE-TEST  $(date) ==="
say "PATH=$PATH"
say "ls ~/.local: $(ls -ld /home/nexus/.local/state /home/nexus/.local/bin 2>&1 | awk '{print $1,$3,$9}' | tr '\n' ' ')"

probe() {
  command -v "$1" >/dev/null 2>&1 || { echo "no -"; return; }
  for fl in --version -V --help -h version; do
    timeout 8 "$1" $fl >/dev/null 2>&1 && { echo "si si"; return; }
  done
  echo "si -"
}

say ""; say "===== APK bin corretti + wireshark ====="
for tb in "bulk-extractor bulk_extractor" "clamav clamscan" "nikto nikto.pl" "sleuthkit fls" "wireshark wireshark" "tcpdump tcpdump" "tshark tshark"; do
  set -- $tb; t=$1; b=$2
  echo "#### $t ####" >>"$LOG"
  nxs-tool install "$t" >>"$LOG" 2>&1 && ins=OK || ins=FAIL
  set -- $(probe "$b")
  say "$(printf '%-16s install=%-4s PATH=%-3s exec=%s (bin=%s)' "$t" "$ins" "$1" "$2" "$b")"
done

say ""; say "===== PIP (12) ====="
ok=0; tot=0
while read t b; do
  [ -z "$t" ] && continue
  tot=$((tot+1))
  echo "######## PIP $t ($b) ########" >>"$LOG"
  if nxs-tool install "$t" >>"$LOG" 2>&1; then ins=OK; else ins=FAIL; fi
  set -- $(probe "$b"); p=$1; e=$2
  [ "$ins" = OK ] && [ "$p" = si ] && ok=$((ok+1))
  say "$(printf '%-16s install=%-4s PATH=%-3s exec=%s' "$t" "$ins" "$p" "$e")"
done < "$SH/pip_tools.txt"
say "----- PIP: $ok/$tot OK -----"
say "=== FINE2 ==="
sync
