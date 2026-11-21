# nxs-persist-setup.sh - funzioni condivise per la persistenza NexusSec.
# Sorgente da nexussec.start (boot) e da nxs-unlock-data (sblocco LUKS a caldo).
# NON eseguibile da solo: si fa `. /usr/local/lib/nxs-persist-setup.sh`.

# Prepara /var/nxs-data (gia' montato) per l'uso: cartelle, storage Podman
# rootless su disco, link stato/loot/cache dalla home effimera. Idempotente.
nxs_persist_setup() {
	for d in containers nxs-state loot apk-cache tool-state local; do
		install -d -o nexus -g nexus "/var/nxs-data/$d"
	done
	# Persisti ~/.local: pip/pipx e i tool 'git' installano QUI (venv + launcher
	# in ~/.local/bin, cloni in ~/.local/share). Bind mount -> sopravvivono al
	# reboot senza reinstallare nulla. Primo avvio: travaso il contenuto di
	# fabbrica dentro la cartella dati, poi il bind.
	if [ -z "$(ls -A /var/nxs-data/local 2>/dev/null)" ] && [ -n "$(ls -A /home/nexus/.local 2>/dev/null)" ]; then
		cp -a /home/nexus/.local/. /var/nxs-data/local/ 2>/dev/null || true
	fi
	install -d -o nexus -g nexus /home/nexus/.local
	mountpoint -q /home/nexus/.local 2>/dev/null || \
		mount --bind /var/nxs-data/local /home/nexus/.local 2>/dev/null || true
	chown nexus:nexus /home/nexus/.local 2>/dev/null || true
	install -d -o nexus -g nexus /home/nexus/.config/containers
	cat > /home/nexus/.config/containers/storage.conf <<STOR
[storage]
driver = "overlay"
graphroot = "/var/nxs-data/containers"
[storage.options.overlay]
mount_program = "/usr/bin/fuse-overlayfs"
STOR
	install -d -o nexus -g nexus /home/nexus/.config /home/nexus/.local/share
	rm -rf /home/nexus/.config/nxs /home/nexus/NexusSec-loot
	ln -sfn /var/nxs-data/nxs-state /home/nexus/.config/nxs
	ln -sfn /var/nxs-data/loot      /home/nexus/NexusSec-loot
	ln -sfn /var/nxs-data/apk-cache /etc/apk/cache 2>/dev/null || true
	chown -h nexus:nexus /home/nexus/.config/nxs /home/nexus/NexusSec-loot \
		/home/nexus/.config/containers/storage.conf 2>/dev/null || true
	# Reti WiFi salvate + abbinamenti Bluetooth: vedi nxs_persist_creds.
	nxs_persist_creds
	# Reinstalla i tool 'apk' registrati (vivono in /usr, cioe' in RAM): in
	# background e offline dalla cache, cosi' il desktop non aspetta.
	nxs_persist_reinstall_tools
}

# Reinstalla i pacchetti apk registrati da nxs-tool (lista su NXSDATA). I tool
# 'container/kali' e 'pip/git' persistono gia' da soli (storage Podman e
# ~/.local); qui copriamo SOLO gli apk, che altrimenti sparirebbero col reboot.
# Gira in BACKGROUND e prova PRIMA offline (cache), poi con rete: il boot non si
# blocca e funziona anche senza Internet.
nxs_persist_reinstall_tools() {
	list=/var/nxs-data/tool-state/apk-tools
	[ -f "$list" ] || return 0
	command -v apk >/dev/null 2>&1 || return 0
	(
		pkgs=""
		while IFS= read -r p; do
			[ -n "$p" ] || continue
			apk info -e "$p" >/dev/null 2>&1 && continue   # gia' presente
			pkgs="$pkgs $p"
		done < "$list"
		[ -n "$pkgs" ] || exit 0
		# offline dalla cache; se non basta, ritenta con la rete
		apk add --no-network $pkgs >/dev/null 2>&1 || apk add $pkgs >/dev/null 2>&1 || true
	) &
}

