#!/usr/bin/env python3
"""Patcha l'init dell'initramfs Alpine (mkinitfs) per il boot NexusSec "fast":
se sul media c'e' nxs-rootfs.squashfs, monta il ROOT gia' pronto come
squashfs (ro) + overlay tmpfs e SALTA l'installazione pacchetti in RAM
(i ~30s). Altrimenti si comporta come l'init standard.

Tre modifiche mirate, replicando lo schema overlaytmpfs gia' presente in Alpine
(mountpoint /media/root-ro e /media/root-rw + creazione dentro $sysroot, cosi'
il loop finale "move mounts" li sposta correttamente prima di switch_root).

Uso:  python3 fastboot-init-patch.py /usr/share/mkinitfs/initramfs-init
"""
import sys

path = sys.argv[1]
s = open(path).read()


def repl(old, new, why):
    n = s.count(old)
    if n != 1:
        print(f"PATCH FAIL ({why}): trovato {n} volte, atteso 1:\n  {old!r}")
        sys.exit(1)
    return s.replace(old, new)


# --- 1) sysroot: overlay(squashfs ro + tmpfs) se c'e' nxs-rootfs.squashfs ------
old1 = '$MOCK mount -t tmpfs -o "$rootflags" tmpfs "$sysroot"'
new1 = '''# NexusSec SPLASH VERA (2026-11-22): appena il supporto e' montato, se c'e'
# un framebuffer (/dev/fb0: UEFI/GOP via simpledrm) e l'immagine fbsplash.ppm,
# la mostriamo SUBITO su una VT dedicata (16, modo grafico: il testo non la
# copre), PRIMA della copia in RAM. Senza framebuffer NON si fa nulla: l'avvio
# resta testuale ESATTAMENTE come prima (mai schermo nero). splash=no la
# disattiva. Resta a schermo finche' X non prende la sua VT.
NXS_SPLASH=
if [ -e /dev/fb0 ] && ! grep -qw "splash=no" /proc/cmdline; then
	for _nxsi in "$ROOT"/media/*/fbsplash.ppm; do
		[ -f "$_nxsi" ] || continue
		echo "IMG_ALIGN=CM" > /tmp/nxs-fbsplash.cfg
		setsid fbsplash -T 16 -s "$_nxsi" -i /tmp/nxs-fbsplash.cfg >/dev/null 2>&1 &
		NXS_SPLASH=1
		break
	done
fi
# NexusSec fast-boot: root GIA' pronto in squashfs -> overlay ro+tmpfs
NXS_PREBUILT=
for _nxsf in "$ROOT"/media/*/nxs-rootfs.squashfs; do
	[ -f "$_nxsf" ] && NXS_PREBUILT="$_nxsf" && break
done
# Copia IN RAM del solo squashfs (compresso, ~310 MB): poi nessuna lettura
# dalla chiavetta durante l'uso e i file si scompattano al volo dalla RAM.
# Automatica con >= 4 GB (MemTotal >= ~3,5 GB); parametro di avvio
# nxs_toram=yes|no per forzare. Se la copia non riesce si usa la chiavetta.
if [ -n "$NXS_PREBUILT" ]; then
	# 2026-11-23: di default NIENTE copia qui (rallentava l'avvio da chiavetta):
	# la fa nxs-toram IN SOTTOFONDO a desktop avviato. nxs_toram=yes la forza
	# qui come prima.
	_nxs_ram=no
	case " $(cat /proc/cmdline) " in
		*" nxs_toram=yes "*|*" nxs_toram=1 "*) _nxs_ram=yes ;;
		*" nxs_toram=no "*|*" nxs_toram=0 "*) _nxs_ram=no ;;
	esac
	_nxs_mem=$(awk '/^MemTotal:/{print $2}' /proc/meminfo)
	if [ "$_nxs_ram" = yes ] || { [ "$_nxs_ram" = auto ] && [ "${_nxs_mem:-0}" -ge 3500000 ]; }; then
		_nxs_kb=$(( $(wc -c < "$NXS_PREBUILT") / 1024 + 16384 ))
		mkdir -p /media/nxs-ram
		ebegin "NexusSec: copio il sistema in RAM ($((_nxs_kb / 1024)) MB)"
		if $MOCK mount -t tmpfs -o size=${_nxs_kb}k,mode=0755 nxs-ram /media/nxs-ram \
		   && cp "$NXS_PREBUILT" /media/nxs-ram/nxs-rootfs.squashfs; then
			NXS_PREBUILT=/media/nxs-ram/nxs-rootfs.squashfs
			eend 0
		else
			$MOCK umount /media/nxs-ram 2>/dev/null
			eend 1 "copia in RAM non riuscita: uso la chiavetta"
		fi
	fi
fi
if [ -n "$NXS_PREBUILT" ]; then
	ebegin "NexusSec: monto il root pre-costruito (squashfs + overlay)"
	$MOCK modprobe -q squashfs 2>/dev/null
	$MOCK modprobe -q loop 2>/dev/null
	$MOCK modprobe -q overlay 2>/dev/null
	mkdir -p /media/root-ro /media/root-rw "$sysroot"/media/root-ro "$sysroot"/media/root-rw
	$MOCK mount -t squashfs -o ro,loop "$NXS_PREBUILT" /media/root-ro
	$MOCK mount -t tmpfs -o mode=0755,rw root-tmpfs /media/root-rw
	mkdir -p /media/root-rw/work /media/root-rw/root
	$MOCK mount -t overlay -o lowerdir=/media/root-ro,upperdir=/media/root-rw/root,workdir=/media/root-rw/work overlayfs "$sysroot"
	eend $?
else
	$MOCK mount -t tmpfs -o "$rootflags" tmpfs "$sysroot"
fi'''
s = repl(old1, new1, "sysroot overlay")

