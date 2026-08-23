"""Pannello stile MATE per NexusSec OS.

Barra nativa GTK3 con icone simboliche cyan, agganciabile in basso o in
alto (configurabile da ~/.config/nxs/panel.conf, vedi panelcfg.py):

  [menu] [term][file][centro] | lista finestre... | [orologio][desktop]

La lista finestre viene da `wmctrl -l` (poll ~1s); il click attiva la
finestra o la minimizza se gia' attiva. Niente conky, niente tint2: solo
GTK3 + wmctrl. Le icone seguono il tema icone selezionato (Adwaita), il
colore cyan e' imposto via CSS (.nxs-panel button image).
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import threading
import time

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf  # noqa: E402

from .common import apply_css, have, run_bg  # noqa: E402
from . import panelcfg  # noqa: E402

# Sistema profili (pacchetto separato, nessuna dipendenza GTK). Se assente, il
# pannello resta pienamente funzionante senza la sezione profilo.
try:
    from nxs_profiles import model as profiles_model  # noqa: E402
except Exception:                                     # noqa: BLE001
    profiles_model = None

try:
    from nxs_profiles import isolation as profiles_iso  # noqa: E402
except Exception:                                       # noqa: BLE001
    profiles_iso = None

# Procedure guidate (wizard): soft-import, il menu mostra quelle del profilo.
try:
    from nxs_wizards import recipes as wiz_recipes  # noqa: E402
except Exception:                                   # noqa: BLE001
    wiz_recipes = None

# Categoria tool -> (etichetta leggibile, icona simbolica). Usate per le
# intestazioni di sezione e l'icona di ogni tool nel menu start.
TOOL_CATEGORIES = [
    ("recon",      ("Ricognizione",      "system-search-symbolic")),
    ("osint",      ("OSINT",             "find-location-symbolic")),
    ("web",        ("Web",               "applications-internet-symbolic")),
    ("password",   ("Password",          "dialog-password-symbolic")),
    ("bruteforce", ("Brute force",       "changes-prevent-symbolic")),
    ("wireless",   ("Wireless",          "network-wireless-symbolic")),
    ("sniffing",   ("Sniffing/Spoofing", "network-transmit-receive-symbolic")),
    ("vuln",       ("Analisi vulnerabilita", "dialog-warning-symbolic")),
    ("exploit",    ("Exploitation",      "application-x-executable-symbolic")),
    ("pivoting",   ("Pivoting/Tunnel",   "network-vpn-symbolic")),
    ("reverse",    ("Reverse engineering", "applications-engineering-symbolic")),
    ("crypto",     ("Crypto/Stego",      "dialog-password-symbolic")),
    ("hardware",   ("Hardware/SDR",      "audio-card-symbolic")),
    ("forensics",  ("Forensics",         "drive-harddisk-symbolic")),
    ("reporting",  ("Reporting",         "text-x-generic-symbolic")),
    ("anonymity",  ("Anonimato",         "security-high-symbolic")),
    ("other",      ("Altri strumenti",   "applications-utilities-symbolic")),
]
TOOL_CAT_LABEL = {k: v[0] for k, v in TOOL_CATEGORIES}
TOOL_CAT_ICON = {k: v[1] for k, v in TOOL_CATEGORIES}
TOOL_CAT_ORDER = [k for k, _ in TOOL_CATEGORIES]

PANEL_HEIGHT = panelcfg.PANEL_HEIGHT
POLL_MS = 1000

# Fusi orari offerti nel popup dell'orologio (cambio al volo senza aprire il
# Centro di Controllo). Il fuso corrente, se non in lista, viene aggiunto in cima.
COMMON_TZ = [
    "Europe/Rome", "Europe/London", "Europe/Paris", "Europe/Berlin",
    "Europe/Madrid", "Europe/Athens", "Europe/Moscow", "UTC",
    "America/New_York", "America/Chicago", "America/Denver",
    "America/Los_Angeles", "America/Sao_Paulo", "Asia/Dubai",
    "Asia/Kolkata", "Asia/Shanghai", "Asia/Tokyo", "Australia/Sydney",
]

# --- monitor di sistema (mini-grafici stile multiload) -----------------------
MON_HIST = 30          # campioni tenuti in ogni grafico
MON_MS = 1500          # intervallo di aggiornamento (ms)
# Dischi FISICI interi (no partizioni/loop/ram) per l'I/O da /proc/diskstats.
_DISK_RE = re.compile(r'^(sd[a-z]+|vd[a-z]+|hd[a-z]+|xvd[a-z]+|'
                      r'nvme\d+n\d+|mmcblk\d+)$')


# Finestre da NON mostrare nella tasklist: la finestra "desktop" di
# pcmanfm (--desktop) e simili. Il file manager vero ha come titolo il
# nome della cartella, quindi non viene filtrato.
_SKIP_TITLES = {"pcmanfm", "desktop", "pcmanfm-desktop", ""}


def _wmctrl_list():
    """Ritorna [(id, desktop, titolo)] delle finestre normali."""
    try:
        out = subprocess.run(["wmctrl", "-l"], capture_output=True,
                             text=True, timeout=3).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    wins = []
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        wid, desk, _host, title = parts
        if desk == "-1":          # finestre sticky/desktop escluse
            continue
        if title.strip().lower() in _SKIP_TITLES:   # desktop di pcmanfm
            continue
        wins.append((wid, desk, title))
    return wins


def _active_window():
    """ID esadecimale della finestra attiva (via Gdk, nessuna dipendenza)."""
    try:
        w = Gdk.Screen.get_default().get_active_window()
        if w is not None:
            return "0x%08x" % w.get_xid()
    except Exception:
        pass
    return None


def _icon_button(icon_name, tooltip, css_class="nxs-icon"):
    b = Gtk.Button()
    b.set_relief(Gtk.ReliefStyle.NONE)
    b.set_tooltip_text(tooltip)
    b.get_style_context().add_class(css_class)
    img = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.LARGE_TOOLBAR)
    b.set_image(img)
    b.set_always_show_image(True)
    return b


_FIELD_RE = re.compile(r'%[fFuUdDnNickvm]')


def _parse_exec(exec_str):
    """Exec di un .desktop -> argv, togliendo i codici di campo freedesktop
    (%f %F %u %U %i %c %k ...) che non si passano al lancio diretto."""
    cleaned = _FIELD_RE.sub("", exec_str).strip()
    try:
        return shlex.split(cleaned)
    except ValueError:
        return cleaned.split()


def _read_desktop(path):
    """Parsa la sola sezione [Desktop Entry] di un file .desktop -> dict."""
    entry = {}
    in_main = False
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.rstrip("\n")
                if line.startswith("["):
                    in_main = (line.strip() == "[Desktop Entry]")
                    continue
                if not in_main or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                entry[k.strip()] = v.strip()
    except OSError:
        return None
    return entry


def scan_desktop_apps():
    """App installate (freedesktop): scansiona ~/.local/share/applications e le
    directory di $XDG_DATA_DIRS (default /usr/local/share:/usr/share). Salta le
    voci NoDisplay/Hidden e i non-Application. Le dir utente vincono su quelle di
    sistema (dedup per nome-file). Ritorna lista ordinata per nome."""
    home = os.path.expanduser("~")
    xdg_data_home = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local/share")
    dirs = [os.path.join(xdg_data_home, "applications")]
    xdg_dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    dirs += [os.path.join(d, "applications") for d in xdg_dirs.split(":") if d]

    seen_files = set()
    apps = {}
    for d in dirs:
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for fn in names:
            if not fn.endswith(".desktop") or fn in seen_files:
                continue
            seen_files.add(fn)                      # dir utente (prima) ha priorita'
            e = _read_desktop(os.path.join(d, fn))
            if not e or e.get("Type") != "Application" or not e.get("Exec"):
                continue
            if e.get("NoDisplay", "").lower() == "true":
                continue
            if e.get("Hidden", "").lower() == "true":
                continue
            argv = _parse_exec(e["Exec"])
            if not argv:
                continue
            name = e.get("Name[it]") or e.get("Name") or fn[:-8]
            apps[name] = {
                "name": name,
                "argv": argv,
                "icon": e.get("Icon", "application-x-executable"),
                "terminal": e.get("Terminal", "").lower() == "true",
            }
    return sorted(apps.values(), key=lambda a: a["name"].lower())


def _app_image(icon):
    """Immagine per una voce app: icona con nome dal tema, o file se path assoluto."""
    try:
        if icon and icon.startswith("/") and os.path.exists(icon):
            pix = GdkPixbuf.Pixbuf.new_from_file_at_size(icon, 22, 22)
            return Gtk.Image.new_from_pixbuf(pix)
    except Exception:                                # noqa: BLE001
        pass
    return Gtk.Image.new_from_icon_name(icon or "application-x-executable",
                                        Gtk.IconSize.LARGE_TOOLBAR)


def _human(n):
    """Byte/s -> stringa compatta (es. 1536 -> '2K')."""
    for unit in ("B", "K", "M", "G"):
        if n < 1024 or unit == "G":
            return "%.0f%s" % (n, unit)
        n /= 1024.0


class _Meter(Gtk.DrawingArea):
    """Mini-grafico a barre (storia scorrevole) di una risorsa, valori 0..1."""
    def __init__(self, rgb):
        super().__init__()
        self.rgb = rgb
        self.hist = [0.0] * MON_HIST
        self.set_size_request(30, PANEL_HEIGHT - 12)
        self.connect("draw", self._draw)

    def push(self, v):
        v = 0.0 if v < 0 else (1.0 if v > 1 else v)
        self.hist.append(v)
        del self.hist[0]
        self.queue_draw()

    def _draw(self, _w, cr):
        w = self.get_allocated_width()
        h = self.get_allocated_height()
        cr.set_source_rgba(0.02, 0.06, 0.10, 0.85)   # sfondo scuro
        cr.rectangle(0, 0, w, h)
        cr.fill()
        r, g, b = self.rgb
        n = len(self.hist)
        if n >= 2:
            step = w / (n - 1)

            def yv(v):
                return h - 1 - (0.0 if v < 0 else (1.0 if v > 1 else v)) * (h - 2)
            # area riempita (sparkline stile multiload)
            cr.move_to(0, h)
            for i, v in enumerate(self.hist):
                cr.line_to(i * step, yv(v))
            cr.line_to((n - 1) * step, h)
            cr.close_path()
            cr.set_source_rgba(r, g, b, 0.30)
            cr.fill()
            # linea di contorno
            cr.set_source_rgba(r, g, b, 0.95)
            cr.set_line_width(1.2)
            for i, v in enumerate(self.hist):
                (cr.move_to if i == 0 else cr.line_to)(i * step, yv(v))
            cr.stroke()
        cr.set_source_rgba(0.10, 0.23, 0.32, 0.9)     # bordo tenue
        cr.set_line_width(1)
        cr.rectangle(0.5, 0.5, w - 1, h - 1)
        cr.stroke()


class LoadMonitor(Gtk.EventBox):
    """Applet risorse: mini-grafici CPU / RAM / Rete letti da /proc (nessuna
    dipendenza esterna). Clic -> Monitor risorse del Centro di Controllo."""
    def __init__(self):
        super().__init__()
        self.get_style_context().add_class("nxs-loadmon")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        box.set_valign(Gtk.Align.CENTER)
        self.cpu = _Meter((0.00, 0.898, 1.00))   # cyan
        self.mem = _Meter((0.40, 0.95, 0.65))    # verde
        self.net = _Meter((1.00, 0.72, 0.25))    # ambra
        self.disk = _Meter((0.66, 0.55, 1.00))   # viola (I/O disco)
        for m in (self.cpu, self.mem, self.net, self.disk):
            box.pack_start(m, False, False, 0)
        self.add(box)
        self.set_tooltip_text("Risorse di sistema (clic: Monitor)")
        self.connect("button-press-event", self._on_click)

        self._prev_cpu = self._read_cpu()
        self._prev_net = self._read_net()
        self._prev_disk = self._read_disk()
        self._net_peak = 64 * 1024.0
        self._disk_peak = 128 * 1024.0
        self._alive = True
        self.connect("destroy", lambda *_: setattr(self, "_alive", False))
        GLib.timeout_add(MON_MS, self._tick)

    def _on_click(self, _w, _e):
        run_bg(["nxs-control-center", "monitor"])
        return True

    @staticmethod
    def _read_cpu():
        try:
            with open("/proc/stat") as f:
                parts = f.readline().split()
            vals = [float(x) for x in parts[1:]]
            idle = vals[3] + (vals[4] if len(vals) > 4 else 0.0)  # idle+iowait
            return idle, sum(vals)
        except (OSError, ValueError, IndexError):
            return 0.0, 0.0

    @staticmethod
    def _read_mem():
        try:
            info = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    k, _, rest = line.partition(":")
                    info[k] = float(rest.split()[0])
            total = info.get("MemTotal", 0.0)
            avail = info.get("MemAvailable", info.get("MemFree", 0.0))
            return 0.0 if total <= 0 else 1.0 - avail / total
        except (OSError, ValueError, IndexError):
            return 0.0

    @staticmethod
    def _read_net():
        tot = 0.0
        try:
            with open("/proc/net/dev") as f:
                for line in f.readlines()[2:]:
                    iface, _, data = line.partition(":")
                    if iface.strip() == "lo":
                        continue
                    cols = data.split()
                    tot += float(cols[0]) + float(cols[8])   # rx + tx bytes
        except (OSError, ValueError, IndexError):
            pass
        return tot

    @staticmethod
    def _read_disk():
        """Byte totali letti+scritti dai dischi FISICI (da /proc/diskstats).
        Solo i dischi interi (sd*, vd*, nvme*n*, mmcblk*, hd*, xvd*) per non
        contare due volte disco + partizioni; esclude loop/ram. Settori * 512."""
        sectors = 0.0
        try:
            with open("/proc/diskstats") as f:
                for line in f:
                    p = line.split()
                    if len(p) < 11:
                        continue
                    if not _DISK_RE.match(p[2]):
                        continue
                    sectors += float(p[5]) + float(p[9])     # letti + scritti
        except (OSError, ValueError, IndexError):
            pass
        return sectors * 512.0

    def _tick(self):
        idle, total = self._read_cpu()
        pidle, ptotal = self._prev_cpu
        dt = total - ptotal
        cpu = 0.0 if dt <= 0 else max(0.0, 1.0 - (idle - pidle) / dt)
        self._prev_cpu = (idle, total)
        self.cpu.push(cpu)

        mem = self._read_mem()
        self.mem.push(mem)

        cur = self._read_net()
        rate = max(0.0, cur - self._prev_net) / (MON_MS / 1000.0)
        self._prev_net = cur
        # auto-scala sul picco osservato (decadimento lento), minimo 64K/s
        self._net_peak = max(self._net_peak * 0.98, rate, 64 * 1024.0)
        self.net.push(rate / self._net_peak)

        dcur = self._read_disk()
        drate = max(0.0, dcur - self._prev_disk) / (MON_MS / 1000.0)
        self._prev_disk = dcur
        self._disk_peak = max(self._disk_peak * 0.98, drate, 128 * 1024.0)
        self.disk.push(drate / self._disk_peak)

        self.set_tooltip_text(
            "CPU %d%%   RAM %d%%   Rete %s/s   Disco %s/s   (clic: Monitor)"
            % (round(cpu * 100), round(mem * 100), _human(rate), _human(drate)))
        return self._alive


class Panel(Gtk.Window):
    def __init__(self, monitor_index=None):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        apply_css()
        # Su quale monitor si ancora questa barra: indice Gdk (None = primario).
        # In multi-monitor si crea UNA Panel per schermo (vedi run()), cosi' la
        # barra e il menu compaiono anche sul monitor esterno.
        self._monitor_index = monitor_index
        self.position = panelcfg.get_position()
        self.set_type_hint(Gdk.WindowTypeHint.DOCK)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.stick()
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        ctx = self.get_style_context()
        ctx.add_class("nxs-panel")
        if self.position == "top":
            ctx.add_class("nxs-panel-top")

        self._task_btns = {}      # id -> Gtk.Button
        self._last_sig = None
        self._popups = {}         # key -> finestra toplevel aperta
        self._popup_closed = {}   # key -> timestamp ultima chiusura (anti-rimbalzo)
        # Flag di vita: in multi-monitor le barre si ricostruiscono (hotplug),
        # ma i GLib.timeout restano attivi anche dopo destroy -> i callback
        # ritornano self._alive per auto-cancellarsi sulla barra distrutta.
        self._alive = True
        self.connect("destroy", lambda *_: setattr(self, "_alive", False))

        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.add(root)

        # --- Sinistra: menu + lanciatori (icone) ---
        left = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        root.pack_start(left, False, False, 0)

        menu_btn = _icon_button("open-menu-symbolic", "Menu NexusSec", "nxs-menu")
        menu_btn.connect("clicked", self._on_menu)
        left.pack_start(menu_btn, False, False, 0)

        left.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL),
                        False, False, 0)

        for icon, tip, cmd in (
            ("utilities-terminal-symbolic", "Terminale", ["nxs-terminal"]),
            ("system-file-manager-symbolic", "File", ["pcmanfm"]),
            ("accessories-text-editor-symbolic", "Editor di testo", ["pluma"]),
            ("nxs-browser", "NexusSec Browser", ["nxs-browser"]),
            ("preferences-system-symbolic", "Centro di Controllo",
             ["nxs-control-center"]),
        ):
            b = _icon_button(icon, tip)
            b.connect("clicked", lambda _w, c=cmd: run_bg(c))
            left.pack_start(b, False, False, 0)

        left.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL),
                        False, False, 0)

        # --- Centro: lista finestre ---
        self.tasks = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        root.pack_start(self.tasks, True, True, 0)

        # --- Destra (da DESTRA a sinistra): mostra-desktop, orologio+data,
        #     WiFi, Schermi, monitor risorse. In pack_start (sinistra->destra)
        #     l'ordine e' quindi: monitor, Schermi, WiFi, orologio, desktop. ---
        right = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        root.pack_end(right, False, False, 0)

        # Mini-grafici CPU/RAM/Rete/Disco (stile multiload), clic -> Monitor.
        self.loadmon = LoadMonitor()
        right.pack_start(self.loadmon, False, False, 4)

        right.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL),
                         False, False, 0)

        # Applet Schermi (xrandr) e WiFi (scan/connessione): compaiono sempre;
        # se manca l'hardware il popup lo segnala.
        scr_btn = _icon_button("video-display-symbolic", "Schermi")
        scr_btn.connect("clicked", self._toggle_screens)
        right.pack_start(scr_btn, False, False, 0)

        wifi_btn = _icon_button("network-wireless-symbolic", "Reti WiFi")
        wifi_btn.connect("clicked", self._toggle_wifi)
        right.pack_start(wifi_btn, False, False, 0)

        # Audio (volume/uscite via wpctl-PipeWire): clic = popup, rotella = +/-.
        self.vol_btn = _icon_button("audio-volume-medium-symbolic", "Audio")
        self.vol_btn.connect("clicked", self._toggle_volume)
        self.vol_btn.add_events(Gdk.EventMask.SCROLL_MASK)
        self.vol_btn.connect("scroll-event", self._vol_scroll)
        right.pack_start(self.vol_btn, False, False, 0)

        # Bluetooth (bluetoothctl-BlueZ): clic = popup accensione/scan/connetti.
        self.bt_btn = _icon_button("bluetooth-active-symbolic", "Bluetooth")
        self.bt_btn.connect("clicked", self._toggle_bluetooth)
        right.pack_start(self.bt_btn, False, False, 0)

        right.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL),
                         False, False, 0)

        clock_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        clock_box.set_valign(Gtk.Align.CENTER)
        self.clock = Gtk.Label()
        self.clock.get_style_context().add_class("nxs-clock")
        self.date = Gtk.Label()
        self.date.get_style_context().add_class("nxs-clock-date")
        clock_box.pack_start(self.clock, False, False, 0)
        clock_box.pack_start(self.date, False, False, 0)

        # Pulsante orologio: apre/chiude il calendario (finestra toplevel).
        self.clock_btn = Gtk.Button()
        self.clock_btn.set_relief(Gtk.ReliefStyle.NONE)
        self.clock_btn.set_tooltip_text("Calendario")
        self.clock_btn.get_style_context().add_class("nxs-clock-btn")
        self.clock_btn.add(clock_box)
        self.clock_btn.connect("clicked", self._toggle_calendar)
        right.pack_start(self.clock_btn, False, False, 0)

        sd = _icon_button("user-desktop-symbolic", "Mostra il desktop")
        sd.connect("clicked", self._on_show_desktop)
        right.pack_start(sd, False, False, 0)

        self._place()
        self.connect("screen-changed", lambda *_: self._place())
        self.connect("realize", self._on_realize)

        self._tick_clock()
        self._refresh_tasks()
        GLib.timeout_add(POLL_MS, self._refresh_tasks)
        GLib.timeout_add(1000, self._tick_clock)
        # icone audio/bluetooth aggiornate periodicamente (non bloccante)
        self._refresh_media()
        GLib.timeout_add(4000, self._refresh_media)

    # --- geometria ---
    def _place(self):
        scr = self.get_screen()
        n = scr.get_n_monitors() if hasattr(scr, "get_n_monitors") else 1
        mon = self._monitor_index
        # Indice non valido (monitor scollegato) -> ripiega sul primario.
        if mon is None or mon < 0 or mon >= n:
            mon = (scr.get_primary_monitor()
                   if hasattr(scr, "get_primary_monitor") else 0)
        geo = scr.get_monitor_geometry(mon)
        self._geo = geo
        self.set_size_request(geo.width, PANEL_HEIGHT)
        if self.position == "top":
            self.move(geo.x, geo.y)
        else:
            self.move(geo.x, geo.y + geo.height - PANEL_HEIGHT)

    def _on_realize(self, _w):
        # Lo spazio e' riservato dal margine di Openbox (rc.xml), aggiornato
        # da panelcfg.move_panel quando si cambia posizione.
        self._place()

    # --- popup come finestre toplevel keep_above (i Gtk.Popover su Openbox
    #     senza compositor finivano "sotto" lo sfondo) ---
    def _spawn_popup(self, key, content, align, autoclose=True):
        # toggle: se gia' aperto, chiudi
        if key in self._popups:
            self._popups.pop(key).destroy()
            self._popup_closed[key] = time.time()
            return
        # anti-rimbalzo: evita la riapertura immediata dopo il focus-out
        if time.time() - self._popup_closed.get(key, 0) < 0.25:
            return

        w = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        w.set_decorated(False)
        w.set_resizable(False)
        w.set_skip_taskbar_hint(True)
        w.set_skip_pager_hint(True)
        w.set_keep_above(True)
        w.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        w.set_screen(self.get_screen())
        w.get_style_context().add_class("nxs-popup")
        w.add(content)
        w.show_all()

        _min, nat = w.get_preferred_size()
        pw, ph = nat.width, nat.height
        geo = self._geo
        margin = 6
        # Clamp: il popup non deve mai superare l'area disponibile (altrimenti il
        # bordo alto esce dallo schermo e le prime voci diventano irraggiungibili).
        avail_h = geo.height - PANEL_HEIGHT - margin
        if ph > avail_h:
            ph = avail_h
            w.resize(pw, ph)
        if align == "right":
            x = geo.x + geo.width - pw - margin
        else:
            x = geo.x + margin
        if self.position == "top":
            y = geo.y + PANEL_HEIGHT
        else:
            y = geo.y + geo.height - PANEL_HEIGHT - ph
        w.move(x, y)

        def on_focus_out(*_a):
            if key in self._popups:
                self._popups.pop(key, None)
                self._popup_closed[key] = time.time()
                w.destroy()
            return False
        # autoclose=False per i popup con widget interattivi (combo/spin): il
        # dropdown della combo ruba il focus -> il focus-out chiudeva tutto e non
        # si riusciva a scegliere il fuso/ora. Quelli si chiudono con Esc, con un
        # nuovo clic sul pulsante, o dopo "Imposta".
        if autoclose:
            w.connect("focus-out-event", on_focus_out)

        def on_key(_w, ev):
            if ev.keyval == Gdk.KEY_Escape:
                self._close_popup(key)
                return True
            return False
        w.connect("key-press-event", on_key)
        self._popups[key] = w
        w.present()

    def _close_popup(self, key):
        if key in self._popups:
            self._popups.pop(key).destroy()
            self._popup_closed[key] = time.time()

    # --- menu NexusSec (stile Windows, con banda verticale) ---
    def _menu_item(self, key, icon, label, cmd=None, move_to=None, confirm=None):
        b = Gtk.Button()
        b.set_relief(Gtk.ReliefStyle.NONE)
        b.get_style_context().add_class("nxs-menu-item")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        img = Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.LARGE_TOOLBAR)
        lab = Gtk.Label(label=label)
        lab.set_xalign(0)
        box.pack_start(img, False, False, 0)
        box.pack_start(lab, True, True, 0)
        b.add(box)

        def on_click(_w):
            self._close_popup(key)
            if move_to is not None:
                panelcfg.move_panel(move_to)
                return
            if cmd is None:
                return
            if confirm:
                d = Gtk.MessageDialog(
                    transient_for=None, modal=True,
                    message_type=Gtk.MessageType.QUESTION,
                    buttons=Gtk.ButtonsType.YES_NO, text=confirm)
                d.set_keep_above(True)
                resp = d.run()
                d.destroy()
                if resp != Gtk.ResponseType.YES:
                    return
            run_bg(cmd)
        b.connect("clicked", on_click)
        return b

    # --- sistema profili ---
    def _profile_data(self):
        """Dati del profilo corrente, o {} se il sistema profili e' assente."""
        if profiles_model is None:
            return {}
        try:
            return profiles_model.profile_data()
        except Exception:                # noqa: BLE001
            return {}

    def _profile_tools(self):
        if profiles_model is None:
            return []
        try:
            return profiles_model.profile_tools()
        except Exception:                # noqa: BLE001
            return []

    def _tool_meta(self, tool):
        """(category, method, description) del tool da repo.json (con fallback)."""
        data = {}
        if profiles_model is not None:
            try:
                data = profiles_model.tool_data(tool) or {}
            except Exception:            # noqa: BLE001
                data = {}
        cat = data.get("category") or "other"
        if cat not in TOOL_CAT_LABEL:
            cat = "other"
        return cat, (data.get("method") or "apk"), (data.get("description") or "")

    def _tool_installed_fast(self, tool):
        """Stato installato 'rapido' per il pallino del menu, SENZA subprocess
        per-tool (il menu deve aprirsi subito). Usa gli insiemi precalcolati in
        _on_menu: pacchetti Kali installati (file di stato) e immagini container
        presenti (una sola 'podman images'). None se non determinabile."""
        if profiles_iso is None:
            return None
        try:
            data = profiles_model.tool_data(tool) if profiles_model else {}
            method = data.get("method") or "apk"
            # kali: il binario NON e' nel PATH host (vive nel container Kali
            # condiviso). Lo stato vero e' nel file kali_installed.txt.
            if method == "kali":
                pkgset = getattr(self, "_kali_pkgset", None)
                if pkgset is None:
                    return None
                return (data.get("apt") or tool) in pkgset
            # container: immagine dedicata -> installato se l'immagine e' locale.
            if method == "container":
                imgset = getattr(self, "_img_set", None)
                img = data.get("image", "")
                if imgset is None or not img:
                    return None
                return img in imgset or img.rsplit(":", 1)[0] in imgset
            # apk/pip/git: l'eseguibile finisce nel PATH host.
            binname = data.get("bin", tool)
            if profiles_iso.have(binname) or profiles_iso.have(tool):
                return True
            return False
        except Exception:                # noqa: BLE001
            return None

    def _tool_row(self, tool):
        """Riga-tool del menu: icona categoria + nome + pallino di stato.
        Ritorna (widget, testo_ricerca) per il filtro live."""
        cat, method, desc = self._tool_meta(tool)
        icon = TOOL_CAT_ICON.get(cat, "utilities-terminal-symbolic")
        installed = self._tool_installed_fast(tool)

        b = Gtk.Button()
        b.set_relief(Gtk.ReliefStyle.NONE)
        b.get_style_context().add_class("nxs-menu-item")
        b.get_style_context().add_class("nxs-tool-item")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        img = Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.LARGE_TOOLBAR)
        lab = Gtk.Label(label=tool)
        lab.set_xalign(0)
        # Pallino di stato: verde=installato, ambra=da scaricare, grigio=ignoto.
        dot = Gtk.Label(label="●")
        dot.get_style_context().add_class("nxs-tool-dot")
        if installed is True:
            dot.get_style_context().add_class("ok")
            dot.set_tooltip_text("Installato")
        elif installed is False:
            dot.get_style_context().add_class("todo")
            dot.set_tooltip_text("Da scaricare (%s)" % method)
        else:
            dot.get_style_context().add_class("unknown")
            dot.set_tooltip_text("Stato sconosciuto (%s)" % method)
        box.pack_start(img, False, False, 0)
        box.pack_start(lab, True, True, 0)
        box.pack_start(dot, False, False, 0)
        b.add(box)
        if desc:
            b.set_tooltip_text("%s  [%s]" % (desc, method))

        cmd = ["lxterminal", "-e", "nxs-run-tool %s" % tool]

        def on_click(_w):
            self._close_popup("menu")
            run_bg(cmd)
        b.connect("clicked", on_click)
        return b, ("%s %s %s" % (tool, cat, desc)).lower()

    def _on_menu(self, _btn):
        # Stato installato precalcolato UNA volta per apertura (non per-tool):
        #  - _kali_pkgset: pacchetti gia' presenti nell'ambiente Kali condiviso
        #    (lettura del file di stato) -> pallino corretto per i tool 'kali';
        #  - _img_set: immagini container locali (una sola 'podman images')
        #    -> pallino corretto per i tool 'container'.
        # Cosi' dopo un'installazione il pallino diventa "installato" alla
        # riapertura del menu, senza rallentarne l'apertura.
        self._kali_pkgset = None
        self._img_set = None
        if profiles_iso is not None:
            try:
                self._kali_pkgset = set(profiles_iso.kali_env_pkgs())
            except Exception:            # noqa: BLE001
                self._kali_pkgset = None
            try:
                self._img_set = profiles_iso.local_images()
            except Exception:            # noqa: BLE001
                self._img_set = None

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        hbox.get_style_context().add_class("nxs-startmenu")

        # Banda verticale brandizzata
        strip = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        strip.get_style_context().add_class("nxs-menu-strip")
        strip.set_valign(Gtk.Align.FILL)
        brand = Gtk.Label(label="NexusSec OS")
        brand.get_style_context().add_class("brand")
        brand.set_angle(90)
        # Sotto-etichetta = profilo operativo corrente (se disponibile).
        prof = self._profile_data()
        sub_text = prof.get("name", "64-bit") if prof else "64-bit"
        sub = Gtk.Label(label=sub_text)
        sub.get_style_context().add_class("brand-sub")
        sub.set_angle(90)
        # Ancorate IN BASSO (pack_end): il nome parte ~14px dal fondo della
        # barra colorata e legge verso l'alto, senza uscire dallo schermo.
        # Ordine dal basso: [14px] NexusSec OS, poi il profilo sopra.
        strip.pack_end(brand, False, False, 14)
        strip.pack_end(sub, False, False, 0)
        hbox.pack_start(strip, False, False, 0)

        lst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        lst.get_style_context().add_class("nxs-startmenu-list")
        # Con profili ricchi la lista supera l'altezza schermo: la mettiamo in
        # uno ScrolledWindow che cresce fino allo spazio disponibile e poi
        # scorre (rotellina/barra), cosi nessuna voce resta tagliata in alto.
        scroller = Gtk.ScrolledWindow()
        scroller.get_style_context().add_class("nxs-startmenu-scroll")
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_propagate_natural_width(True)
        scroller.set_propagate_natural_height(True)
        # Riservo ~220px per ricerca + footer fisso (Esci/Riavvia/Spegni), cosi'
        # il footer non viene mai schiacciato e i tool scorrono nello spazio sopra.
        avail_h = max(160, self._geo.height - PANEL_HEIGHT - 24 - 220)
        scroller.set_max_content_height(avail_h)
        scroller.add(lst)
        # Scorrevole SI', ma NON deve auto-scrollare da solo: di default lo
        # ScrolledWindow segue il focus (quando una voce prende il focus salta
        # a quella voce -> il menu si apriva gia' scrollato). Neutralizziamo gli
        # adjustment di focus del viewport interno: cosi' lo scroll lo decide
        # solo l'utente (rotellina/barra) e il menu si apre fermo all'inizio.
        _vp = scroller.get_child()
        if _vp is not None:
            _vp.set_focus_vadjustment(Gtk.Adjustment())
            _vp.set_focus_hadjustment(Gtk.Adjustment())

        # Colonna destra = [ricerca] + [lista scrollabile]. La ricerca resta
        # fissa in alto e filtra dal vivo le righe-tool.
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        search = Gtk.SearchEntry()
        search.get_style_context().add_class("nxs-menu-search")
        search.set_placeholder_text("Cerca strumento...")
        col.pack_start(search, False, False, 0)
        col.pack_start(scroller, True, True, 0)
        hbox.pack_start(col, True, True, 0)

        # Registri per il filtro live: ogni voce-tool e ogni intestazione di
        # categoria con le sue voci, per nascondere le sezioni vuote.
        tool_rows = []        # [(widget, testo_ricerca)]
        cat_sections = []     # [(header_widget, [row_widget, ...])]

        def sep():
            lst.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL),
                           False, False, 0)

        # Rivela una riga collassata: NB con set_no_show_all(True) il show_all
        # iniziale salta la riga E I SUOI FIGLI (icona+etichetta), quindi un
        # semplice set_visible(True) mostrerebbe solo il bottone vuoto (si vedeva
        # l'hover ma NON il testo). Va tolto il flag e fatto show_all() sulla riga.
        def _reveal_row(r):
            r.set_no_show_all(False)
            r.show_all()

        # --- Voce PROFILO in CIMA ---
        # E' l'azione firma della distro (cambia modalita' operativa) e deve
        # restare la PRIMA voce, sempre visibile senza scorrere. Col riordino le
        # utilita' sono sotto, i tool ancora piu' giu'. (Se finisse in fondo,
        # come nella prima versione del riordino, sparirebbe sotto la piega.)
        prof = self._profile_data()
        if prof:
            lst.pack_start(
                self._menu_item("menu", prof.get("icon", "system-users"),
                                "Profilo: %s  (cambia)" % prof.get("name", ""),
                                ["nxs-profile"], None, None),
                False, False, 0)
            sep()

        move_to = "bottom" if self.position == "top" else "top"
        move_label = ("Sposta pannello in basso" if move_to == "bottom"
                      else "Sposta pannello in alto")
        move_icon = "go-bottom-symbolic" if move_to == "bottom" else "go-top-symbolic"

        # (icona, etichetta, comando, sposta_a, conferma)
        # Voci SCORREVOLI (app e utilita'): vanno nella lista che scorre.
        app_items = [
            ("preferences-system-symbolic", "Centro di Controllo",
             ["nxs-control-center"], None, None),
            ("utilities-terminal-symbolic", "Terminale", ["nxs-terminal"], None, None),
            ("system-file-manager-symbolic", "File manager", ["pcmanfm"], None, None),
            ("accessories-text-editor-symbolic", "Editor di testo", ["pluma"], None, None),
            ("nxs-browser", "NexusSec Browser", ["nxs-browser"], None, None),
            ("system-run-symbolic", "Procedure guidate", ["nxs-wizard"], None, None),
            (None, None, None, None, None),
            ("computer-symbolic", "Info sistema",
             ["nxs-control-center", "sysinfo"], None, None),
            ("applications-system-symbolic", "Monitor risorse",
             ["nxs-control-center", "monitor"], None, None),
            ("system-software-install-symbolic", "Gestore pacchetti",
             ["nxs-control-center", "pacchetti"], None, None),
            ("network-wired-symbolic", "Rete",
             ["nxs-control-center", "rete"], None, None),
            (None, None, None, None, None),
            (move_icon, move_label, None, move_to, None),
            ("view-refresh-symbolic", "Riavvia Openbox",
             ["openbox", "--restart"], None, None),
        ]
        for icon, label, cmd, mv, conf in app_items:
            if icon is None:
                sep()
            else:
                lst.pack_start(
                    self._menu_item("menu", icon, label, cmd, mv, conf),
                    False, False, 0)
        sep()

        # --- Sezione APPLICAZIONI: app installate via .desktop (LibreOffice,
        #     GIMP, VLC, ...). Cosi' qualunque app apk compare nel menu senza
        #     configurazione. Fisarmonica come le categorie tool; le righe
        #     entrano nel filtro di ricerca. ---
        desktop_apps = scan_desktop_apps()
        if desktop_apps:
            state_a = {"collapsed": True}
            app_rows = []
            header_a = Gtk.Button()
            header_a.get_style_context().add_class("nxs-menu-cat")
            hlbl_a = Gtk.Label()
            hlbl_a.set_xalign(0)
            hlbl_a.set_markup("▸  APPLICAZIONI  <small>(%d)</small>" % len(desktop_apps))
            header_a.add(hlbl_a)
            lst.pack_start(header_a, False, False, 0)
            for app in desktop_apps:
                row = Gtk.Button()
                row.set_relief(Gtk.ReliefStyle.NONE)
                row.get_style_context().add_class("nxs-menu-item")
                row.get_style_context().add_class("nxs-tool-item")
                rbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                rbox.pack_start(_app_image(app["icon"]), False, False, 0)
                rlab = Gtk.Label(label=app["name"])
                rlab.set_xalign(0)
                rbox.pack_start(rlab, True, True, 0)
                row.add(rbox)
                row.set_no_show_all(True)          # parte collassato

                def _on_app(_w, a=app):
                    self._close_popup("menu")
                    self._launch_desktop(a)
                row.connect("clicked", _on_app)
                lst.pack_start(row, False, False, 0)
                tool_rows.append((row, app["name"].lower()))
                app_rows.append(row)

            def _toggle_a(_btn, lbl=hlbl_a, rows=app_rows, st=state_a,
                          reveal=_reveal_row):
                st["collapsed"] = not st["collapsed"]
                arrow = "▸" if st["collapsed"] else "▾"
                lbl.set_markup("%s  APPLICAZIONI  <small>(%d)</small>"
                               % (arrow, len(rows)))
                for r in rows:
                    r.hide() if st["collapsed"] else reveal(r)
            header_a.connect("clicked", _toggle_a)
            cat_sections.append((header_a, app_rows, state_a))
            sep()

        # --- Sezione PROFILO: procedure guidate + tool del profilo corrente
        #     (la voce "Profilo: ... (cambia)" e' gia' in cima, vedi sopra) ---
        if prof:
            # Procedure guidate del profilo corrente: un clic apre il wizard
            # gia' sul form giusto (es. "Pentest rapido" chiede l'IP e fa tutto).
            if wiz_recipes is not None and profiles_model is not None:
                try:
                    pkey = profiles_model.current_profile()
                    wizs = wiz_recipes.for_profile(pkey)
                except Exception:            # noqa: BLE001
                    wizs = []
                for wid, w in wizs:
                    lst.pack_start(
                        self._menu_item(
                            "menu", w.get("icon", "system-run-symbolic"),
                            "  %s (procedura guidata)" % w.get("name", wid),
                            ["nxs-wizard", "gui", wid], None, None),
                        False, False, 0)

            # Tool del profilo RAGGRUPPATI per categoria, in ordine fisso.
            # Ogni voce mostra icona di categoria + pallino di stato; le
            # intestazioni di sezione si nascondono quando il filtro le svuota.
            by_cat = {}
            for tool in self._profile_tools():
                cat, _m, _d = self._tool_meta(tool)
                by_cat.setdefault(cat, []).append(tool)

            # Sottomenu per categoria a FISARMONICA: con centinaia di tool
            # (arsenale Kali completo) una lista piatta sarebbe ingestibile.
            # Di default si vedono solo le intestazioni (collassate); un clic
            # espande la categoria. Il filtro di ricerca espande al volo i
            # risultati ignorando lo stato collassato.
            for cat in TOOL_CAT_ORDER:
                tools = by_cat.get(cat)
                if not tools:
                    continue
                state = {"collapsed": True}
                section_rows = []
                # Uppercase in Python (text-transform e' GTK4-only).
                header = Gtk.Button()
                header.get_style_context().add_class("nxs-menu-cat")
                hlbl = Gtk.Label()
                hlbl.set_xalign(0)
                hlbl.set_markup("▸  %s  <small>(%d)</small>"
                                % (TOOL_CAT_LABEL[cat].upper(), len(tools)))
                header.add(hlbl)
                lst.pack_start(header, False, False, 0)
                for tool in sorted(tools):
                    row, haystack = self._tool_row(tool)
                    row.set_no_show_all(True)     # parte collassato (no flash)
                    lst.pack_start(row, False, False, 0)
                    tool_rows.append((row, haystack))
                    section_rows.append(row)

                def _toggle(_btn, lbl=hlbl, name=TOOL_CAT_LABEL[cat],
                            rows=section_rows, st=state, reveal=_reveal_row):
                    st["collapsed"] = not st["collapsed"]
                    arrow = "▸" if st["collapsed"] else "▾"
                    lbl.set_markup("%s  %s  <small>(%d)</small>"
                                   % (arrow, name.upper(), len(rows)))
                    for r in rows:
                        r.hide() if st["collapsed"] else reveal(r)
                header.connect("clicked", _toggle)
                cat_sections.append((header, section_rows, state))
            sep()

        # --- Filtro live: nasconde righe-tool non corrispondenti e le
        #     intestazioni di categoria rimaste senza voci visibili ---
        def on_search(entry):
            q = entry.get_text().strip().lower()
            if q:
                # ricerca: mostra le righe che combaciano (ignora il collasso) e
                # le sole intestazioni con risultati. reveal mostra anche i figli.
                for row, hay in tool_rows:
                    _reveal_row(row) if q in hay else row.hide()
                for header, rows, _st in cat_sections:
                    header.set_visible(any(r.get_visible() for r in rows))
            else:
                # ricerca vuota: ripristina lo stato a fisarmonica (collassato).
                for header, rows, st in cat_sections:
                    header.set_visible(True)
                    for r in rows:
                        r.hide() if st["collapsed"] else _reveal_row(r)
        search.connect("search-changed", on_search)
        if not tool_rows:
            search.set_no_show_all(True)
            search.hide()

        # Voci di USCITA/SPEGNIMENTO: ancorate in un FOOTER FISSO fuori dallo
        # scroller, cosi' restano SEMPRE visibili anche con tanti tool (prima
        # finivano in coda alla lista scrollabile e sparivano sotto il bordo).
        footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        footer.get_style_context().add_class("nxs-startmenu-footer")
        footer.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL),
                          False, False, 0)
        power_items = [
            ("system-log-out-symbolic", "Esci (logout)",
             ["openbox", "--exit"], None, "Uscire dalla sessione (logout)?"),
            ("system-reboot-symbolic", "Riavvia il sistema",
             ["nxs-shutdown", "reboot"], None, "Riavviare il sistema?"),
            ("system-shutdown-symbolic", "Spegni",
             ["nxs-shutdown", "poweroff"], None, "Spegnere il sistema?"),
        ]
        for icon, label, cmd, mv, conf in power_items:
            footer.pack_start(self._menu_item("menu", icon, label, cmd, mv, conf),
                              False, False, 0)
        col.pack_end(footer, False, False, 0)

        self._spawn_popup("menu", hbox, align="left")

        # Apertura SEMPRE in cima: anche con gli adjustment di focus neutralizzati
        # il primo layout puo' lasciare il viewport a un offset != 0 (la voce che
        # prende il focus, la barra che si dimensiona...). Forziamo il valore a 0
        # DOPO che il popup ha calcolato la sua altezza, cosi' il menu nasce
        # mostrando subito le voci di base in cima (niente scroll iniziale).
        def _scroll_top():
            adj = scroller.get_vadjustment()
            if adj is not None:
                adj.set_value(adj.get_lower())
            return False
        GLib.idle_add(_scroll_top)

        # Focus alla ricerca per poter digitare subito (la ricerca e' FUORI dallo
        # scroller, quindi non sposta la lista). Lo rifacciamo dopo il reset dello
        # scroll con priorita' piu' bassa, cosi' l'ordine e': layout -> scroll 0
        # -> focus, e il menu resta fermo in cima.
        if tool_rows:
            GLib.idle_add(search.grab_focus, priority=GLib.PRIORITY_LOW)

    def _on_show_desktop(self, _w):
        if have("wmctrl"):
            run_bg(["wmctrl", "-k", "on"])

    def _launch_desktop(self, app):
        """Lancia un'app .desktop: in terminale se Terminal=true, altrimenti diretta."""
        argv = app["argv"]
        if app.get("terminal"):
            run_bg(["lxterminal", "-e", " ".join(argv)])
        else:
            run_bg(argv)

    # --- helper comando con output ---
    def _run_out(self, cmd, timeout=20):
        try:
            return subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=timeout).stdout
        except (OSError, subprocess.SubprocessError):
            return ""

    # --- applet WiFi (scan/connessione via nxs-wifi) ---
    # --- Audio (PipeWire/wpctl) e Bluetooth (BlueZ) --------------------------
    def _bg(self, cmd):
        """Esegue un comando in background (fire-and-forget), non blocca la UI."""
        threading.Thread(target=lambda: self._run_out(cmd, 8), daemon=True).start()

    def _refresh_media(self):
        def worker():
            pct = None; muted = False
            try:
                o = self._run_out(["nxs-audio", "get"]).split()
                pct = int(o[0]); muted = (o[1] == "1")
            except Exception:                       # noqa: BLE001
                pass
            try:
                bt = self._run_out(["nxs-bluetooth", "status"]).strip()
            except Exception:                       # noqa: BLE001
                bt = "noadapter"
            GLib.idle_add(self._apply_media_icons, pct, muted, bt)
        threading.Thread(target=worker, daemon=True).start()
        return True

    def _apply_media_icons(self, pct, muted, bt):
        if pct is None or muted or pct <= 0:
            ai = "audio-volume-muted-symbolic"
        elif pct < 34:
            ai = "audio-volume-low-symbolic"
        elif pct < 67:
            ai = "audio-volume-medium-symbolic"
        else:
            ai = "audio-volume-high-symbolic"
        self.vol_btn.set_image(Gtk.Image.new_from_icon_name(
            ai, Gtk.IconSize.LARGE_TOOLBAR))
        bi = "bluetooth-active-symbolic" if bt == "on" else "bluetooth-disabled-symbolic"
        self.bt_btn.set_image(Gtk.Image.new_from_icon_name(
            bi, Gtk.IconSize.LARGE_TOOLBAR))
        return False

    def _vol_scroll(self, _w, ev):
        up = down = False
        if ev.direction == Gdk.ScrollDirection.UP:
            up = True
        elif ev.direction == Gdk.ScrollDirection.DOWN:
            down = True
        elif ev.direction == Gdk.ScrollDirection.SMOOTH:
            _ok, _dx, dy = ev.get_scroll_deltas()
            up = dy < 0; down = dy > 0
        if up:
            self._bg(["nxs-audio", "up"])
        elif down:
            self._bg(["nxs-audio", "down"])
        GLib.timeout_add(200, self._refresh_media)
        return True

    def _toggle_volume(self, _btn):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.get_style_context().add_class("nxs-calbox")
        box.set_size_request(300, -1)
        title = Gtk.Label(); title.set_markup("<b>Audio</b>"); title.set_xalign(0)
        box.pack_start(title, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        mute_b = Gtk.Button(); mute_b.set_relief(Gtk.ReliefStyle.NONE)
        mute_b.get_style_context().add_class("nxs-icon")
        mute_b.set_image(Gtk.Image.new_from_icon_name(
            "audio-volume-high-symbolic", Gtk.IconSize.MENU))
        row.pack_start(mute_b, False, False, 0)
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        scale.set_draw_value(True); scale.set_value_pos(Gtk.PositionType.RIGHT)
        scale.set_hexpand(True)
        row.pack_start(scale, True, True, 0)
        box.pack_start(row, False, False, 0)

        status = Gtk.Label(label="..."); status.set_xalign(0)
        status.get_style_context().add_class("nxs-clock-date")
        box.pack_start(status, False, False, 0)
        outs = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.pack_start(outs, False, False, 0)
        self._spawn_popup("audio", box, align="right", autoclose=False)

        def on_scale(s):
            self._bg(["nxs-audio", "set", str(int(s.get_value()))])
            GLib.timeout_add(150, self._refresh_media)

        def fill(pct, muted, sinks):
            if "audio" not in self._popups:
                return False
            scale.set_value(pct if pct is not None else 0)
            scale.connect("value-changed", on_scale)
            mute_b.connect("clicked", lambda _w: (
                self._bg(["nxs-audio", "mute"]),
                GLib.timeout_add(150, self._refresh_media)))
            if pct is None:
                status.set_text("PipeWire non attivo o nessuna uscita audio.")
            else:
                status.set_text("Uscita audio:" if sinks else "")
            for sid, name, is_def in sinks:
                b = Gtk.Button(); b.set_relief(Gtk.ReliefStyle.NONE)
                b.get_style_context().add_class("nxs-menu-item")
                lab = Gtk.Label(label=("● " if is_def else "○ ") + name)
                lab.set_xalign(0); b.add(lab)
                b.connect("clicked", lambda _w, i=sid: (
                    self._bg(["nxs-audio", "default", i]),
                    self._close_popup("audio")))
                outs.pack_start(b, False, False, 0)
            outs.show_all()
            return False

        def worker():
            pct = None; muted = False
            try:
                o = self._run_out(["nxs-audio", "get"]).split()
                pct = int(o[0]); muted = (o[1] == "1")
            except Exception:                       # noqa: BLE001
                pass
            sinks = []
            for line in self._run_out(["nxs-audio", "sinks"]).splitlines():
                p = line.split("\t")
                if len(p) >= 2 and p[0].strip():
                    sinks.append((p[0], p[1], len(p) > 2 and p[2] == "*"))
            GLib.idle_add(fill, pct, muted, sinks)
        threading.Thread(target=worker, daemon=True).start()

    def _toggle_bluetooth(self, _btn):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.get_style_context().add_class("nxs-calbox")
        box.set_size_request(320, -1)
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title = Gtk.Label(); title.set_markup("<b>Bluetooth</b>"); title.set_xalign(0)
        head.pack_start(title, True, True, 0)
        sw = Gtk.Switch(); sw.set_valign(Gtk.Align.CENTER)
        head.pack_end(sw, False, False, 0)
        box.pack_start(head, False, False, 0)

        status = Gtk.Label(label="..."); status.set_xalign(0)
        status.set_line_wrap(True)
        status.get_style_context().add_class("nxs-clock-date")
        box.pack_start(status, False, False, 0)

        scan_b = Gtk.Button(label="Scansiona dispositivi")
        scan_b.get_style_context().add_class("nxs-menu-item")
        box.pack_start(scan_b, False, False, 0)
        devlist = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.pack_start(devlist, False, False, 0)
        self._spawn_popup("bt", box, align="right", autoclose=False)

        def render_devs(devs):
            if "bt" not in self._popups:
                return False
            for c in devlist.get_children():
                devlist.remove(c)
            for mac, name, st in devs:
                b = Gtk.Button(); b.set_relief(Gtk.ReliefStyle.NONE)
                b.get_style_context().add_class("nxs-menu-item")
                hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                ico = "bluetooth-active-symbolic" if st == "conn" else "bluetooth-symbolic"
                hb.pack_start(Gtk.Image.new_from_icon_name(ico, Gtk.IconSize.MENU),
                              False, False, 0)
                lab = Gtk.Label(label=name or mac); lab.set_xalign(0)
                hb.pack_start(lab, True, True, 0)
                if st:
                    tag = Gtk.Label(label="connesso" if st == "conn" else "abbinato")
                    tag.get_style_context().add_class("nxs-clock-date")
                    hb.pack_start(tag, False, False, 0)
                b.add(hb)
                b.connect("clicked", lambda _w, m=mac, s=st: self._bt_toggle_dev(m, s))
                devlist.pack_start(b, False, False, 0)
            devlist.show_all()
            return False

        def do_scan(_w=None):
            status.set_text("Scansione in corso (qualche secondo)...")
            def worker():
                devs = []
                for line in self._run_out(["nxs-bluetooth", "scan", "6"], 15).splitlines():
                    p = line.split("\t")
                    if len(p) >= 2:
                        devs.append((p[0], p[1], p[2] if len(p) > 2 else ""))
                GLib.idle_add(lambda: (status.set_text(
                    "Clic su un dispositivo per connettere/disconnettere:"
                    if devs else "Nessun dispositivo trovato."), render_devs(devs)))
            threading.Thread(target=worker, daemon=True).start()
        scan_b.connect("clicked", do_scan)

        def on_switch(s, state):
            self._bg(["nxs-bluetooth", "on" if state else "off"])
            GLib.timeout_add(400, self._refresh_media)
            return False
        def load():
            st = self._run_out(["nxs-bluetooth", "status"]).strip()
            devs = []
            if st == "on":
                for line in self._run_out(["nxs-bluetooth", "devices"]).splitlines():
                    p = line.split("\t")
                    if len(p) >= 2:
                        devs.append((p[0], p[1], p[2] if len(p) > 2 else ""))
            def apply():
                if "bt" not in self._popups:
                    return False
                if st == "noadapter":
                    status.set_text("Nessun adattatore Bluetooth rilevato. In VM "
                                    "non e' disponibile: usa un dongle USB.")
                    sw.set_sensitive(False); scan_b.set_sensitive(False)
                    return False
                sw.set_active(st == "on")
                sw.connect("state-set", on_switch)
                status.set_text("Bluetooth acceso." if st == "on"
                                else "Bluetooth spento.")
                render_devs(devs)
                return False
            GLib.idle_add(apply)
        threading.Thread(target=load, daemon=True).start()

    def _bt_toggle_dev(self, mac, st):
        act = "disconnect" if st == "conn" else "connect"
        self._bg(["nxs-bluetooth", act, mac])
        self._close_popup("bt")

    def _toggle_wifi(self, _btn):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.get_style_context().add_class("nxs-calbox")
        box.set_size_request(300, -1)
        title = Gtk.Label(); title.set_markup("<b>Reti WiFi</b>"); title.set_xalign(0)
        box.pack_start(title, False, False, 0)
        status = Gtk.Label(label="Scansione in corso..."); status.set_xalign(0)
        status.set_line_wrap(True)
        status.get_style_context().add_class("nxs-clock-date")
        box.pack_start(status, False, False, 0)
        listbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.pack_start(listbox, False, False, 0)
        self._spawn_popup("wifi", box, align="right", autoclose=False)

        def populate(nets, iface):
            if "wifi" not in self._popups:
                return False
            for c in listbox.get_children():
                listbox.remove(c)
            if not iface:
                status.set_text("Nessuna scheda WiFi rilevata. In una macchina "
                                "virtuale il WiFi non e' disponibile: usa Ethernet "
                                "o passa un adattatore WiFi USB.")
                return False
            if not nets:
                status.set_text("Nessuna rete in portata (WiFi acceso, nessuna rete "
                                "trovata).")
                return False
            status.set_text("Clic su una rete per connetterti:")
            for ssid, sig, flags in nets:
                locked = any(x in flags for x in ("WPA", "PSK", "WEP", "SAE"))
                b = Gtk.Button(); b.set_relief(Gtk.ReliefStyle.NONE)
                b.get_style_context().add_class("nxs-menu-item")
                hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                ico = ("network-wireless-encrypted-symbolic" if locked
                       else "network-wireless-symbolic")
                hb.pack_start(Gtk.Image.new_from_icon_name(
                    ico, Gtk.IconSize.MENU), False, False, 0)
                lab = Gtk.Label(label=ssid); lab.set_xalign(0)
                hb.pack_start(lab, True, True, 0)
                sg = Gtk.Label(label="%s dBm" % sig)
                sg.get_style_context().add_class("nxs-clock-date")
                hb.pack_start(sg, False, False, 0)
                b.add(hb)
                b.connect("clicked",
                          lambda _w, s=ssid, lk=locked: self._wifi_connect(s, lk))
                listbox.pack_start(b, False, False, 0)
            listbox.show_all()
            return False

        def worker():
            iface = self._run_out(["nxs-wifi", "iface"]).strip()
            out = self._run_out(["nxs-wifi", "scan"]) if iface else ""
            nets = []
            for line in out.splitlines():
                p = line.split("\t")
                if len(p) >= 3 and p[0].strip():
                    nets.append((p[0], p[1], p[2]))
            GLib.idle_add(populate, nets, iface)
        threading.Thread(target=worker, daemon=True).start()

    def _wifi_connect(self, ssid, locked):
        psk = ""
        if locked:
            psk = self._ask_password("Password per la rete «%s»" % ssid)
            if psk is None:
                return
        self._close_popup("wifi")
        threading.Thread(
            target=lambda: self._run_out(["nxs-wifi", "connect", ssid, psk], 30),
            daemon=True).start()

    def _ask_password(self, prompt):
        d = Gtk.Dialog(title="Connessione WiFi", modal=True)
        d.set_keep_above(True)
        d.add_button("Annulla", Gtk.ResponseType.CANCEL)
        d.add_button("Connetti", Gtk.ResponseType.OK)
        d.set_default_response(Gtk.ResponseType.OK)
        area = d.get_content_area()
        area.set_spacing(8); area.set_border_width(12)
        area.add(Gtk.Label(label=prompt))
        e = Gtk.Entry(); e.set_visibility(False); e.set_activates_default(True)
        area.add(e)
        d.show_all()
        resp = d.run()
        psk = e.get_text() if resp == Gtk.ResponseType.OK else None
        d.destroy()
        return psk

    # --- applet Schermi (xrandr via nxs-screens) ---
    def _toggle_screens(self, _btn):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.get_style_context().add_class("nxs-calbox")
        box.set_size_request(300, -1)
        title = Gtk.Label(); title.set_markup("<b>Schermi</b>"); title.set_xalign(0)
        box.pack_start(title, False, False, 0)

        outs = []
        for line in self._run_out(["nxs-screens", "outputs"]).splitlines():
            p = line.split("\t")
            if len(p) >= 4 and p[1] == "connected":
                outs.append((p[0], p[2], p[3]))       # nome, primary?, WxH

        if not outs:
            lbl = Gtk.Label(label="Nessuno schermo rilevato."); lbl.set_xalign(0)
            box.pack_start(lbl, False, False, 0)
        else:
            if len(outs) >= 2:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
                for lbl, act in (("Estendi", ["extend"]), ("Duplica", ["mirror"])):
                    b = Gtk.Button(label=lbl)
                    b.get_style_context().add_class("nxs-menu-item")
                    b.connect("clicked", lambda _w, a=act: self._screens_apply(a))
                    row.pack_start(b, True, True, 0)
                box.pack_start(row, False, False, 0)
            for name, prim, res in outs:
                oc = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
                oc.get_style_context().add_class("nxs-dt-row")
                hdr = Gtk.Label(); hdr.set_xalign(0)
                hdr.set_markup("<b>%s</b>%s  <small>%s</small>" % (
                    name, "  (principale)" if prim == "primary" else "", res))
                oc.pack_start(hdr, False, False, 0)
                r = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
                combo = Gtk.ComboBoxText()
                modes = self._run_out(["nxs-screens", "modes", name]).split()
                for m in modes:
                    combo.append_text(m)
                if modes:
                    combo.set_active(0)
                r.pack_start(combo, True, True, 0)
                ba = Gtk.Button(label="Applica")
                ba.get_style_context().add_class("nxs-menu-item")
                ba.connect("clicked", lambda _w, n=name, c=combo:
                           self._screens_apply(["mode", n, c.get_active_text() or ""]))
                r.pack_start(ba, False, False, 0)
                oc.pack_start(r, False, False, 0)
                if len(outs) >= 2:
                    bo = Gtk.Button(label="Usa solo questo")
                    bo.get_style_context().add_class("nxs-menu-item")
                    bo.connect("clicked",
                               lambda _w, n=name: self._screens_apply(["only", n]))
                    oc.pack_start(bo, False, False, 0)
                box.pack_start(oc, False, False, 0)

        self._spawn_popup("screens", box, align="right", autoclose=False)

    def _screens_apply(self, args):
        self._close_popup("screens")
        if len(args) >= 3 and args[0] == "mode" and not args[2]:
            return                                    # nessuna risoluzione scelta
        run_bg(["nxs-screens"] + list(args))

    def _on_today(self, _w):
        t = time.localtime()
        self.calendar.select_month(t.tm_mon - 1, t.tm_year)
        self.calendar.select_day(t.tm_mday)
        self.spin_h.set_value(t.tm_hour)
        self.spin_m.set_value(t.tm_min)

    def _current_tz(self):
        """Fuso corrente via nxs-datetime (legge /etc/timezone o il symlink)."""
        try:
            out = subprocess.run(["nxs-datetime", "get-tz"], capture_output=True,
                                 text=True, timeout=4).stdout.strip()
            return out or "UTC"
        except (OSError, subprocess.SubprocessError):
            return "UTC"

    def _apply_datetime(self, _btn):
        """Imposta data (dal calendario) + ora (dagli spin) come clock di sistema."""
        y, m0, d = self.calendar.get_date()          # mese 0-based
        s = "%04d-%02d-%02d %02d:%02d:00" % (
            y, m0 + 1, d, int(self.spin_h.get_value()), int(self.spin_m.get_value()))
        try:
            subprocess.run(["nxs-datetime", "set-datetime", s], timeout=8)
        except (OSError, subprocess.SubprocessError):
            pass
        self._tick_clock()
        self._close_popup("calendar")

    def _apply_tz(self, _btn):
        """Cambia il fuso orario di sistema e aggiorna subito l'orologio."""
        tz = self.tz_combo.get_active_text()
        if not tz:
            return
        try:
            subprocess.run(["nxs-datetime", "set-tz", tz], timeout=8)
        except (OSError, subprocess.SubprocessError):
            pass
        try:                                          # ricarica il fuso nel processo
            os.environ.pop("TZ", None)
            time.tzset()
        except Exception:                             # noqa: BLE001
            pass
        self._tick_clock()
        self._close_popup("calendar")

    # --- calendario + regolazione ora/data/fuso (toplevel toggle) ---
    def _toggle_calendar(self, _btn):
        cal_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        cal_box.get_style_context().add_class("nxs-calbox")
        self.calendar = Gtk.Calendar()
        self.calendar.get_style_context().add_class("nxs-calendar")
        cal_box.pack_start(self.calendar, True, True, 0)

        btn_today = Gtk.Button(label="Oggi")
        btn_today.get_style_context().add_class("nxs-menu-item")
        btn_today.connect("clicked", self._on_today)
        cal_box.pack_start(btn_today, False, False, 0)

        cal_box.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL),
                           False, False, 2)

        # Riga ORA: HH : MM + Imposta (usa la data selezionata nel calendario).
        t = time.localtime()
        time_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        time_row.get_style_context().add_class("nxs-dt-row")
        time_row.pack_start(Gtk.Label(label="Ora"), False, False, 0)
        self.spin_h = Gtk.SpinButton.new_with_range(0, 23, 1)
        self.spin_h.set_value(t.tm_hour)
        self.spin_m = Gtk.SpinButton.new_with_range(0, 59, 1)
        self.spin_m.set_value(t.tm_min)
        time_row.pack_start(self.spin_h, False, False, 0)
        time_row.pack_start(Gtk.Label(label=":"), False, False, 0)
        time_row.pack_start(self.spin_m, False, False, 0)
        apply_dt = Gtk.Button(label="Imposta")
        apply_dt.get_style_context().add_class("nxs-menu-item")
        apply_dt.connect("clicked", self._apply_datetime)
        time_row.pack_end(apply_dt, False, False, 0)
        cal_box.pack_start(time_row, False, False, 0)

        # Riga FUSO: combo + Imposta.
        tz_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        tz_row.get_style_context().add_class("nxs-dt-row")
        tz_row.pack_start(Gtk.Label(label="Fuso"), False, False, 0)
        self.tz_combo = Gtk.ComboBoxText()
        cur = self._current_tz()
        zones = list(COMMON_TZ)
        if cur not in zones:
            zones.insert(0, cur)
        for z in zones:
            self.tz_combo.append_text(z)
        try:
            self.tz_combo.set_active(zones.index(cur))
        except ValueError:
            self.tz_combo.set_active(0)
        tz_row.pack_start(self.tz_combo, True, True, 0)
        apply_tz = Gtk.Button(label="Imposta")
        apply_tz.get_style_context().add_class("nxs-menu-item")
        apply_tz.connect("clicked", self._apply_tz)
        tz_row.pack_end(apply_tz, False, False, 0)
        cal_box.pack_start(tz_row, False, False, 0)

        self._spawn_popup("calendar", cal_box, align="right", autoclose=False)

    # --- lista finestre ---
    def _refresh_tasks(self):
        wins = _wmctrl_list()
        active = _active_window()
        sig = tuple((w, t) for w, _d, t in wins)
        if sig != self._last_sig:
            self._last_sig = sig
            for child in self.tasks.get_children():
                self.tasks.remove(child)
            self._task_btns = {}
            for wid, _desk, title in wins:
                short = title if len(title) <= 28 else title[:27] + "…"
                b = Gtk.Button(label=short)
                b.set_tooltip_text(title)
                b.get_style_context().add_class("nxs-task")
                b.connect("clicked", self._on_task, wid)
                self.tasks.pack_start(b, False, False, 0)
                self._task_btns[wid] = b
            self.tasks.show_all()
        for wid, b in self._task_btns.items():
            ctx = b.get_style_context()
            if active and wid.lower() == active.lower():
                ctx.add_class("nxs-task-active")
            else:
                ctx.remove_class("nxs-task-active")
        return self._alive

    def _on_task(self, _btn, wid):
        active = _active_window()
        if active and wid.lower() == active.lower():
            if have("xdotool"):
                run_bg(["xdotool", "windowminimize", str(int(wid, 16))])
        else:
            run_bg(["wmctrl", "-i", "-a", wid])

    # --- orologio ---
    def _tick_clock(self):
        t = time.localtime()
        self.clock.set_text(time.strftime("%H:%M", t))
        giorni = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]
        mesi = ["gen", "feb", "mar", "apr", "mag", "giu",
                "lug", "ago", "set", "ott", "nov", "dic"]
        self.date.set_text("%s %d %s" % (giorni[t.tm_wday], t.tm_mday,
                                         mesi[t.tm_mon - 1]))
        return self._alive


def run():
    # UNA barra per monitor: cosi' bar + menu compaiono su OGNI schermo (interno
    # e esterno). Le barre si ricostruiscono quando si collega/scollega un
    # monitor o cambia la risoluzione (monitors-changed / size-changed).
    screen = Gdk.Screen.get_default()
    panels = []

    def build(*_a):
        for p in panels:
            p.destroy()
        panels.clear()
        n = screen.get_n_monitors() if hasattr(screen, "get_n_monitors") else 1
        for i in range(max(1, n)):
            p = Panel(i)
            p.show_all()
            panels.append(p)

    build()
    screen.connect("monitors-changed", build)
    screen.connect("size-changed", build)
    Gtk.main()


if __name__ == "__main__":
    run()
