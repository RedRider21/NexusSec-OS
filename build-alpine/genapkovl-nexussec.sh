#!/bin/sh -e
# genapkovl-nexussec.sh - genera l'apkovl (overlay di configurazione) della live
# NexusSec a partire dall'albero overlay/ del repo.
#
# Usato sia da mkimage.sh (profilo nexussec) sia in standalone. La sorgente
# overlay/ e' individuata via env NXS_OVERLAY (default: ../overlay relativo a
# questo script). Output: "<hostname>.apkovl.tar.gz" nella CWD (convenzione
# mkimage) e, se NXS_OUT e' impostata, anche una copia li'.

# Hostname sempre "nexussec" (mkimage passa il nome immagine come $1: ignorato).
HOSTNAME="nexussec"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OVERLAY="${NXS_OVERLAY:-$SCRIPT_DIR/../overlay}"

cleanup() { rm -rf "$tmp"; }
tmp="$(mktemp -d)"
trap cleanup EXIT

# 1) Inietta l'intero overlay del repo (usr/local, home/nexus, etc/local.d).
cp -a "$OVERLAY"/. "$tmp"/

# 1a) CRITICO: rimuovi ogni bytecode Python (__pycache__/*.pyc). I .pyc stale
# hanno lo stesso mtime dei .py (build deterministica) e Python li usa AL POSTO
# dei .py aggiornati -> il sistema esegue codice VECCHIO (es. lo stile finestre
# non cambia). Non devono MAI finire nell'apkovl: Python li rigenera a runtime.
find "$tmp" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$tmp" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true

# 1bis) /etc/apk/world: ELENCO DEI PACCHETTI INSTALLATI AL BOOT. L'init della
# live (initramfs) installa "alpine-base" + il contenuto di world dal repo sul
# media. SENZA questo file la live monta solo alpine-base -> niente desktop,
# niente agetty (loop "can't run /sbin/agetty"). nexussec-base tira tutto lo
# stack desktop. I sec-profile-* NON vanno qui: si installano on-demand.
mkdir -p "$tmp/etc/apk"
cat > "$tmp/etc/apk/world" <<'EOF'
alpine-base
nexussec-base
EOF

# 2) Utente nexus + gruppi (in apkovl si scrivono i file, niente adduser).
mkdir -p "$tmp/etc"
cat > "$tmp/etc/passwd" <<'EOF'
root:x:0:0:root:/root:/bin/sh
nexus:x:1000:1000:NexusSec:/home/nexus:/bin/sh
EOF
# /etc/group COMPLETO (lista standard Alpine): il nostro file sovrascrive quello
# di sistema, quindi DEVE contenere tutti i gruppi standard, altrimenti spariscono
# (video/input/kvm...). nexus va aggiunto ai gruppi del desktop: wheel (doas),
# video+input (Xorg ROOTLESS: accesso a /dev/dri e /dev/input), audio, cdrom,
# dialout, netdev, kvm (podman/qemu), tty.
cat > "$tmp/etc/group" <<'EOF'
root:x:0:root
bin:x:1:root,bin,daemon
daemon:x:2:root,bin,daemon
sys:x:3:root,bin
adm:x:4:root,daemon
tty:x:5:nexus
disk:x:6:root
lp:x:7:lp
kmem:x:9:
wheel:x:10:root,nexus
floppy:x:11:root
mail:x:12:mail
news:x:13:news
uucp:x:14:uucp
cron:x:16:cron
audio:x:18:nexus
cdrom:x:19:nexus
dialout:x:20:root,nexus
ftp:x:21:
sshd:x:22:
input:x:23:nexus
tape:x:26:root
video:x:27:root,nexus
netdev:x:28:nexus
kvm:x:34:kvm,nexus
games:x:35:
shadow:x:42:
www-data:x:82:
users:x:100:games
ntp:x:123:
abuild:x:300:
utmp:x:406:
ping:x:999:
nexus:x:1000:
nogroup:x:65533:
nobody:x:65534:
EOF
cat > "$tmp/etc/shadow" <<'EOF'
root::19000:0:::::
nexus::19000:0:::::
EOF
chmod 640 "$tmp/etc/shadow"

# 3) doas: nexus (wheel) puo' elevare senza password (apk, podman, poweroff).
mkdir -p "$tmp/etc/doas.d"
echo "permit nopass :wheel" > "$tmp/etc/doas.d/doas.conf"

