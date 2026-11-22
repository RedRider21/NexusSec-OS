#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""collaudo-iso.py - collaudo AUTOMATICO di una ISO NexusSec in QEMU, prima di
ogni release. Nessun download: usa solo qemu, OVMF/AAVMF e socat del PC.

Perche' (2026-11-21): quasi tutti i difetti trovati quel giorno (doas rotto dai
permessi, blkid di busybox, persistenza impossibile sulla chiavetta, GRUB ARM
fermo al prompt) erano INVISIBILI senza avviare davvero la ISO.

Prove (ognuna con esito OK/KO):
  bios        avvio x86_64 in BIOS fino al desktop (terminale funzionante)
  uefi        avvio x86_64 in UEFI (OVMF) fino al desktop
  doas        doas funziona (comandi da amministratore)
  persist     da chiavetta USB virtuale: crea la persistenza dopo la distro,
              scrive un file, RIAVVIA, la ritrova montata e il file c'e'
  estranea    una seconda chiavetta con NXSDATA in chiaro viene IGNORATA
  arm         (solo con --arm) avvio aarch64 in UEFI (AAVMF), lento: ~15 min

Come legge i risultati: la live, dal suo terminale, scrive le righe di esito
su un piccolo disco virtuale "risultati" (/dev/disk con etichetta NXSTEST);
lo script lo rilegge dal PC. Niente interpretazione di schermate.
Le schermate restano comunque salvate per controllo a vista.

Uso:
  build-alpine/collaudo-iso.py out/alpine-nexussec-AAMMGG-x86_64.iso [--arm ISO_ARM]
                                [--solo bios,uefi,...] [--dir CARTELLA]
