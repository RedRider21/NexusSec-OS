"""nxs-recorder - registratore vocale NexusSec (GTK3 + Cairo).

Cattura dal microfono con `arecord` (ALSA, gia' nella base; instradato via il
bridge ALSA di PipeWire), mostra in tempo reale la forma d'onda (alti/bassi
della voce) e un indicatore di livello, registra su file WAV e permette di
riascoltare. Nessuna dipendenza nuova: solo alsa-utils + GTK3/Cairo.

Privacy: la cattura parte solo con la finestra aperta (per il monitor del
livello) e il file viene scritto solo quando premi Registra.
"""
import os
import struct
import subprocess
import threading
import wave
from datetime import datetime

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk  # noqa: E402
try:
    from gi.repository import Pango  # noqa: E402,F401
except Exception:                       # noqa: BLE001
    Pango = None

RATE = 16000            # Hz (voce: 16 kHz e' piu' che sufficiente e leggero)
CH = 1                  # mono
BYTES = 2              # S16_LE
CHUNK = 1024           # campioni per lettura
NBARS = 160            # quante barre di storia nella forma d'onda
OUTDIR = os.path.expanduser("~/NexusSec-loot/registrazioni")

# Palette NexusSec (coerente col resto del desktop)
GROUND = (5 / 255, 10 / 255, 20 / 255)
ACCENT = (0.0, 0.898, 1.0)          # #00e5ff
DIM = (0.35, 0.54, 0.60)
ALARM = (1.0, 0.353, 0.541)         # #ff5a8a

CSS = b"""
window { background:#050a14; color:#d4f3ff; }
.rec-title { font-weight:700; font-size:15px; color:#d4f3ff; }
.rec-sub { color:#6f97a8; font-size:12px; }
.rec-time { font-family:monospace; font-size:22px; color:#00e5ff; }
button { background:#0a1a26; color:#d4f3ff; border:1px solid #173247;
         border-radius:6px; padding:8px 14px; }
button:hover { border-color:#00e5ff; }
.rec-go { background:#00e5ff; color:#050a14; font-weight:700; border:none; }
.rec-stop { background:#ff5a8a; color:#050a14; font-weight:700; border:none; }
"""