# --- Credenziali di rete: reti WiFi e abbinamenti Bluetooth ----------------
# Fa in modo che la CHIAVETTA si ricordi le reti e i telefoni abbinati: al
# riavvio non si reinserisce la password del WiFi ne si rifa il pairing.
#
#   /etc/wpa_supplicant : le reti salvate. wpa_supplicant ci scrive da solo
#       grazie a update_config=1 quando nxs-wifi fa save_config.
#   /var/lib/bluetooth  : le chiavi di accoppiamento di BlueZ, una cartella per
#       adattatore e device. Senza questa il telefono va riabbinato ogni volta.
#
# Si usa BIND MOUNT e non un symlink: bluetoothd e wpa_supplicant aprono
# percorsi assoluti e controllano i permessi della directory; un link
# simbolico verso un altro filesystem li fa inciampare.
#
# NB: questo funziona perche NXSDATA e una partizione SCRIVIBILE separata. Sul
# filesystem della ISO non si puo scrivere (e ISO9660, sola lettura), quindi
# senza NXSDATA non c e posto dove salvare.
nxs_persist_creds() {
	for coppia in "wpa:/etc/wpa_supplicant" "bluetooth:/var/lib/bluetooth"; do
		sorg="/var/nxs-data/${coppia%%:*}"
		dest="${coppia#*:}"
		install -d -m 700 "$sorg" || continue
		install -d -m 700 "$dest" || continue
		# Primo avvio: la cartella dati e vuota, quindi ci travasiamo dentro
		# quello che il sistema ha gia (conf di fabbrica, chiavi adattatore).
		if [ -z "$(ls -A "$sorg" 2>/dev/null)" ] && 		   [ -n "$(ls -A "$dest" 2>/dev/null)" ]; then
			cp -a "$dest/." "$sorg/" 2>/dev/null || true
		fi
		mountpoint -q "$dest" 2>/dev/null || 			mount --bind "$sorg" "$dest" 2>/dev/null || true
	done
	# bluetoothd puo aver gia aperto la vecchia cartella (l ordine fra il
	# servizio "local" e "bluetooth" non e garantito): riavviandolo riparte
	# dalle chiavi persistenti e i device abbinati tornano noti.
	rc-service bluetooth restart >/dev/null 2>&1 || true
}

# Cerca la partizione dati CIFRATA (LUKS2 con label NXSCRYPT). Stampa il device
# del container LUKS, vuoto se assente.
nxs_find_luks() {
	# lsblk via nxs-findlabel: il blkid di busybox ignora -t/-o (vedi l'helper)
	/usr/local/bin/nxs-findlabel NXSCRYPT crypto_LUKS 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# PERSISTENZA LEGATA AL SUPPORTO DI AVVIO (2026-11-21)
# Prima si montava QUALUNQUE disco con etichetta NXSDATA: una chiavetta altrui
# preparata con quell'etichetta, inserita all'avvio, sarebbe diventata la "tua"
# persistenza (e i programmi nel suo ~/.local sarebbero partiti col tuo utente).
# Regola: una NXSDATA IN CHIARO si monta da sola SOLO se sta sul disco da cui
# si e' avviata la live; altrove serve la persistenza CIFRATA (la passphrase e'
# la prova che e' tua). Eccezione voluta: parametro di avvio nxs_persist=any.
# ---------------------------------------------------------------------------

# Disco "padre" di un device (/dev/sda1 -> /dev/sda; un disco intero resta se
# stesso). Vuoto se non determinabile.
nxs_parent_disk() {
	_d="$(readlink -f "$1" 2>/dev/null)"; [ -b "$_d" ] || return 0
	_n="$(basename "$_d")"
	if [ -e "/sys/class/block/$_n/partition" ]; then
		echo "/dev/$(basename "$(readlink -f "/sys/class/block/$_n/..")")"
	else
		echo "$_d"
	fi
}

# Disco da cui si e' avviata la live: quello che contiene il modloop (vive
# SEMPRE sul supporto di avvio: /media/<dev>/boot/modloop-*). Su un sistema
# installato (niente modloop su /media) e' il disco della radice.
nxs_boot_disk() {
	_src=""
	for _bf in /sys/block/loop*/loop/backing_file; do
		[ -r "$_bf" ] || continue
		case "$(cat "$_bf" 2>/dev/null)" in
			*/boot/modloop-*)
				_src="$(findmnt -no SOURCE -T "$(cat "$_bf")" 2>/dev/null | head -1)"
				break ;;
		esac
	done
	[ -n "$_src" ] || _src="$(findmnt -no SOURCE / 2>/dev/null | head -1)"
	case "$_src" in /dev/*) nxs_parent_disk "$_src" ;; esac
}

# Sceglie la NXSDATA in chiaro da montare: SOLO sul disco di avvio (o ovunque
# con nxs_persist=any). Stampa il device; vuoto se non ce n'e' una ammessa.
# Se ne trova di NON ammesse, lo scrive su stderr (finisce nel log di avvio).
nxs_pick_nxsdata() {
	_boot="$(nxs_boot_disk)"
	_any=""; grep -qw "nxs_persist=any" /proc/cmdline 2>/dev/null && _any=1
	_ok=""
	for _p in $(lsblk -rpno NAME,LABEL 2>/dev/null | awk '$2=="NXSDATA"{print $1}'); do
		case "$_p" in /dev/mapper/*|/dev/loop*) continue ;; esac
		if [ -n "$_any" ] || [ "$(nxs_parent_disk "$_p")" = "$_boot" ]; then
			[ -n "$_ok" ] || _ok="$_p"
		else
			echo "persistenza: IGNORATA la NXSDATA in chiaro su $_p (non e' sulla chiavetta di avvio $_boot: per usarla altrove serve la persistenza cifrata)" >&2
			mkdir -p /run/nxs 2>/dev/null && echo "$_p" >> /run/nxs/persist-ignored 2>/dev/null
		fi
	done
	echo "$_ok"
}
