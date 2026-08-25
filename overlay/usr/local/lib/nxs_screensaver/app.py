"""Salvaschermo NexusSec - GTK3 + Cairo, coerente con l'estetica della distro.

Finestra a schermo intero, senza decorazioni, keep-above; animazione Cairo
tinta con l'ACCENT del profilo attivo. Stili disponibili:
  - nebula     : rete di particelle collegate (plexus) su nebulosa
  - matrix     : pioggia di glifi verticali stile "matrix"
  - starfield  : campo stellare in avvicinamento (warp)
  - aurora     : bande sinusoidali fluide (aurora boreale)
  - grid       : griglia prospettica synthwave con "sole" all'orizzonte
  - hexpulse   : nido d'ape (come il badge NexusSec) che pulsa a onde
  - orbits     : nodo centrale con particelle in orbita (costellazione)

Blocco schermo: se abilitato (lock=1 in screensaver.conf) e c'e' una password
impostata, al primo input compare la richiesta di sblocco; si esce solo con la
password corretta. Altrimenti si esce a qualsiasi input.

Uso: nxs-screensaver [stile]
Nessuna dipendenza extra (Cairo/GTK via PyGObject, gia' nel desktop base).
"""
import math
import os
import random
import sys
import time

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib  # noqa: E402

from nxs_screensaver import secret  # noqa: E402

STYLES = ("nebula", "matrix", "starfield", "aurora", "grid", "hexpulse", "orbits")


def _accent():
    try:
        from nxs_profiles import model
        ac = model.accent()
        if isinstance(ac, str) and ac.startswith("#") and len(ac) == 7:
            return ac
    except Exception:                       # noqa: BLE001
        pass
    return "#00e5ff"


