# mkimg.nexussec.sh - profilo immagine per Alpine mkimage.sh.
# Copiare (o linkare) questo file e genapkovl-nexussec.sh in
# aports/scripts/ e lanciare mkimage con --profile nexussec.
#
# Definisce i pacchetti dell'ISO live (== meta-pacchetto nexussec-base +
# profili) e aggancia l'apkovl generato da genapkovl-nexussec.sh.

profile_nexussec() {
	title="NexusSec OS"
	desc="Live security distro (Alpine + Openbox + profili)"
	profile_base
	# In edge il meta 'network-extras' (ereditato da profile_base) tira il
	# pacchetto legacy 'vlan' che ROMPE ifupdown-ng[!vlan]. Lo rimuoviamo: le
	# capacita' utili (WiFi, VLAN/bridge) sono in nexussec-base via
	# wpa_supplicant / iw / iproute2 / bridge.
	apks="$(echo "$apks" | sed 's/network-extras/ /g')"
	profile_abbrev="nexussec"
	image_ext="iso"
	# IMPORTANTE: settare output_format="iso" QUI. La sezione syslinux (boot
	# BIOS/El Torito) ha guardia [ "$output_format" = iso ], ma mkimage lo
	# imposta solo DOPO il giro delle sezioni. Senza questo, l'ISO esce
	# SOLO-EFI (VirtualBox/SeaBIOS: "no bootable medium"). Come mkimg.standard.
	output_format="iso"
	# Architettura parametrica (default x86_64). Su aarch64 l'ISO e' SOLO-UEFI
	# (grub-efi arm64-efi): non esiste isolinux/BIOS su ARM, quindi la sezione
	# syslinux di mkimage viene naturalmente saltata per questa arch.
	arch="${NXS_ARCH:-x86_64}"
	kernel_flavors="lts"
	kernel_addons=
	# --- Boot media detection su HARDWARE REALE (root-cause fix v2) -----------
	# ROOT CAUSE confermata leggendo il vero /init dell'initramfs:
	#   * riga "Loading boot drivers": `modprobe -a $KOPT_modules ... 2>/dev/null`
	#     con esito IGNORATO. Quindi la lista `modules=` NON e' il meccanismo che
	#     porta su i driver hardware: i driver del disco/USB/SD reali li carica
	#     comunque il COLDPLUG dentro nlplug-findfs (mdev + modalias). Gonfiare o
	#     "sfoltire" la lista non cambia quali driver partono -> era rumore.
	#   * riga "Mounting boot media": `nlplug-findfs ... -b <repo> -a <apkovls>`
	#     gira SENZA device posizionale e SENZA -t: non ha un TETTO di attesa, sta
	#     in ascolto finche' il flusso di uevent non diventa SILENZIOSO. In VM tace
	#     subito -> istantaneo. Su portatile reale (lettore SD interno che ritenta,
	#     hub USB che rienumera, ...) il flusso non tace -> 170s e, nel caso peggiore,
	#     attesa che NON finisce mai (blocco al menu "Linux lts").
	# FIX v3 (usbdelay era la regressione: -t 20000 => nlplug rinuncia a 20s e
	# cade in shell muta = "congelato su Booting Linux lts"). RIMOSSO usbdelay,
	# si torna al "trova sempre, seppur lento".
	#   * blacklist mmc/sdhci SOLO x86: il lettore SD interno VUOTO che ritenta
	#     init card e' la sorgente tipica dello storm di uevent che nega a nlplug
	#     la finestra di silenzio (i ~170s). KOPT_blacklist scrive modprobe.d
	#     NELL'INITRAMFS, scartato allo switch_root -> la SD resta usabile a
	#     sistema avviato (hwdrivers/udev). Su ARM NO: microSD = media di boot.
	#   * boot CONFERMATO OK su HW reale (chiavetta dd).
	# SPLASH VERA (fbsplash nativo Alpine): l'init dell'initramfs, se trova
	#   /media/*/fbsplash.ppm (iniettato in build-in-container.sh) e KOPT_splash
	#   != no (default attivo), lancia `setsid fbsplash -T 16 -s fbsplash.ppm`:
	#   disegna l'immagine sul framebuffer di una VT DEDICATA (tty16) e ci
	#   commuta sopra -> copre TUTTO il boot (initramfs + OpenRC), nascondendo il
	#   testo senza bisogno di console=tty12. La fbsplash NON viene chiusa a
	#   switch_root (il codice la termina solo con splash=init): resta finche' X
	#   non prende una nuova VT. Sequenza reale: immagine fbsplash (boot) ->
	#   X-splash animata identica (primo autostart Openbox) -> desktop.
	# PERCHE' NIENTE console=tty12: con fbsplash il testo e' gia' coperto da
	#   -T 16; togliere console=tty12 rende il FALLBACK SICURO -> se il
	#   framebuffer manca (nessun /dev/fb0), invece di un nero muto su una VT
	#   non visibile si vede un boot testuale 'quiet' e poi il desktop.
	#   'vt.global_cursor_default=0' toglie il cursore lampeggiante.
	# NB Ventoy resta lento a prescindere (espone molti block device: dm delle
	# ISO, exfat, VTOYEFI -> nlplug li scandisce tutti). Uso reale = chiavetta
	# SOLO-NexusSec scritta con `dd`. Diagnosi: al menu togliere 'quiet' e
	# aggiungere 'debug_init splash=no' -> si rivedono i messaggi su tty1.
	_nxs_black=
	if [ "$arch" != "aarch64" ]; then
		_nxs_black=" blacklist=sdhci,sdhci_pci,sdhci_acpi,mmc_block,mmc_core"
	fi
	initfs_cmdline="modules=loop,squashfs,sd-mod,usb-storage${_nxs_black} quiet vt.global_cursor_default=0"
	# --- cgroups v2 (unified) per Podman ROOTLESS (root-cause fix) -----------
	# Sintomo: attivando un profilo e lanciando un tool via container Kali,
	# `crun` abortiva con "invalid file system type on /sys/fs/cgroup" e Podman
	# avvisava "Using cgroups-v1 which is deprecated". Causa: la live montava
	# /sys/fs/cgroup in v1/hybrid. Su cgroups v1 il Podman ROOTLESS non ha la
	# delega dei controller -> crun non riesce a montare la gerarchia nel
	# container e l'installazione del tool FALLISCE.
	# Il solo rc_cgroup_mode="unified" in rc.conf NON basta: serve anche il
	# servizio OpenRC `cgroups` in un runlevel (aggiunto da genapkovl) E, per
	# essere deterministici a prescindere dall'ordine dei servizi, forziamo il
	# KERNEL a NON esporre affatto i controller v1: `cgroup_no_v1=all`. Cosi'
	# qualunque montaggio di /sys/fs/cgroup e' obbligatoriamente cgroup2 e i
	# container (anche rootless) partono. NB: v2-only e' pienamente supportato
	# da Podman/crun e dai container Kali.
	kernel_cmdline="${kernel_cmdline:+$kernel_cmdline }cgroup_no_v1=all"
	# Pacchetti installati nella live. nexussec-base tira tutto il desktop;
	# i sec-profile-* sono disponibili nel repo ma installati on-demand.
	apks="$apks
		alpine-base
		nexussec-base
		"
	# Repository locale con i nostri APKBUILD compilati (vedi README).
	apkovl="genapkovl-nexussec.sh"
}
