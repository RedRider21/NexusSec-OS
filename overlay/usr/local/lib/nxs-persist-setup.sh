# nxs-persist-setup.sh - funzioni condivise per la persistenza NexusSec.
# Sorgente da nexussec.start (boot) e da nxs-unlock-data (sblocco LUKS a caldo).
# NON eseguibile da solo: si fa `. /usr/local/lib/nxs-persist-setup.sh`.

# Prepara /var/nxs-data (gia' montato) per l'uso: cartelle, storage Podman
# rootless su disco, link stato/loot/cache dalla home effimera. Idempotente.
nxs_persist_setup() {
	for d in containers nxs-state loot apk-cache; do
		install -d -o nexus -g nexus "/var/nxs-data/$d"
	done
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
}

# Cerca la partizione dati CIFRATA (LUKS2 con label NXSCRYPT). Stampa il device
# del container LUKS, vuoto se assente.
nxs_find_luks() {
	blkid -t TYPE=crypto_LUKS 2>/dev/null | while IFS=: read -r dev _rest; do
		lbl="$(blkid -o value -s LABEL "$dev" 2>/dev/null)"
		[ "$lbl" = "NXSCRYPT" ] && { echo "$dev"; break; }
	done
}
