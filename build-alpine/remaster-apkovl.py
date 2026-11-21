#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""remaster-apkovl.py - aggiorna una ISO NexusSec GIA' COSTRUITA sostituendo
soltanto il suo apkovl (overlay), SENZA scaricare nulla e SENZA ricomporre
l'immagine.

Perche' cosi': l'overlay (pannello, HORUS, script nxs-*) e' quasi tutto quello
che cambia fra una versione e l'altra; kernel, initramfs, modloop e i ~630
pacchetti in apks/ restano validi. Rifare la ISO da zero richiede un container
Alpine pulito che riscarica ~1,5 GB per architettura; ricomporla con
genisoimage/isohybrid cambierebbe i settori di avvio ibridi creati da xorriso
(MBR+GPT su x86_64, GPT con "gap" su aarch64), gia' collaudati. Qui invece:

  1. si copia la ISO di partenza;
  2. si scrive il nuovo apkovl DENTRO l'estensione del vecchio file (deve
     starci: si controlla) azzerando il resto;
  3. si aggiorna la lunghezza del file nei record di directory ISO 9660
     (descrittore primario e Joliet);
  4. si sostituisce la data YYMMDD nell'etichetta del volume (stessa lunghezza).

Settori di avvio, MBR, GPT, El Torito, kernel e pacchetti restano IDENTICI
byte per byte. Uso:

  remaster-apkovl.py VECCHIA.iso NUOVA.iso nexussec.apkovl.tar.gz VECCHIA_DATA NUOVA_DATA
  es.: ... alpine-nexussec-261010-x86_64.iso alpine-nexussec-261121-x86_64.iso \\
           out/nexussec.apkovl.tar.gz 261010 261121
"""
import os
import shutil
import struct
import sys

SECTOR = 2048


def _records(f, lba, size):
    """Record di directory (offset assoluto, bytes) di un'estensione di directory."""
    out = []
    for s in range((size + SECTOR - 1) // SECTOR):
        base = (lba + s) * SECTOR
        f.seek(base)
        blk = f.read(SECTOR)
        i = 0
        while i < SECTOR:
            ln = blk[i]
            if ln == 0:
                break                      # resto del settore vuoto
            out.append((base + i, blk[i:i + ln]))
            i += ln
    return out


def _name(rec, joliet):
    n = rec[33:33 + rec[32]]
    try:
        n = n.decode("utf-16-be") if joliet else n.decode("ascii", "replace")
    except UnicodeDecodeError:
        return ""
    return n.split(";")[0].lower()


def main(argv):
    if len(argv) != 6:
        print(__doc__)
        return 2
    src, dst, ovl, old_d, new_d = argv[1:]
    if len(old_d) != len(new_d):
        print("le date devono avere la stessa lunghezza (YYMMDD)")
        return 2
    data = open(ovl, "rb").read()
    if os.path.abspath(src) == os.path.abspath(dst):
        print("la ISO di destinazione deve essere diversa da quella di partenza")
        return 2
    shutil.copyfile(src, dst)

    with open(dst, "r+b") as f:
        found = []                         # (offset_record, lba, size)
        vd = 16
        while True:
            f.seek(vd * SECTOR)
            d = f.read(SECTOR)
            typ = d[0]
            if d[1:6] != b"CD001":
                print("descrittore di volume non valido al settore %d" % vd)
                return 1
            if typ == 255:
                break
            if typ in (1, 2):
                joliet = typ == 2 and d[88:91] in (b"%/@", b"%/C", b"%/E")
                root = d[156:156 + 34]
                rlba = struct.unpack("<I", root[2:6])[0]
                rsize = struct.unpack("<I", root[10:14])[0]
                for off, rec in _records(f, rlba, rsize):
                    nm = _name(rec, joliet)
                    # primario: NEXUSSEC_APKOVL_TAR.GZ ; Joliet: nexussec.apkovl.tar.gz
                    if nm.startswith("nexussec") and "apkovl" in nm:
                        lba = struct.unpack("<I", rec[2:6])[0]
                        size = struct.unpack("<I", rec[10:14])[0]
                        found.append((off, lba, size))
                # etichetta del volume (32 byte a-characters / UCS-2 Joliet)
                vid = d[40:72]
                o = (old_d.encode("utf-16-be") if joliet else old_d.encode())
                n = (new_d.encode("utf-16-be") if joliet else new_d.encode())
                if o in vid:
                    f.seek(vd * SECTOR + 40)
                    f.write(vid.replace(o, n, 1))
                    print("etichetta %s: %s" % ("Joliet" if joliet else "primaria",
                          (vid.replace(o, n, 1).decode("utf-16-be" if joliet else "ascii", "replace")).strip()))
            vd += 1

        if not found:
            print("apkovl non trovato nella ISO")
            return 1
        lbas = {x[1] for x in found}
        if len(lbas) != 1:
            print("record apkovl incoerenti: %s" % found)
            return 1
        lba = found[0][1]
        old_size = found[0][2]
        capacity = ((old_size + SECTOR - 1) // SECTOR) * SECTOR
        if len(data) > capacity:
            print("il nuovo apkovl (%d byte) non entra nello spazio del vecchio (%d byte)"
                  % (len(data), capacity))
            return 1
        f.seek(lba * SECTOR)
        f.write(data + b"\0" * (capacity - len(data)))
        for off, _l, _s in found:
            f.seek(off + 10)
            f.write(struct.pack("<I", len(data)) + struct.pack(">I", len(data)))
        print("apkovl sostituito: LBA %d, %d -> %d byte, %d record aggiornati"
              % (lba, old_size, len(data), len(found)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