# 4) Autologin su tty1 -> .profile di nexus lancia startx.
cat > "$tmp/etc/inittab" <<'EOF'
::sysinit:/sbin/openrc sysinit
::sysinit:/sbin/openrc boot
::wait:/sbin/openrc default
tty1::respawn:/sbin/agetty --autologin nexus --noclear 38400 tty1 linux
tty2::respawn:/sbin/agetty 38400 tty2 linux
::ctrlaltdel:/sbin/reboot
::shutdown:/sbin/openrc shutdown
EOF

# 5) Servizi OpenRC.
# CRITICO: i servizi di base (devfs, mdev, hwdrivers, MODLOOP, modules, ...)
# NON vanno scritti a mano (facile dimenticare MODLOOP/hwdrivers -> niente
# moduli kernel -> niente DRM/grafica/rete). Creando /etc/.default_boot_services
# l'init dell'initramfs aggiunge da solo l'INTERO set standard (compresi
# modloop e hwdrivers) nei runlevel giusti (sysinit/boot/shutdown).
: > "$tmp/etc/.default_boot_services"

# Aggiungiamo SOLO i nostri extra nel runlevel default:
#   local  -> esegue /etc/local.d/*.start (repo runtime, loot, stato profili)
#   dbus   -> bus di sistema per il desktop GTK
#   udev + udev-trigger -> device manager completo (meglio di mdev per il
#            desktop; coesiste, il coldplug carica i driver mancanti)
#   networking -> rete (ifupdown-ng)
#   cgroups -> MONTA /sys/fs/cgroup. Senza questo servizio la live NON monta
#            la gerarchia unified richiesta da rc_cgroup_mode="unified" (in
#            rc.conf) e Podman ROOTLESS resta su v1 -> crun "invalid file
#            system type on /sys/fs/cgroup" -> installazione tool FALLISCE.
#            Va in coppia col kernel cmdline cgroup_no_v1=all (mkimg): il
#            kernel vieta il v1, questo servizio monta cgroup2. Gira ben prima
#            che l'utente lanci un tool dal menu del desktop.
mkdir -p "$tmp/etc/runlevels/default"
for s in local dbus udev udev-trigger networking cgroups bluetooth; do
  ln -sf "/etc/init.d/$s" "$tmp/etc/runlevels/default/$s"
done

# Splash di avvio: e' un client X (nxs-boot-splash, primo autostart Openbox),
# non un servizio OpenRC -> qui non serve nulla. Il boot testuale e' su tty12
# (console=tty12 in mkimg), cosi' tty1 resta pulito fino allo splash.
# (Plymouth valutato e SCARTATO: non aggancia il display in questo stack e fa
#  riemergere la VT col testo -> peggiora il boot pulito.)

chmod +x "$tmp/etc/local.d/nexussec.start" 2>/dev/null || true
echo "$HOSTNAME" > "$tmp/etc/hostname"

# /etc/hosts: l'hostname DEVE risolvere a 127.0.0.1, altrimenti startx/xauth
# costruiscono il display "<hostname>:0" e falliscono con
# "xauth: bad display name nexussec:0" -> X non parte (visto su VirtualBox).
cat > "$tmp/etc/hosts" <<EOF
127.0.0.1	localhost localhost.localdomain $HOSTNAME
::1		localhost localhost.localdomain $HOSTNAME
EOF

# 6) Pacchetto apkovl: STDOUT-safe e file nella CWD (convenzione mkimage).
#    Include solo le dir presenti (var c'e' se incorporiamo il repo nexussec).
OUT_FILE="$HOSTNAME.apkovl.tar.gz"
DIRS=""
for d in etc home usr root var opt; do [ -e "$tmp/$d" ] && DIRS="$DIRS $d"; done
tar -c -C "$tmp" --owner=0 --group=0 $DIRS 2>/dev/null \
  | gzip -9n > "$OUT_FILE" || \
  tar -c -C "$tmp" --owner=0 --group=0 . | gzip -9n > "$OUT_FILE"

[ -n "$NXS_OUT" ] && { mkdir -p "$NXS_OUT"; cp -f "$OUT_FILE" "$NXS_OUT/"; }
echo "[apkovl] creato: $OUT_FILE" >&2
