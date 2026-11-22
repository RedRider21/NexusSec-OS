# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""NexusSec OS - splash di avvio sotto X (GTK3 + Cairo), 2026-11-22.

STESSA grafica della splash sul framebuffer (nxs_cc/fbanim.py), in stile
Linux Mint: sfondo uniforme, logo NexusSec che pulsa (fotogrammi di
splash/pulse.bin, build/make-bootsplash.py) e barra di avanzamento sottile.
La barra RIPARTE da dove l'aveva lasciata fbanim (/run/nxs-splash.progress) e
arriva al 100% mentre il desktop si prepara DIETRO; poi sfuma sul desktop.
A occhio: un'unica splash dall'accensione al desktop.

Parte come PRIMO client X (autostart), a tutto schermo, sopra tutto; ESC o un
clic la chiudono subito.
"""
from __future__ import annotations

import os

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib  # noqa: E402

ASSETS = os.environ.get("NXS_SPLASH_DIR", "/usr/local/share/nexussec/splash")

DURATION_MS = 4500      # durata visibile (poi fade-out e chiusura)
# 0: subentra senza stacco alla splash di avvio (fbsplash, stessa grafica)
FADE_IN_MS = 0
FADE_OUT_MS = 650
STEP_MS = 33            # ~30 fps
HARD_TIMEOUT_MS = 8000  # rete di sicurezza: chiude comunque
BG = (5 / 255.0, 9 / 255.0, 15 / 255.0)
TRACK = (22 / 255.0, 40 / 255.0, 54 / 255.0)
FILL = (0.0, 229 / 255.0, 1.0)
LOGO_DY, BAR_W, BAR_H, BAR_DY = 40, 260, 4, 120   # come make-bootsplash.py
PROGRESS = "/run/nxs-splash.progress"


def _fotogrammi():
    """Fotogrammi del logo che pulsa (pulse.bin) come GdkPixbuf."""
    import struct
    import zlib
    try:
        with open(os.path.join(ASSETS, "pulse.bin"), "rb") as fh:
            d = fh.read()
        w, h, n = struct.unpack_from("<HHH", d, 4)
        pos, out = 10, []
        for _ in range(n):
            ln = struct.unpack_from("<I", d, pos)[0]
            raw = zlib.decompress(d[pos + 4:pos + 4 + ln])
            out.append(GdkPixbuf.Pixbuf.new_from_bytes(
                GLib.Bytes.new(raw), GdkPixbuf.Colorspace.RGB, False, 8, w, h, w * 3))
            pos += 4 + ln
        return out
    except Exception:                       # noqa: BLE001
        return []


def _progresso_iniziale():
    try:
        return max(0.0, min(0.95, float(open(PROGRESS).read().strip())))
    except (OSError, ValueError):
        return 0.0


class BootSplash(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_app_paintable(True)
        try:
            scr = Gdk.Screen.get_default()
            self._sw, self._sh = scr.get_width(), scr.get_height()
        except Exception:                   # noqa: BLE001
            self._sw, self._sh = 1920, 1080
        self.set_default_size(self._sw, self._sh)
        self.move(0, 0)
        self.set_events(self.get_events()
                        | Gdk.EventMask.KEY_PRESS_MASK
                        | Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("key-press-event", lambda *_: self._finish())
        self.connect("button-press-event", lambda *_: self._finish())
        self.connect("draw", self._draw)

        self._frames = _fotogrammi()
        self._p0 = _progresso_iniziale()
        self._elapsed = 0
        self._done = False

    def _draw(self, _w, cr):
        W, H = self._sw, self._sh
        cx, cy = W / 2.0, H / 2.0
        cr.set_source_rgb(*BG)
        cr.paint()
        if self._frames:
            k = int(self._elapsed / 50.0) % len(self._frames)   # 20 fps
            pb = self._frames[k]
            Gdk.cairo_set_source_pixbuf(cr, pb, int(cx - pb.get_width() / 2),
                                        int(cy - LOGO_DY - pb.get_height() / 2))
            cr.paint()
        # barra: da dove l'ha lasciata la splash sul framebuffer fino al 100%
        corsa = max(1.0, float(DURATION_MS - FADE_OUT_MS))
        p = self._p0 + (1.0 - self._p0) * min(1.0, self._elapsed / corsa)
        bx, by = int(cx - BAR_W / 2), int(cy + BAR_DY)
        cr.set_source_rgb(*TRACK)
        cr.rectangle(bx, by, BAR_W, BAR_H)
        cr.fill()
        cr.set_source_rgb(*FILL)
        cr.rectangle(bx, by, int(BAR_W * p), BAR_H)
        cr.fill()
        ga = self._global_alpha()
        if ga < 1.0:                     # logo e barra sfumano nello sfondo
            cr.set_source_rgba(BG[0], BG[1], BG[2], 1.0 - ga)
            cr.rectangle(0, 0, W, H)
            cr.fill()
        return False

    def _global_alpha(self):
        e = self._elapsed
        if e < FADE_IN_MS:
            return e / float(FADE_IN_MS)
        if e > DURATION_MS - FADE_OUT_MS:
            return max(0.0, (DURATION_MS - e) / float(FADE_OUT_MS))
        return 1.0

    def _tick(self):
        self._elapsed += STEP_MS
        self.queue_draw()
        if self._elapsed >= DURATION_MS:
            return self._finish()
        return True

    def _finish(self):
        if self._done:
            return False
        self._done = True
        try:
            self.destroy()
        finally:
            Gtk.main_quit()
        return False

    def _stay_on_top(self):
        # Il desktop (pcmanfm/pannello/selettore) si costruisce DIETRO: ci
        # rialziamo periodicamente sopra tutto, cosi' la splash non viene
        # "bucata" e allo sfumare rivela un desktop gia' pronto.
        if self._done:
            return False
        self.set_keep_above(True)
        w = self.get_window()
        if w is not None:
            w.raise_()
        return True

    def run(self):
        self.connect("destroy", lambda *_: Gtk.main_quit())
        self.show_all()
        self.fullscreen()
        GLib.timeout_add(STEP_MS, self._tick)
        # Re-raise frequente (150ms): il desktop di base (pcmanfm/pannello) si
        # costruisce DIETRO durante la splash -> ci teniamo sopra a tutto cosi'
        # non lampeggia nulla prima che la splash sfumi. (Il selettore ora parte
        # solo DOPO la splash, vedi autostart: quello non serve piu' coprirlo.)
        GLib.timeout_add(150, self._stay_on_top)
        GLib.timeout_add(HARD_TIMEOUT_MS, self._finish)
        Gtk.main()


def main():
    BootSplash().run()


if __name__ == "__main__":
    main()