def _rgb01(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _read_conf():
    cfg = {"style": "nebula", "lock": "0"}
    path = os.path.expanduser("~/.config/nxs/screensaver.conf")
    try:
        with open(path) as f:
            for line in f:
                if "=" in line:
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip()
    except OSError:
        pass
    return cfg


class Saver(Gtk.Window):
    def __init__(self, style="nebula", lock=False):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.style = style if style in STYLES else "nebula"
        self.accent = _accent()
        self.ar, self.ag, self.ab = _rgb01(self.accent)
        self.locked = bool(lock) and secret.has_password()
        self._unlock_shown = False
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_app_paintable(True)
        self.set_title("NexusSec Screensaver")
        self._t0 = time.time()
        self._started = self._t0
        self.W, self.H = 1920, 1080

        # stage: DrawingArea (animazione) + overlay per la card di sblocco
        self.overlay = Gtk.Overlay()
        self.area = Gtk.DrawingArea()
        self.area.connect("draw", self._draw)
        self.overlay.add(self.area)
        self._build_unlock_card()
        self.add(self.overlay)

        self.add_events(Gdk.EventMask.KEY_PRESS_MASK |
                        Gdk.EventMask.POINTER_MOTION_MASK |
                        Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("key-press-event", self._on_key)
        self.connect("button-press-event", self._on_input)
        self.connect("motion-notify-event", self._on_motion)
        self.connect("realize", self._on_realize)
        self.connect("size-allocate", self._on_size)

        self._particles = []
        self._drops = []
        self._stars = []
        self._orbits = []
        self._init_scene()

        self.fullscreen()
        self.show_all()
        self.card.hide()
        self._tick_id = GLib.timeout_add(33, self._tick)   # ~30 fps

    # -------------------------------------------------------- card sblocco
    def _build_unlock_card(self):
        self.card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.card.set_halign(Gtk.Align.CENTER)
        self.card.set_valign(Gtk.Align.CENTER)
        self.card.get_style_context().add_class("nxs-lock-card")
        # stile locale (non dipende dal CSS globale)
        css = ("""
        .nxs-lock-card { background-color: rgba(6,11,18,0.92);
            border: 1px solid rgba(%d,%d,%d,0.55); border-radius: 16px;
            padding: 26px 30px; }
        .nxs-lock-title { color: #eaf6ff; font-size: 17px; font-weight: bold; }
        .nxs-lock-msg { color: #ff6f9a; font-size: 12px; }
        .nxs-lock-card entry { border-radius: 10px; min-width: 260px;
            padding: 8px 12px; }
        """ % (int(self.ar * 255), int(self.ag * 255), int(self.ab * 255)))
        try:
            prov = Gtk.CssProvider()
            prov.load_from_data(css.encode("utf-8"))
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(), prov,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 2)
        except Exception:                   # noqa: BLE001
            pass

        title = Gtk.Label(label="Schermo bloccato")
        title.get_style_context().add_class("nxs-lock-title")
        self.card.pack_start(title, False, False, 0)
        who = Gtk.Label(label="Inserisci la password per sbloccare")
        who.get_style_context().add_class("nxs-lock-msg")
        who.override_color(Gtk.StateFlags.NORMAL,
                           Gdk.RGBA(0.7, 0.82, 0.9, 1.0))
        self.card.pack_start(who, False, False, 0)

        self.entry = Gtk.Entry()
        self.entry.set_visibility(False)
        self.entry.set_placeholder_text("Password")
        self.entry.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY,
                                           "view-reveal-symbolic")
        self.entry.connect("icon-press", self._toggle_eye)
        self.entry.connect("activate", lambda _w: self._try_unlock())
        self.card.pack_start(self.entry, False, False, 0)

        self.msg = Gtk.Label(label="")
        self.msg.get_style_context().add_class("nxs-lock-msg")
        self.card.pack_start(self.msg, False, False, 0)

        btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btns.set_halign(Gtk.Align.CENTER)
        b_ok = Gtk.Button(label="Sblocca")
        b_ok.connect("clicked", lambda _w: self._try_unlock())
        b_cancel = Gtk.Button(label="Annulla")
        b_cancel.connect("clicked", lambda _w: self._hide_card())
        btns.pack_start(b_ok, False, False, 0)
        btns.pack_start(b_cancel, False, False, 0)
        self.card.pack_start(btns, False, False, 0)
        self.overlay.add_overlay(self.card)

    def _toggle_eye(self, entry, _pos, _ev):
        vis = not entry.get_visibility()
        entry.set_visibility(vis)
        entry.set_icon_from_icon_name(
            Gtk.EntryIconPosition.SECONDARY,
            "view-conceal-symbolic" if vis else "view-reveal-symbolic")

    def _show_card(self):
        if self._unlock_shown:
            return
        self._unlock_shown = True
        self.msg.set_text("")
        self.entry.set_text("")
        self.card.show_all()
        self.entry.grab_focus()

    def _hide_card(self):
        self._unlock_shown = False
        self.card.hide()

    def _try_unlock(self):
        if secret.verify(self.entry.get_text()):
            self._quit()
        else:
            self.msg.set_text("Password errata. Riprova.")
            self.entry.set_text("")
            self.entry.grab_focus()

    # ------------------------------------------------------------------
    def _on_realize(self, *_a):
        win = self.get_window()
        if win is not None:
            blank = Gdk.Cursor.new_for_display(
                Gdk.Display.get_default(), Gdk.CursorType.BLANK_CURSOR)
            win.set_cursor(blank)
            if self.locked:
                self._grab(win)
        try:
            disp = Gdk.Display.get_default()
            seat = disp.get_default_seat()
            ptr = seat.get_pointer()
            _s, self._mx, self._my = ptr.get_position()
        except Exception:                   # noqa: BLE001
            self._mx = self._my = -1

    def _grab(self, win):
        # blocca tastiera+puntatore sulla nostra finestra (lock vero)
        try:
            seat = Gdk.Display.get_default().get_default_seat()
            seat.grab(win, Gdk.SeatCapabilities.ALL, True, None, None, None, None)
        except Exception:                   # noqa: BLE001
            pass

    def _ungrab(self):
        try:
            Gdk.Display.get_default().get_default_seat().ungrab()
        except Exception:                   # noqa: BLE001
            pass

    def _on_size(self, _w, alloc):
        self.W, self.H = max(1, alloc.width), max(1, alloc.height)

    def _reveal_cursor(self):
        win = self.get_window()
        if win is not None:
            win.set_cursor(None)

    def _on_key(self, _w, ev):
        if self.locked:
            # Esc chiude la card (torna all'animazione); altri tasti la mostrano
            if ev.keyval == Gdk.KEY_Escape:
                self._hide_card()
                return True
            self._reveal_cursor()
            self._show_card()
            return False
        return self._quit()

    def _on_input(self, _w, _ev):
        if self.locked:
            self._reveal_cursor()
            self._show_card()
            return False
        return self._quit()

    def _on_motion(self, _w, ev):
        if time.time() - self._started < 0.6:
            self._mx, self._my = ev.x, ev.y
            return False
        if getattr(self, "_mx", -1) < 0:
            self._mx, self._my = ev.x, ev.y
            return False
        if abs(ev.x - self._mx) + abs(ev.y - self._my) > 6:
            if self.locked:
                self._reveal_cursor()
                self._show_card()
            else:
                self._quit()
        return False

    def _quit(self, *_a):
        try:
            if self._tick_id:
                GLib.source_remove(self._tick_id)
        except Exception:                   # noqa: BLE001
            pass
        self._ungrab()
        Gtk.main_quit()
        return True

    # ------------------------------------------------------------- scene
    def _init_scene(self):
        random.seed()
        for _ in range(70):
            self._particles.append([
                random.uniform(0, 1), random.uniform(0, 1),
                random.uniform(-0.03, 0.03), random.uniform(-0.03, 0.03),
                random.uniform(1.2, 2.8)])
        cols = 90
        for i in range(cols):
            self._drops.append([i / float(cols), random.uniform(-1, 0),
                                random.uniform(0.35, 0.9)])
        for _ in range(180):
            self._stars.append([random.uniform(-1, 1), random.uniform(-1, 1),
                                random.uniform(0.02, 1.0)])
        for _ in range(48):
            self._orbits.append([
                random.uniform(0, 2 * math.pi),          # angolo
                random.uniform(0.08, 0.46),              # raggio (frazione)
                random.uniform(0.3, 1.3),                # velocita'
                random.uniform(0.35, 0.85)])             # schiacciamento ellisse

    def _tick(self):
        self.area.queue_draw()
        return True

    # -------------------------------------------------------------- draw
    def _draw(self, _w, cr):
        W, H = self.W, self.H
        t = time.time() - self._t0
        cr.set_source_rgb(0.016, 0.03, 0.055)
        cr.paint()
        try:
            g = self._radial(W, H, t)
            cr.set_source(g)
            cr.paint()
        except Exception:                   # noqa: BLE001
            pass

        fn = {
            "matrix": self._draw_matrix,
            "starfield": lambda c, w, h: self._draw_starfield(c, w, h, t),
            "aurora": lambda c, w, h: self._draw_aurora(c, w, h, t),
            "grid": lambda c, w, h: self._draw_grid(c, w, h, t),
            "hexpulse": lambda c, w, h: self._draw_hexpulse(c, w, h, t),
            "orbits": lambda c, w, h: self._draw_orbits(c, w, h, t),
        }.get(self.style, self._draw_nebula)
        fn(cr, W, H)

        self._draw_branding(cr, W, H, t)
        return False

    def _radial(self, W, H, t):
        import cairo
        cx = W * (0.5 + 0.06 * math.sin(t * 0.15))
        cy = H * (0.45 + 0.05 * math.cos(t * 0.11))
        r = max(W, H) * 0.75
        g = cairo.RadialGradient(cx, cy, 0, cx, cy, r)
        g.add_color_stop_rgba(0, self.ar, self.ag, self.ab, 0.10)
        g.add_color_stop_rgba(0.5, self.ar * 0.4, self.ag * 0.4, self.ab * 0.4, 0.04)
        g.add_color_stop_rgba(1, 0.01, 0.02, 0.04, 0.0)
        return g

    def _draw_nebula(self, cr, W, H):
        ps = self._particles
        for p in ps:
            p[0] = (p[0] + p[2] * 0.01) % 1.0
            p[1] = (p[1] + p[3] * 0.01) % 1.0
        cr.set_line_width(1.0)
        for i in range(len(ps)):
            xi, yi = ps[i][0] * W, ps[i][1] * H
            for j in range(i + 1, len(ps)):
                dx = (ps[i][0] - ps[j][0]) * W
                dy = (ps[i][1] - ps[j][1]) * H
                d2 = dx * dx + dy * dy
                if d2 < 160 * 160:
                    a = 0.28 * (1 - math.sqrt(d2) / 160.0)
                    cr.set_source_rgba(self.ar, self.ag, self.ab, a)
                    cr.move_to(xi, yi)
                    cr.line_to(ps[j][0] * W, ps[j][1] * H)
                    cr.stroke()
        for p in ps:
            x, y = p[0] * W, p[1] * H
            cr.set_source_rgba(self.ar, self.ag, self.ab, 0.9)
            cr.arc(x, y, p[4], 0, 2 * math.pi)
            cr.fill()

    def _draw_matrix(self, cr, W, H):
        cr.select_font_face("monospace")
        cr.set_font_size(18)
        glyphs = "01<>[]{}#$%&/\\|=+*ABCDEF0123456789xzΩλΣ"
        for d in self._drops:
            d[1] += d[2] * 0.02
            if d[1] > 1.2:
                d[1] = random.uniform(-0.4, 0)
                d[2] = random.uniform(0.35, 0.9)
            x = d[0] * W
            head = d[1] * H
            for k in range(16):
                y = head - k * 20
                if y < 0 or y > H:
                    continue
                a = max(0.0, 0.85 - k * 0.06)
                if k == 0:
                    cr.set_source_rgba(0.85, 1.0, 0.95, a)
                else:
                    cr.set_source_rgba(self.ar, self.ag, self.ab, a)
                cr.move_to(x, y)
                cr.show_text(random.choice(glyphs))

    def _draw_starfield(self, cr, W, H, t):
        cx, cy = W / 2.0, H / 2.0
        for s in self._stars:
            s[2] -= 0.006
            if s[2] <= 0.02:
                s[0] = random.uniform(-1, 1)
                s[1] = random.uniform(-1, 1)
                s[2] = 1.0
            k = 1.0 / s[2]
            x = cx + s[0] * k * cx
            y = cy + s[1] * k * cy
            if x < 0 or x > W or y < 0 or y > H:
                continue
            r = max(0.4, (1.0 - s[2]) * 2.6)
            a = min(1.0, (1.0 - s[2]) * 1.1)
            cr.set_source_rgba(self.ar, self.ag, self.ab, a)
            cr.arc(x, y, r, 0, 2 * math.pi)
            cr.fill()

    def _draw_aurora(self, cr, W, H, t):
        # bande sinusoidali morbide che scorrono, con leggera sfumatura
        cr.set_operator(1)  # OVER
        bands = 5
        for b in range(bands):
            phase = t * (0.25 + 0.05 * b) + b * 1.7
            base = H * (0.30 + 0.10 * b)
            amp = H * (0.05 + 0.015 * b)
            alpha = 0.10 + 0.04 * (bands - b)
            cr.move_to(0, H)
            step = max(6, W // 220)
            for x in range(0, W + step, step):
                y = base + amp * math.sin(x * 0.006 + phase) \
                    + amp * 0.4 * math.sin(x * 0.013 - phase * 1.3)
                cr.line_to(x, y)
            cr.line_to(W, H)
            cr.close_path()
            shade = 0.5 + 0.5 * (b / float(bands))
            cr.set_source_rgba(self.ar * shade, self.ag * shade,
                               self.ab * shade, alpha)
            cr.fill()

    def _draw_grid(self, cr, W, H, t):
        # synthwave: sole all'orizzonte + griglia prospettica in movimento
        hor = H * 0.52
        # sole
        import cairo
        sun = cairo.RadialGradient(W / 2, hor, 10, W / 2, hor, H * 0.22)
        sun.add_color_stop_rgba(0, self.ar, self.ag, self.ab, 0.55)
        sun.add_color_stop_rgba(1, self.ar, self.ag, self.ab, 0.0)
        cr.set_source(sun)
        cr.arc(W / 2, hor, H * 0.22, 0, 2 * math.pi)
        cr.fill()
        cr.set_line_width(1.2)
        cr.set_source_rgba(self.ar, self.ag, self.ab, 0.5)
        # linee verticali che convergono verso un punto di fuga
        vp_x = W / 2.0
        for i in range(-14, 15):
            x_bottom = vp_x + i * (W / 14.0)
            cr.move_to(x_bottom, H)
            cr.line_to(vp_x + i * 6, hor)
            cr.stroke()
        # linee orizzontali che "avanzano" verso lo spettatore
        speed = (t * 0.6) % 1.0
        for k in range(1, 22):
            f = (k + speed) / 22.0
            y = hor + (H - hor) * (f * f)
            a = 0.55 * (1 - f)
            cr.set_source_rgba(self.ar, self.ag, self.ab, a)
            cr.move_to(0, y)
            cr.line_to(W, y)
            cr.stroke()

    def _draw_hexpulse(self, cr, W, H, t):
        # nido d'ape (come il badge NexusSec) che pulsa a onde radiali
        R = max(26, H // 22)                 # raggio esagono
        dx = R * 1.5
        dy = R * math.sqrt(3)
        cx0, cy0 = W / 2.0, H / 2.0
        cr.set_line_width(1.4)
        col = 0
        x = -R
        while x < W + R:
            row = 0
            yoff = 0 if col % 2 == 0 else dy / 2.0
            y = -R + yoff
            while y < H + R:
                d = math.hypot(x - cx0, y - cy0)
                wave = 0.5 + 0.5 * math.sin(d * 0.012 - t * 2.0)
                a = 0.08 + 0.30 * wave
                cr.set_source_rgba(self.ar, self.ag, self.ab, a)
                self._hexpath(cr, x, y, R)
                cr.stroke()
                if wave > 0.85:
                    cr.set_source_rgba(self.ar, self.ag, self.ab, 0.18 * wave)
                    self._hexpath(cr, x, y, R)
                    cr.fill()
                y += dy
                row += 1
            x += dx
            col += 1

    def _hexpath(self, cr, cx, cy, r):
        for i in range(6):
            ang = math.pi / 180.0 * (60 * i)
            px = cx + r * math.cos(ang)
            py = cy + r * math.sin(ang)
            if i == 0:
                cr.move_to(px, py)
            else:
                cr.line_to(px, py)
        cr.close_path()

    def _draw_orbits(self, cr, W, H, t):
        cx, cy = W / 2.0, H / 2.0
        rr = min(W, H)
        # nucleo pulsante
        pulse = 0.6 + 0.4 * math.sin(t * 1.8)
        cr.set_source_rgba(self.ar, self.ag, self.ab, 0.9)
        cr.arc(cx, cy, 4 + 3 * pulse, 0, 2 * math.pi)
        cr.fill()
        cr.set_line_width(1.0)
        for o in self._orbits:
            o[0] += 0.01 * o[2]
            a_ang, rad, _sp, squash = o
            rx = rad * rr
            ry = rad * rr * squash
            x = cx + rx * math.cos(a_ang)
            y = cy + ry * math.sin(a_ang)
            # linea verso il centro
            cr.set_source_rgba(self.ar, self.ag, self.ab, 0.12)
            cr.move_to(cx, cy)
            cr.line_to(x, y)
            cr.stroke()
            # nodo
            cr.set_source_rgba(self.ar, self.ag, self.ab, 0.85)
            cr.arc(x, y, 2.2, 0, 2 * math.pi)
            cr.fill()

    def _draw_branding(self, cr, W, H, t):
        if self._unlock_shown:
            return
        pulse = 0.75 + 0.25 * math.sin(t * 1.6)
        cr.select_font_face("sans-serif", 0, 1)
        cr.set_font_size(64)
        text = "NexusSec"
        ext = cr.text_extents(text)
        tx = (W - ext.width) / 2.0 - ext.x_bearing
        ty = H / 2.0
        cr.set_source_rgba(self.ar, self.ag, self.ab, 0.9 * pulse)
        cr.move_to(tx, ty)
        cr.show_text(text)
        cr.select_font_face("sans-serif", 0, 0)
        cr.set_font_size(30)
        clock = time.strftime("%H:%M")
        e2 = cr.text_extents(clock)
        cr.set_source_rgba(0.85, 0.96, 1.0, 0.85)
        cr.move_to((W - e2.width) / 2.0 - e2.x_bearing, ty + 50)
        cr.show_text(clock)
        cr.set_font_size(15)
        hint = ("Premi un tasto per sbloccare" if self.locked
                else "Muovi il mouse o premi un tasto per sbloccare")
        e3 = cr.text_extents(hint)
        cr.set_source_rgba(0.55, 0.72, 0.82, 0.7)
        cr.move_to((W - e3.width) / 2.0 - e3.x_bearing, H - 60)
        cr.show_text(hint)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    cfg = _read_conf()
    style = argv[0] if argv else cfg.get("style", "nebula")
    lock = cfg.get("lock", "0") == "1"
    Saver(style, lock=lock)
    Gtk.main()


if __name__ == "__main__":
    main()
