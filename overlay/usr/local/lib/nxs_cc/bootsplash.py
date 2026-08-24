"""NexusSec OS - splash di avvio a schermo intero (GTK3 + Cairo).

Compone gli asset pre-renderizzati (build/make-plymouth-theme.py ->
/usr/local/share/nexussec/splash/) in una scena "cyber command" ANIMATA:
  - sfondo con esagoni concentrici, vignette, brackets HUD (bg.png),
  - anello-strumento + emblema esagonale "N",
  - glow che "respira", particelle orbitanti,
  - wordmark + tagline IA + footer profili,
  - barra di avanzamento con testa luminosa,
  - scanline che scorre; fade da/verso nero.

Parte come PRIMO client X (autostart), a tutto schermo, sopra tutto; copre la
preparazione del desktop e si chiude da sola (o con ESC/click). Il boot testuale
e' nascosto (console su tty12), quindi allo sguardo la sequenza e':
schermo pulito -> questa splash -> desktop.
"""
from __future__ import annotations

import math
import os

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib  # noqa: E402

ASSETS = os.environ.get("NXS_SPLASH_DIR", "/usr/local/share/nexussec/splash")

DURATION_MS = 6500      # durata visibile (poi fade-out e chiusura)
FADE_IN_MS = 550
FADE_OUT_MS = 650
STEP_MS = 33            # ~30 fps
HARD_TIMEOUT_MS = 9500  # rete di sicurezza: chiude comunque


def _load(name):
    try:
        return GdkPixbuf.Pixbuf.new_from_file(os.path.join(ASSETS, name))
    except Exception:                       # noqa: BLE001
        return None


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

        # asset
        self._img = {n: _load(n + ".png") for n in (
            "bg", "scan", "glow", "ring", "emblem", "particle",
            "wordmark", "tagline", "footer", "version",
            "bar_track", "bar_fill", "bar_head")}
        self._cache = {}
        self._elapsed = 0
        self._done = False

    # --- utilita' di disegno ---
    def _scaled(self, name, w, h):
        w = max(1, int(w)); h = max(1, int(h))
        key = (name, w, h)
        pb = self._cache.get(key)
        if pb is None:
            src = self._img.get(name)
            if src is None:
                return None
            pb = src.scale_simple(w, h, GdkPixbuf.InterpType.BILINEAR)
            self._cache[key] = pb
        return pb

    def _paint(self, cr, name, cx, cy, w, h, alpha=1.0):
        """Disegna l'asset 'name' scalato a (w,h) CENTRATO in (cx,cy)."""
        pb = self._scaled(name, w, h)
        if pb is None or alpha <= 0:
            return
        x = cx - pb.get_width() / 2
        y = cy - pb.get_height() / 2
        cr.save()
        Gdk.cairo_set_source_pixbuf(cr, pb, x, y)
        cr.paint_with_alpha(max(0.0, min(1.0, alpha)))
        cr.restore()

    def _aspect_h(self, name, w):
        src = self._img.get(name)
        if src is None:
            return 0
        return w * src.get_height() / src.get_width()

    def _draw(self, _w, cr):
        W, H = self._sw, self._sh
        f = H / 1080.0
        cx = W / 2
        t = self._elapsed / 1000.0

        # sfondo (opaco, riempie lo schermo)
        bg = self._scaled("bg", W, H)
        if bg is not None:
            Gdk.cairo_set_source_pixbuf(cr, bg, 0, 0)
            cr.paint()
        else:
            cr.set_source_rgb(0.02, 0.04, 0.08); cr.paint()

        # scanline che scorre
        travel = (t * 0.16) % 1.0
        sh_h = int(140 * f)
        scan_y = H * 0.14 + (H * 0.66) * travel
        self._paint(cr, "scan", cx, scan_y, W, sh_h, 0.85)

        ecy = H * 0.34
        # glow pulsante
        gs = int(760 * f)
        self._paint(cr, "glow", cx, ecy, gs, gs,
                    0.28 + 0.22 * math.sin(t * 2.2))
        # anello
        rs = int(360 * f)
        self._paint(cr, "ring", cx, ecy, rs, rs, 1.0)
        # particelle orbitanti
        R = 175 * f
        ps = int(40 * f)
        for i in range(6):
            ang = t * 0.9 + i * (math.pi / 3)
            px = cx + R * math.cos(ang)
            py = ecy + R * math.sin(ang)
            op = 0.35 + 0.55 * (0.5 + 0.5 * math.sin(ang * 2))
            self._paint(cr, "particle", px, py, ps, ps, op)
        # emblema
        es = int(250 * f)
        self._paint(cr, "emblem", cx, ecy, es, es, 1.0)

        # testi
        ww = W * 0.375
        self._paint(cr, "wordmark", cx, H * 0.585, ww, self._aspect_h("wordmark", ww))
        tw = W * 0.44
        self._paint(cr, "tagline", cx, H * 0.70, tw, self._aspect_h("tagline", tw))
        fw = W * 0.52
        self._paint(cr, "footer", cx, H * 0.93, fw, self._aspect_h("footer", fw))
        vw = W * 0.13
        self._paint(cr, "version", cx, H * 0.965, vw, self._aspect_h("version", vw))

        # barra di avanzamento
        bw = W * 0.40
        bh = max(6, int(14 * f))
        by = H * 0.78
        self._paint(cr, "bar_track", cx, by, bw, bh, 1.0)
        frac = min(1.0, self._elapsed / float(DURATION_MS - FADE_OUT_MS))
        fillw = max(1, int(bw * frac))
        fill = self._scaled("bar_fill", int(bw), bh)
        if fill is not None:
            bx = cx - bw / 2
            cr.save()
            cr.rectangle(bx, by - bh / 2 - 1, fillw, bh + 2)
            cr.clip()
            Gdk.cairo_set_source_pixbuf(cr, fill, bx, by - fill.get_height() / 2)
            cr.paint()
            cr.restore()
            hs = int(64 * f)
            self._paint(cr, "bar_head", bx + fillw, by, hs, hs,
                        0.7 + 0.3 * math.sin(t * 6))

        # fade globale da/verso nero
        ga = self._global_alpha()
        if ga < 1.0:
            cr.set_source_rgba(0, 0, 0, 1.0 - ga)
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