Esce 0 se tutte le prove sono OK.
"""
import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

# La live ha la tastiera ITALIANA, QEMU invia scancode US: mappatura dei
# caratteri che servono (verificata a mano il 2026-11-21).
_TASTI = {" ": "spc", "/": "shift-7", "-": "slash", ".": "dot", ";": "shift-comma",
          "_": "shift-slash", "|": "shift-grave_accent", ">": "shift-less",
          "=": "shift-0", "$": "shift-4", "&": "shift-6", ",": "comma",
          ":": "shift-dot", "'": "minus", "(": "shift-8", ")": "shift-9",
          "\n": "ret"}

OVMF_CODE = "/usr/share/OVMF/OVMF_CODE_4M.fd"
OVMF_VARS = "/usr/share/OVMF/OVMF_VARS_4M.fd"
AAVMF_CODE = "/usr/share/AAVMF/AAVMF_CODE.fd"
AAVMF_VARS = "/usr/share/AAVMF/AAVMF_VARS.fd"

ATTESA_BOOT = 150      # secondi fino al desktop (x86, KVM)
ATTESA_ARM = 600       # aarch64 emulata


class VM:
    """Una macchina QEMU pilotata dal monitor (socket UNIX corto)."""

    def __init__(self, nome, argv, cartella):
        self.nome = nome
        self.dir = cartella
        self.mon = "/run/user/%d/nxsck-%s.mon" % (os.getuid(), nome)
        if not os.path.isdir(os.path.dirname(self.mon)):
            self.mon = "/tmp/nxsck-%s-%d.mon" % (nome, os.getpid())
        if os.path.exists(self.mon):
            os.remove(self.mon)
        self.p = subprocess.Popen(argv + ["-display", "none", "-monitor",
                                          "unix:%s,server,nowait" % self.mon],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def cmd(self, c):
        for _ in range(30):
            try:
                s = socket.socket(socket.AF_UNIX)
                s.connect(self.mon)
                break
            except OSError:
                time.sleep(1)
        else:
            return
        time.sleep(0.2)
        try:
            s.recv(4096)
        except OSError:
            pass
        s.send((c + "\n").encode())
        time.sleep(0.3)
        s.close()

    def scrivi(self, testo, pausa=0.06):
        s = socket.socket(socket.AF_UNIX)
        s.connect(self.mon)
        time.sleep(0.2)
        s.recv(4096)
        for ch in testo:
            k = _TASTI.get(ch) or (("shift-" + ch.lower()) if ch.isupper() else ch)
            s.send(("sendkey %s\n" % k).encode())
            time.sleep(pausa)
        time.sleep(0.5)
        s.close()

    def schermata(self, etichetta):
        self.cmd("screendump %s" % os.path.join(self.dir, "%s-%s.ppm" % (self.nome, etichetta)))

    def terminale(self, attesa=6):
        self.cmd("sendkey meta_l-t")
        time.sleep(attesa)

    def chiudi(self):
        self.cmd("quit")
        try:
            self.p.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.p.kill()


def _disco_risultati(cartella, nome):
    """Disco da 4 MB con filesystem ext2 etichettato NXSTEST (via mke2fs del PC)."""
    p = os.path.join(cartella, "risultati-%s.img" % nome)
    with open(p, "wb") as f:
        f.truncate(4 * 1024 * 1024)
    subprocess.run(["mke2fs", "-q", "-F", "-t", "ext2", "-L", "NXSTEST", p], check=True)
    return p


def _leggi_risultati(img):
    """Legge il file esito.txt dal disco risultati (debugfs, niente mount/root)."""
    r = subprocess.run(["debugfs", "-R", "cat /esito.txt", img],
                       capture_output=True, text=True)
    return r.stdout


# Comando che la live esegue per scrivere gli esiti sul disco NXSTEST. Tutto con
# caratteri della mappa _TASTI. `nxs-findlabel` trova il disco senza indovinare
# il nome (sdb/sdc...).
def _cmd_esito(righe_shell):
    return ("clear; D=$(nxs-findlabel NXSTEST); doas mkdir -p /mnt/t; "
            "doas mount -t ext2 $D /mnt/t; ( %s ) | doas tee /mnt/t/esito.txt; "
            "doas umount /mnt/t\n" % righe_shell)


# Misure (2026-11-22, confronto fast-boot): secondi dall'accensione all'avvio
# del pannello (= desktop pronto; campo 22 di /proc/PID/stat, in centesimi di
# secondo) e memoria (free -m) a desktop pronto.
_CONTROLLI_BASE = ("echo DESKTOP-OK; doas true && echo DOAS-OK || echo DOAS-KO; "
                   "nxs-persist status; P=$(pgrep -f nxs_cc.panel | head -1); "
                   "echo PANNELLO-CS $(cut -d' ' -f22 /proc/$P/stat); free -m; "
                   "grep -c nxs-ram /proc/mounts | sed 's/^/RAMCOPY /'")


def _qemu_x86(iso_o_disco, uefi, cartella, nome, dischi=(), usb_boot=False):
    a = ["qemu-system-x86_64", "-enable-kvm", "-m", "4096", "-smp", "2", "-vga", "std",
         "-nic", "user,model=virtio-net-pci", "-device", "qemu-xhci"]
    if uefi:
        vars_ = os.path.join(cartella, "%s.vars" % nome)
        shutil.copy(OVMF_VARS, vars_)
        a += ["-drive", "if=pflash,format=raw,readonly=on,file=%s" % OVMF_CODE,
              "-drive", "if=pflash,format=raw,file=%s" % vars_]
    if usb_boot:
        a += ["-drive", "if=none,id=boot,format=raw,file=%s" % iso_o_disco,
              "-device", "usb-storage,drive=boot,removable=on,bootindex=0"]
    else:
        a += ["-cdrom", iso_o_disco, "-boot", "d"]
    for i, d in enumerate(dischi):
        a += ["-drive", "if=none,id=d%d,format=raw,file=%s" % (i, d),
              "-device", "usb-storage,drive=d%d,removable=on" % i]
    return a


def prova_avvio(iso, uefi, cartella):
    nome = "uefi" if uefi else "bios"
    ris = _disco_risultati(cartella, nome)
    vm = VM(nome, _qemu_x86(iso, uefi, cartella, nome, dischi=[ris]), cartella)
    time.sleep(ATTESA_BOOT)
    vm.schermata("desktop")
    vm.terminale()
    vm.scrivi(_cmd_esito(_CONTROLLI_BASE))
    time.sleep(6)
    vm.schermata("esito")
    vm.chiudi()
    out = _leggi_risultati(ris)
    esiti = {nome: "DESKTOP-OK" in out, "doas": "DOAS-OK" in out}
    for riga in out.splitlines():
        if riga.startswith("PANNELLO-CS"):
            try:
                print("  [%s] desktop pronto dopo %.0f s dall'accensione"
                      % (nome, int(riga.split()[1]) / 100.0))
            except (IndexError, ValueError):
                pass
        if riga.startswith("Mem:"):
            c = riga.split()
            print("  [%s] RAM: totale %s MB, usata %s MB, disponibile %s MB"
                  % (nome, c[1], c[2], c[-1]))
    return esiti, out


def prova_persistenza(iso, cartella):
    """Chiavetta USB virtuale da 8 GB con la ISO + chiavetta estranea NXSDATA."""
    chiavetta = os.path.join(cartella, "chiavetta.img")
    shutil.copyfile(iso, chiavetta)
    with open(chiavetta, "r+b") as f:
        f.truncate(8 * 1024 ** 3)
    estranea = os.path.join(cartella, "estranea.img")
    with open(estranea, "wb") as f:
        f.truncate(256 * 1024 ** 2)
    subprocess.run(["mkfs.ext4", "-q", "-F", "-L", "NXSDATA", estranea], check=True)
    ris = _disco_risultati(cartella, "persist")
    argv = _qemu_x86(chiavetta, False, cartella, "persist", dischi=[estranea, ris],
                     usb_boot=True)
    vm = VM("persist", argv, cartella)
    time.sleep(ATTESA_BOOT)
    vm.terminale()
    # risposte: [1] spazio dopo la distro, 1G, conferma, niente LUKS
    vm.scrivi("clear; nxs-persist\n")
    time.sleep(7)
    vm.schermata("menu")
    for r in ("1\n", "1G\n", "\n", "n\n"):
        vm.scrivi(r)
        time.sleep(4 if r != "n\n" else 20)
    vm.schermata("creata")
    vm.scrivi("echo prova-collaudo > /var/nxs-data/loot/prova.txt; sync\n")
    time.sleep(3)
    vm.cmd("system_reset")
    time.sleep(ATTESA_BOOT)
    vm.terminale()
    vm.scrivi(_cmd_esito(
        "nxs-persist status; mountpoint -q /var/nxs-data && echo PERSIST-MONTATA; "
        "cat /var/nxs-data/loot/prova.txt; "
        "test -s /run/nxs/persist-ignored && echo ESTRANEA-IGNORATA; "
        "findmnt -rno SOURCE /var/nxs-data"))
    time.sleep(6)
    vm.schermata("riavvio")
    vm.chiudi()
    out = _leggi_risultati(ris)
    esiti = {"persist": "PERSIST-MONTATA" in out and "prova-collaudo" in out,
             "estranea": "ESTRANEA-IGNORATA" in out}
    return esiti, out


def prova_installa(iso, cartella):
    """Installazione su disco (2026-11-22): la live installa con setup-disk -m sys
    su un disco virtuale da 8 GB, SENZA RETE (deve bastare la chiavetta), poi si
    controlla dalla live cosa c'e' sul disco e infine si riavvia DAL DISCO."""
    disco = os.path.join(cartella, "disco-install.img")
    with open(disco, "wb") as f:
        f.truncate(8 * 1024 ** 3)
    ris = _disco_risultati(cartella, "installa")
    argv = _qemu_x86(iso, False, cartella, "installa", dischi=[ris])
    argv = [x for x in argv if x not in ("-nic", "user,model=virtio-net-pci")]
    argv += ["-nic", "none", "-drive", "if=virtio,format=raw,file=%s" % disco]
    vm = VM("installa", argv, cartella)
    time.sleep(ATTESA_BOOT)
    vm.terminale()
    t0 = time.time()
    vm.scrivi("clear; doas sh -c 'ERASE_DISKS=/dev/vda setup-disk -m sys /dev/vda "
              ">/tmp/inst.log 2>&1 && echo INST-OK >>/tmp/inst.log "
              "|| echo INST-KO >>/tmp/inst.log'; echo FATTO\n")
    time.sleep(420)
    vm.schermata("dopo-install")
    vm.scrivi(_cmd_esito(
        "tail -12 /tmp/inst.log; lsblk -o NAME,SIZE,FSTYPE /dev/vda; "
        "doas mkdir -p /mnt/i; doas mount -t ext4 /dev/vda3 /mnt/i; "
        "doas test -f /mnt/i/usr/local/bin/nxs-install && echo NXS-PRESENTE "
        "|| echo NXS-ASSENTE; doas test -d /mnt/i/usr/local/lib/nxs_cc "
        "&& echo PANNELLO-PRESENTE || echo PANNELLO-ASSENTE; "
        "doas test -d /mnt/i/home/nexus && echo HOME-PRESENTE || echo HOME-ASSENTE; "
        "doas grep -c nexus /mnt/i/etc/passwd; doas du -sh /mnt/i; doas umount /mnt/i"))
    time.sleep(15)
    vm.chiudi()
    out1 = _leggi_risultati(ris)
    # riavvio dal disco installato (niente ISO)
    ris2 = _disco_risultati(cartella, "dal-disco")
    argv2 = ["qemu-system-x86_64", "-enable-kvm", "-m", "4096", "-smp", "2",
             "-vga", "std", "-nic", "none", "-device", "qemu-xhci",
             "-drive", "if=virtio,format=raw,file=%s" % disco, "-boot", "c",
             "-drive", "if=none,id=r,format=raw,file=%s" % ris2,
             "-device", "usb-storage,drive=r,removable=on"]
    vm = VM("daldisco", argv2, cartella)
    time.sleep(ATTESA_BOOT)
    vm.schermata("desktop")
    vm.terminale()
    vm.scrivi(_cmd_esito(_CONTROLLI_BASE))
    time.sleep(8)
    vm.schermata("esito")
    vm.chiudi()
    out2 = _leggi_risultati(ris2)
    try:
        os.remove(disco)
    except OSError:
        pass
    out = out1 + "\n--- avvio dal disco ---\n" + out2
    esiti = {"install": "INST-OK" in out1, "inst-nxs": "NXS-PRESENTE" in out1
             and "PANNELLO-PRESENTE" in out1, "daldisco": "DESKTOP-OK" in out2}
    return esiti, out


def prova_arm(iso, cartella):
    ris = _disco_risultati(cartella, "arm")
    vars_ = os.path.join(cartella, "arm.vars")
    shutil.copy(AAVMF_VARS, vars_)
    argv = ["qemu-system-aarch64", "-M", "virt", "-cpu", "max", "-smp", "4", "-m", "4096",
            "-drive", "if=pflash,format=raw,readonly=on,file=%s" % AAVMF_CODE,
            "-drive", "if=pflash,format=raw,file=%s" % vars_,
            "-device", "virtio-gpu-pci", "-device", "qemu-xhci", "-device", "usb-kbd",
            "-device", "usb-tablet",
            "-drive", "if=none,id=cd,format=raw,readonly=on,file=%s" % iso,
            "-device", "usb-storage,drive=cd,removable=on",
            "-drive", "if=none,id=r,format=raw,file=%s" % ris,
            "-device", "usb-storage,drive=r,removable=on",
            "-nic", "user,model=virtio-net-pci"]
    vm = VM("arm", argv, cartella)
    time.sleep(ATTESA_ARM)
    vm.schermata("desktop")
    # ARM e' EMULATA (lenta): il terminale ci mette molto ad aprirsi e i tasti
    # mandati troppo presto andavano persi (comando monco -> falso KO, 2026-11-22)
    vm.terminale(attesa=45)
    vm.scrivi(_cmd_esito("echo DESKTOP-OK; uname -m"), pausa=0.2)
    time.sleep(20)
    vm.schermata("esito")
    vm.chiudi()
    out = _leggi_risultati(ris)
    return {"arm": "DESKTOP-OK" in out and "aarch64" in out}, out


def main():
    ap = argparse.ArgumentParser(description="Collaudo automatico di una ISO NexusSec")
    ap.add_argument("iso", help="ISO x86_64 da collaudare")
    ap.add_argument("--arm", help="ISO aarch64 da collaudare (lento)")
    ap.add_argument("--solo", help="prove da eseguire, es. bios,uefi,persist")
    ap.add_argument("--dir", help="cartella di lavoro (default: temporanea)")
    a = ap.parse_args()
    for t in ("qemu-system-x86_64", "mke2fs", "debugfs", "mkfs.ext4"):
        if not shutil.which(t):
            print("manca %s sul PC" % t)
            return 2
    cartella = a.dir or tempfile.mkdtemp(prefix="nxs-collaudo-")
    os.makedirs(cartella, exist_ok=True)
    solo = set((a.solo or "bios,uefi,persist").split(","))
    esiti, log = {}, []
    if "bios" in solo:
        e, o = prova_avvio(a.iso, False, cartella); esiti.update(e); log.append(("BIOS", o))
    if "uefi" in solo:
        e, o = prova_avvio(a.iso, True, cartella); esiti.update(e); log.append(("UEFI", o))
    if "persist" in solo:
        e, o = prova_persistenza(a.iso, cartella); esiti.update(e); log.append(("PERSISTENZA", o))
    if "installa" in solo:
        e, o = prova_installa(a.iso, cartella); esiti.update(e); log.append(("INSTALLA", o))
    if a.arm:
        e, o = prova_arm(a.arm, cartella); esiti.update(e); log.append(("ARM", o))
    with open(os.path.join(cartella, "rapporto.txt"), "w") as f:
        for titolo, o in log:
            f.write("=== %s ===\n%s\n" % (titolo, o))
    print("\nCOLLAUDO di %s" % os.path.basename(a.iso))
    for k, v in esiti.items():
        print("  %-10s %s" % (k, "OK" if v else "KO"))
    print("\nSchermate e rapporto in: %s" % cartella)
    # i dischi grandi non servono piu'
    for g in ("chiavetta.img", "estranea.img", "disco-install.img"):
        try:
            os.remove(os.path.join(cartella, g))
        except OSError:
            pass
    return 0 if esiti and all(esiti.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
