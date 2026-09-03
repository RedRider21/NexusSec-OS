# mkimg.nexussec-rpi.sh - profilo immagine NexusSec per Raspberry Pi (SBC).
#
# Copiare in aports/scripts/ insieme a genapkovl-nexussec.sh e lanciare
# mkimage con --profile nexussec-rpi. Produce un tar.gz "diskless" (stile
# Alpine RPi): va estratto sulla partizione FAT32 di boot della microSD.
# build-sd-rpi.sh lo impacchetta poi in un'immagine .img.gz flashabile con dd.
#
# PERCHE' un profilo separato dalla ISO: gli SBC (Raspberry Pi 4/5) NON fanno
# boot da ISO UEFI. Il RPi ha un boot proprietario in due stadi (GPU legge la
# FAT32: bootcode/start*.elf -> kernel). Alpine lo copre col profilo 'rpi'
# (kernel 'linux-rpi' + raspberrypi-bootloader + config.txt/cmdline.txt).
# Qui ci innestiamo sopra i pacchetti e l'apkovl di NexusSec.

profile_nexussec_rpi() {
	# Eredita TUTTO il boot Raspberry Pi da Alpine: kernel_flavors="rpi",
	# raspberrypi-bootloader (firmware GPU), config.txt/cmdline.txt, dtbs,
	# initfs_features per mmc/usb e output_format tar.gz. Copre RPi 3/4/5 a
	# 64 bit (firmware di edge include gli start*.elf del Pi5).
	profile_rpi

	title="NexusSec OS (Raspberry Pi)"
	desc="Live security distro NexusSec per SBC ARM (Raspberry Pi 4/5)"
	profile_abbrev="nexussec-rpi"
	image_name="nexussec-rpi"

	# Solo 64-bit: i nostri container/tool presuppongono aarch64. Niente armhf/v7.
	arch="aarch64"
	kernel_flavors="rpi"

	# Pacchetti NexusSec: STESSA lista della ISO (vedi mkimg.nexussec.sh).
	# nexussec-base tira desktop Openbox + pannello + profili; i sei forensics
	# finiscono nel repo sul media per funzionare offline.
	apks="$apks
		alpine-base
		nexussec-base
		sleuthkit
		testdisk
		ddrescue
		libewf
		binwalk
		exiftool
		"
	# Vedi nota in mkimg.nexussec.sh: 'network-extras' tira 'vlan' che rompe
	# ifupdown-ng[!vlan]; lo togliamo qui come nella ISO.
	apks="$(echo "$apks" | sed 's/network-extras/ /g')"

	# Il nostro apkovl (overlay NexusSec + servizi OpenRC + cgroups v2 per
	# Podman) al posto di quello dhcp del profilo rpi. genapkovl-nexussec.sh e'
	# arch-agnostico (imposta servizi e sovrappone /work/overlay).
	apkovl="genapkovl-nexussec.sh"
	hostname="nexussec"
}