class Recorder(Gtk.Window):
    def __init__(self):
        super().__init__(title="NexusSec - Registratore vocale")
        self.set_default_size(600, 340)
        self.set_icon_name("audio-input-microphone-symbolic")

        try:
            prov = Gtk.CssProvider()
            prov.load_from_data(CSS)
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(), prov,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        except Exception:               # noqa: BLE001
            pass

        self.levels = [0.0] * NBARS     # storia dei picchi (0..1) per la forma d'onda
        self.peak = 0.0                 # picco corrente (per la barra livello)
        self.recording = False
        self.wav = None
        self.frames = 0
        self.proc = None
        self._stop = False
        self.last_file = None
        self._start_mono = 0.0

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.set_border_width(14)
        self.add(root)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        t = Gtk.Label(label="Registratore vocale"); t.set_xalign(0)
        t.get_style_context().add_class("rec-title")
        head.pack_start(t, True, True, 0)
        self.time_lbl = Gtk.Label(label="00:00")
        self.time_lbl.get_style_context().add_class("rec-time")
        head.pack_start(self.time_lbl, False, False, 0)
        root.pack_start(head, False, False, 0)

        # Forma d'onda live (alti/bassi della voce)
        self.canvas = Gtk.DrawingArea()
        self.canvas.set_size_request(-1, 150)
        self.canvas.connect("draw", self._on_draw)
        root.pack_start(self.canvas, True, True, 0)

        # Barra di livello corrente
        self.level = Gtk.LevelBar()
        self.level.set_min_value(0.0); self.level.set_max_value(1.0)
        root.pack_start(self.level, False, False, 0)

        # Comandi
        ctr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.rec_btn = Gtk.Button(label="●  Registra")
        self.rec_btn.get_style_context().add_class("rec-go")
        self.rec_btn.connect("clicked", self._toggle_record)
        ctr.pack_start(self.rec_btn, False, False, 0)
        self.play_btn = Gtk.Button(label="▶  Riascolta")
        self.play_btn.set_sensitive(False)
        self.play_btn.connect("clicked", self._play_last)
        ctr.pack_start(self.play_btn, False, False, 0)
        open_btn = Gtk.Button(label="Cartella")
        open_btn.connect("clicked", self._open_folder)
        ctr.pack_end(open_btn, False, False, 0)
        root.pack_start(ctr, False, False, 0)

        self.status = Gtk.Label(label="Microfono: in ascolto (parla per vedere il livello).")
        self.status.set_xalign(0)
        self.status.get_style_context().add_class("rec-sub")
        root.pack_start(self.status, False, False, 0)

        self.connect("destroy", self._on_destroy)
        self.show_all()

        # Avvia cattura (monitor livello) + ridisegno periodico
        threading.Thread(target=self._cap_loop, daemon=True).start()
        GLib.timeout_add(33, self._tick)          # ~30 fps
        GLib.timeout_add(250, self._tick_time)

    # -------------------------------------------------- cattura
    def _cap_loop(self):
        cmd = ["arecord", "-q", "-f", "S16_LE", "-c", str(CH),
               "-r", str(RATE), "-t", "raw"]
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL)
        except (OSError, FileNotFoundError):
            GLib.idle_add(self._no_mic)
            return
        nbytes = CHUNK * BYTES
        while not self._stop:
            data = self.proc.stdout.read(nbytes)
            if not data:
                break
            cnt = len(data) // 2
            if cnt:
                vals = struct.unpack("<%dh" % cnt, data[:cnt * 2])
                peak = max((abs(v) for v in vals), default=0) / 32768.0
            else:
                peak = 0.0
            self.peak = peak
            # La forma d'onda avanza SOLO se c'e' segnale o durante la
            # registrazione: da fermo (silenzio, non in registrazione) resta
            # statica invece di scorrere all'infinito. Il livello istantaneo
            # (LevelBar) continua comunque ad aggiornarsi da self.peak.
            if self.recording or peak > 0.02:
                self.levels.append(peak)
                if len(self.levels) > NBARS:
                    self.levels.pop(0)
            if self.recording and self.wav is not None:
                try:
                    self.wav.writeframes(data)
                    self.frames += cnt
                except Exception:          # noqa: BLE001
                    pass

    def _no_mic(self):
        self.status.set_text("Nessun microfono disponibile (arecord non parte).")
        self.rec_btn.set_sensitive(False)
        return False

    # -------------------------------------------------- disegno
    def _tick(self):
        self.canvas.queue_draw()
        self.level.set_value(min(1.0, self.peak))
        return True

    def _tick_time(self):
        if self.recording:
            el = int(GLib.get_monotonic_time() / 1e6 - self._start_mono)
            self.time_lbl.set_text("%02d:%02d" % (el // 60, el % 60))
        return True

    def _on_draw(self, area, cr):
        w = area.get_allocated_width()
        h = area.get_allocated_height()
        cr.set_source_rgb(*GROUND)
        cr.paint()
        # linea centrale
        cr.set_source_rgb(*DIM)
        cr.set_line_width(1)
        cr.move_to(0, h / 2); cr.line_to(w, h / 2); cr.stroke()
        n = len(self.levels)
        if n == 0:
            return False
        bw = w / float(n)
        col = ALARM if self.recording else ACCENT
        cr.set_source_rgb(*col)
        for i, lv in enumerate(self.levels):
            bh = max(1.0, lv * (h * 0.92))
            x = i * bw
            cr.rectangle(x + bw * 0.15, (h - bh) / 2, max(1.0, bw * 0.7), bh)
        cr.fill()
        return False

    # -------------------------------------------------- record / play
    def _toggle_record(self, _b):
        if self.recording:
            self.recording = False
            try:
                if self.wav:
                    self.wav.close()
            except Exception:              # noqa: BLE001
                pass
            self.wav = None
            self.rec_btn.set_label("●  Registra")
            self.rec_btn.get_style_context().remove_class("rec-stop")
            self.rec_btn.get_style_context().add_class("rec-go")
            if self.last_file:
                self.play_btn.set_sensitive(True)
                self.status.set_text("Salvato: %s" % self.last_file)
            return
        # start
        try:
            os.makedirs(OUTDIR, exist_ok=True)
            path = os.path.join(
                OUTDIR, "rec-%s.wav" % datetime.now().strftime("%Y%m%d-%H%M%S"))
            w = wave.open(path, "wb")
            w.setnchannels(CH); w.setsampwidth(BYTES); w.setframerate(RATE)
            self.wav = w
            self.last_file = path
            self.frames = 0
            self._start_mono = GLib.get_monotonic_time() / 1e6
            self.recording = True
            self.time_lbl.set_text("00:00")
            self.rec_btn.set_label("■  Stop")
            self.rec_btn.get_style_context().remove_class("rec-go")
            self.rec_btn.get_style_context().add_class("rec-stop")
            self.status.set_text("Registrazione in corso...")
        except Exception as e:             # noqa: BLE001
            self.status.set_text("Impossibile registrare: %s" % e)

    def _play_last(self, _b):
        if not self.last_file or not os.path.exists(self.last_file):
            return
        try:
            subprocess.Popen(["aplay", "-q", self.last_file],
                             stderr=subprocess.DEVNULL)
            self.status.set_text("Riproduco: %s" % os.path.basename(self.last_file))
        except (OSError, FileNotFoundError):
            self.status.set_text("aplay non disponibile.")

    def _open_folder(self, _b):
        try:
            os.makedirs(OUTDIR, exist_ok=True)
            subprocess.Popen(["pcmanfm", OUTDIR], stderr=subprocess.DEVNULL)
        except (OSError, FileNotFoundError):
            self.status.set_text("Cartella: %s" % OUTDIR)

    def _on_destroy(self, _w):
        self._stop = True
        try:
            if self.recording and self.wav:
                self.wav.close()
        except Exception:                  # noqa: BLE001
            pass
        try:
            if self.proc:
                self.proc.terminate()
        except Exception:                  # noqa: BLE001
            pass
        Gtk.main_quit()


def main():
    Recorder()
    Gtk.main()


if __name__ == "__main__":
    main()
