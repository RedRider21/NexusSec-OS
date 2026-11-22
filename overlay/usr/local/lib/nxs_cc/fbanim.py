# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""fbanim - anima la splash di avvio sul FRAMEBUFFER (2026-11-22).

Gira durante l'avvio dei servizi (OpenRC), PRIMA di X, sopra la splash fissa
di fbsplash (che tiene la VT 16 in modo grafico: il testo non la copre). Disegna
la stessa grafica di nxs_cc.bootsplash: sfondo uniforme, logo che pulsa
(fotogrammi di splash/pulse.bin, build/make-bootsplash.py) e la barra di
avanzamento, che segue i servizi davvero avviati (/run/openrc/started rispetto
ai servizi dei runlevel). L'avanzamento raggiunto va in /run/nxs-splash.progress
cosi' la splash sotto X riparte da li': a occhio e' un'unica splash.

Python puro (niente GTK, niente PIL): legge geometria e ordine dei colori del
framebuffer con le ioctl FBIOGET_*. Solo 32 o 16 bit per pixel; altrimenti esce
e resta l'immagine fissa. Esce quando parte X, con /run/nxs-splash.stop o dopo
3 minuti. Non deve MAI bloccare l'avvio: ogni errore = uscita silenziosa.
"""
import fcntl
import glob
import os
import struct
import sys
import time
import zlib

PULSE = "/usr/local/share/nexussec/splash/pulse.bin"
PROGRESS = "/run/nxs-splash.progress"
STOP = "/run/nxs-splash.stop"
BG = (5, 9, 15)
TRACK = (22, 40, 54)
FILL = (0, 229, 255)
LOGO_DY, BAR_W, BAR_H, BAR_DY = 40, 260, 4, 120   # come make-bootsplash.py
QUOTA_OPENRC = 0.8          # la barra arriva all'80%; il resto sotto X
FPS = 20


def _info(fd):
    v = bytearray(160)
    fcntl.ioctl(fd, 0x4600, v)                     # FBIOGET_VSCREENINFO
    xres, yres, _xv, _yv, xoff, yoff, bpp = struct.unpack_from("<7I", v, 0)
    r_off, r_len = struct.unpack_from("<2I", v, 32)
    g_off, g_len = struct.unpack_from("<2I", v, 44)
    b_off, b_len = struct.unpack_from("<2I", v, 56)
    f = bytearray(80)
    fcntl.ioctl(fd, 0x4602, f)                     # FBIOGET_FSCREENINFO
    line = struct.unpack_from("<I", f, 48)[0]
    return dict(w=xres, h=yres, xoff=xoff, yoff=yoff, bpp=bpp, line=line,
                r=(r_off, r_len), g=(g_off, g_len), b=(b_off, b_len))


def _px(info, rgb):
    """Un pixel nel formato del framebuffer."""
    r, g, b = rgb
    v = 0
    for (off, ln), c in ((info["r"], r), (info["g"], g), (info["b"], b)):
        v |= (c >> (8 - ln)) << off
    return struct.pack("<I" if info["bpp"] == 32 else "<H", v)


def _converti(info, rgb_bytes):
    """Fotogramma RGB -> byte del framebuffer (veloce per i casi comuni)."""
    if info["bpp"] == 32 and info["r"][0] == 16 and info["b"][0] == 0:
        # XRGB8888 (il caso di quasi tutti): RGB -> BGRX con slicing
        n = len(rgb_bytes) // 3
        out = bytearray(n * 4)
        out[0::4] = rgb_bytes[2::3]
        out[1::4] = rgb_bytes[1::3]
        out[2::4] = rgb_bytes[0::3]
        return bytes(out)
    px = {}
    out = bytearray()
    for i in range(0, len(rgb_bytes), 3):
        k = rgb_bytes[i:i + 3]
        if k not in px:
            px[k] = _px(info, tuple(k))
        out += px[k]
    return bytes(out)


def _fotogrammi(info):
    with open(PULSE, "rb") as fh:
        d = fh.read()
    if d[:4] != b"NXSP":
        raise ValueError("pulse.bin non valido")
    w, h, n = struct.unpack_from("<HHH", d, 4)
    pos, out = 10, []
    for _ in range(n):
        ln = struct.unpack_from("<I", d, pos)[0]
        out.append(_converti(info, zlib.decompress(d[pos + 4:pos + 4 + ln])))
        pos += 4 + ln
    return w, h, out


def _totale_servizi():
    tot = set()
    for rl in ("sysinit", "boot", "default"):
        for p in glob.glob("/etc/runlevels/%s/*" % rl):
            tot.add(os.path.basename(p))
    return max(1, len(tot))


def _avviati():
    try:
        return len(os.listdir("/run/openrc/started"))
    except OSError:
        return 0


def _x_partito():
    return os.path.exists("/tmp/.X0-lock")


def main():
    try:
        fd = os.open("/dev/fb0", os.O_RDWR)
        info = _info(fd)
        if info["bpp"] not in (16, 32):
            return 0
        bpx = info["bpp"] // 8
        W, H, line = info["w"], info["h"], info["line"]
        fw, fh, frames = _fotogrammi(info)
    except Exception:                                # noqa: BLE001
        return 0
    base = (info["yoff"] * line) + info["xoff"] * bpx
    cx, cy = W // 2, H // 2

    def scrivi(x, y, dati, larg):
        for r in range(len(dati) // (larg * bpx)):
            os.pwrite(fd, dati[r * larg * bpx:(r + 1) * larg * bpx],
                      base + (y + r) * line + x * bpx)

    # sfondo uniforme su tutto lo schermo (fbsplash copre solo 1280x720)
    riga = _px(info, BG) * W
    for y in range(H):
        os.pwrite(fd, riga, base + y * line)
    lx, ly = cx - fw // 2, cy - LOGO_DY - fh // 2
    bx, by = cx - BAR_W // 2, cy + BAR_DY
    track = _px(info, TRACK)
    fill = _px(info, FILL)
    tot = _totale_servizi()
    prog = 0.0
    t0 = time.time()
    i = 0
    while True:
        if _x_partito() or os.path.exists(STOP) or time.time() - t0 > 180:
            break
        if lx >= 0 and ly >= 0:
            scrivi(lx, ly, frames[i % len(frames)], fw)
        # barra: segue i servizi avviati, mai all'indietro, lenta avanzata
        # minima per non sembrare ferma
        obiettivo = min(1.0, _avviati() / float(tot)) * QUOTA_OPENRC
        prog = max(prog + 0.0008, prog + (obiettivo - prog) * 0.15)
        prog = min(prog, QUOTA_OPENRC)
        piena = int(BAR_W * prog)
        barra = fill * piena + track * (BAR_W - piena)
        for r in range(BAR_H):
            os.pwrite(fd, barra, base + (by + r) * line + bx * bpx)
        try:
            with open(PROGRESS, "w") as fh_:
                fh_.write("%.3f\n" % prog)
        except OSError:
            pass
        i += 1
        time.sleep(1.0 / FPS)
    os.close(fd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