# --- 1b) splash di Alpine: NON una seconda volta, e mai senza framebuffer --
#   (lo start di Alpine non controlla /dev/fb0: senza framebuffer resterebbe
#   una VT vuota = schermo nero). Se la condizione e' falsa Alpine mette
#   KOPT_splash=no e non scrive piu' nella fifo (che non esisterebbe).
old1b = '''if [ -n "$fbsplash" ] && [ -e "$fbsplash" ]; then
	ebegin "Starting bootsplash"'''
new1b = '''if [ -z "$NXS_SPLASH" ] && [ -e /dev/fb0 ] && [ -n "$fbsplash" ] && [ -e "$fbsplash" ]; then
	ebegin "Starting bootsplash"'''
s = repl(old1b, new1b, "splash Alpine con controllo framebuffer")

# --- 2) NON scompattare l'apkovl sul root pre-costruito (il suo apk --initdb
#        svuoterebbe il db pacchetti dell'overlay) ------------------------------
old2 = '''# load apkovl or set up a minimal system
if [ -f "$ovl" ]; then'''
new2 = '''# load apkovl or set up a minimal system
if [ -z "$NXS_PREBUILT" ] && [ -f "$ovl" ]; then'''
s = repl(old2, new2, "skip apkovl unpack")

# --- 3) salta l'installazione pacchetti in RAM sul root pre-costruito ----------
old3 = 'mkdir -p "$sysroot"/sys "$sysroot"/proc "$sysroot"/dev'
new3 = 'if [ -z "$NXS_PREBUILT" ]; then\nmkdir -p "$sysroot"/sys "$sysroot"/proc "$sysroot"/dev'
s = repl(old3, new3, "wrap install (start)")

old4 = '''$MOCK umount "$sysroot"/sys "$sysroot"/proc "$sysroot"/dev
eend 0'''
new4 = '''$MOCK umount "$sysroot"/sys "$sysroot"/proc "$sysroot"/dev
eend 0
fi'''
s = repl(old4, new4, "wrap install (end)")

open(path, "w").write(s)
print("[fastboot] init patchato:", path)
