#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""make-grub-disco.py - prepara il GRUB per NexusSec INSTALLATO su disco.

Sulla chiavetta non c'e' nessun pacchetto GRUB (la live si avvia con il GRUB
gia' dentro la ISO) e l'installatore deve funzionare SENZA RETE. Quindi le
immagini di avvio si costruiscono QUI, sul PC di sviluppo, con grub-mkimage
(pacchetti grub-pc-bin / grub-efi-amd64-bin gia' installati), e viaggiano
nell'overlay (~1,5 MB):

  mbr.bin      440 byte di codice MBR (boot.img) gia' "puntato" al core
  core.img     core GRUB per BIOS, da scrivere nella partizione BIOS boot
               che DEVE iniziare al settore 2048 (lo fa nxs-install-disco)
  BOOTX64.EFI  GRUB UEFI (percorso "removibile": nessuna voce NVRAM serve)

Entrambi hanno TUTTI i moduli incorporati e una configurazione minima che
cerca la partizione EFI con etichetta NXSEFI e carica /grub/grub.cfg da li'
(scritto dall'installatore, con gli UUID degli slot A/B).

Il lavoro di grub-bios-setup lo facciamo a mano (formato GRUB 2.06):
  boot.img: settore del core a 0x5c (8 byte LE), drive 0xff a 0x64,
            0x9090 a 0x66 (niente controllo floppy, come per i dischi fissi)
  core.img: primo settore = diskboot; lista blocchi in fondo (0x1f4):
            inizio = LBA core + 1, lunghezza = settori del core - 1
"""
import os
import struct
import subprocess
import sys
import tempfile

QUI = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(QUI, "..", "overlay", "usr", "local", "share", "nexussec", "grub-disco")
CORE_LBA = 2048
EMBED = """search --no-floppy --set=root --label NXSEFI
set prefix=($root)/grub
configfile ($root)/grub/grub.cfg
"""
COMUNI = ["part_gpt", "part_msdos", "fat", "ext2", "search", "search_label",
          "search_fs_uuid", "normal", "linux", "configfile", "echo", "test",
          "gzio", "loadenv", "sleep", "reboot", "halt", "ls", "cat", "true",
          "minicmd", "gfxterm", "font"]
PC = COMUNI + ["biosdisk", "vbe", "vga", "video_bochs", "video_cirrus"]
# Ubuntu: in UEFI "linux" passa la mano a linuxefi (patch Debian/Ubuntu):
# senza questo modulo il kernel non si carica (collaudo 2026-11-22)
EFI = COMUNI + ["efi_gop", "efi_uga", "all_video", "linuxefi"]


def mkimage(fmt, out, mods, cfg):
    subprocess.run(["grub-mkimage", "-O", fmt, "-o", out, "-c", cfg, "-p", "/grub"] + mods,
                   check=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    with tempfile.TemporaryDirectory() as t:
        cfg = os.path.join(t, "embed.cfg")
        open(cfg, "w").write(EMBED)
        core = os.path.join(t, "core.img")
        mkimage("i386-pc", core, PC, cfg)
        mkimage("x86_64-efi", os.path.join(OUT, "BOOTX64.EFI"), EFI, cfg)
        c = bytearray(open(core, "rb").read())
    n = (len(c) + 511) // 512
    c += b"\0" * (n * 512 - len(c))
    # lista blocchi di diskboot: ultima voce in fondo al primo settore
    struct.pack_into("<QH", c, 0x200 - 12, CORE_LBA + 1, n - 1)
    open(os.path.join(OUT, "core.img"), "wb").write(c)
    b = bytearray(open("/usr/lib/grub/i386-pc/boot.img", "rb").read())
    struct.pack_into("<Q", b, 0x5c, CORE_LBA)
    b[0x64] = 0xff
    struct.pack_into("<H", b, 0x66, 0x9090)
    for i in range(0x3, 0x5a):              # BPB: zeri, come nell'MBR protettivo
        b[i] = 0
    open(os.path.join(OUT, "mbr.bin"), "wb").write(bytes(b[:440]))
    print("core.img: %d settori (partizione BIOS boot da 2 MiB = 4096)" % n)
    for f in sorted(os.listdir(OUT)):
        print("  %-12s %7d byte" % (f, os.path.getsize(os.path.join(OUT, f))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
