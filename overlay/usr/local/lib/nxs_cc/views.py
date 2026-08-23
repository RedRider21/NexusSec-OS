"""Viste GTK native del Centro di Controllo NexusSec.

Ogni funzione open_* costruisce e mostra una finestra con una vera
interfaccia grafica (niente dump testuali ne terminali esterni, salvo
dove un programma dedicato e' gia' una GUI: lxappearance).
"""
from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import threading
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Pango  # noqa: E402
import cairo  # noqa: E402  (py3-cairo, gia' dipendenza)

from nxs_cc.common import (
    HOME, have, run_bg, run_capture, info_dialog, panel_window, read_file,
    icon_button, COL_ACCENT, COL_ALERT,
)
from nxs_cc import panelcfg


# ---------------------------------------------------------------------------
# Letture di sistema
# ---------------------------------------------------------------------------
def _meminfo() -> tuple[int, int]:
    """Ritorna (used_kb, total_kb)."""
    total = avail = 0
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                total = int(line.split()[1])
            elif line.startswith("MemAvailable:"):
                avail = int(line.split()[1])
    except OSError:
        pass
    return max(total - avail, 0), total


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return "CPU sconosciuta"


def _cpu_count() -> int:
    return os.cpu_count() or 1


def _read_cpu_times() -> tuple[int, int]:
    """Ritorna (idle, total) dalla prima riga di /proc/stat."""
    try:
        parts = Path("/proc/stat").read_text().splitlines()[0].split()[1:]
        nums = [int(x) for x in parts]
        idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
        return idle, sum(nums)
    except (OSError, ValueError, IndexError):
        return 0, 0


def _human(kb: int) -> str:
    mb = kb / 1024
    if mb >= 1024:
        return f"{mb/1024:.1f} GB"
    return f"{mb:.0f} MB"


def _human_bps(n: float) -> str:
    """Byte/s -> stringa (B/s, K/s, M/s, G/s)."""
    for unit in ("B", "K", "M", "G"):
        if n < 1024 or unit == "G":
            return f"{n:.0f} {unit}/s"
        n /= 1024.0
    return f"{n:.0f} G/s"


def _human_bytes(n: float) -> str:
    """Byte -> stringa (B/KB/MB/GB/TB) per lo spazio dei filesystem."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} TB"


_DISK_RE = re.compile(r'^(sd[a-z]+|vd[a-z]+|hd[a-z]+|xvd[a-z]+|nvme\d+n\d+|mmcblk\d+)$')


def _read_net_total() -> float:
    """Byte totali rx+tx su tutte le interfacce (esclusa lo)."""
    tot = 0.0
    try:
        with open("/proc/net/dev") as f:
            for line in f.readlines()[2:]:
                iface, _, data = line.partition(":")
                if iface.strip() == "lo":
                    continue
                cols = data.split()
                tot += float(cols[0]) + float(cols[8])
    except (OSError, ValueError, IndexError):
        pass
    return tot


def _read_disk_total() -> float:
    """Byte totali letti+scritti sui dischi fisici interi (da /proc/diskstats)."""
    sectors = 0.0
    try:
        with open("/proc/diskstats") as f:
            for line in f:
                p = line.split()
                if len(p) < 11 or not _DISK_RE.match(p[2]):
                    continue
                sectors += float(p[5]) + float(p[9])
    except (OSError, ValueError, IndexError):
        pass
    return sectors * 512.0


# ---------------------------------------------------------------------------
# Info sistema
# ---------------------------------------------------------------------------
def open_sysinfo(_btn=None):
    win, body = panel_window("Informazioni di sistema", 560, 480)

    grid = Gtk.Grid(column_spacing=18, row_spacing=8)
    body.pack_start(grid, False, False, 0)

    def row(r, key, val):
        k = Gtk.Label(label=key)
        k.set_xalign(0)
        k.get_style_context().add_class("nxs-key")
        v = Gtk.Label(label=val)
        v.set_xalign(0)
        v.set_selectable(True)
        v.get_style_context().add_class("nxs-val")
        v.set_line_wrap(True)
        grid.attach(k, 0, r, 1, 1)
        grid.attach(v, 1, r, 1, 1)
        return v

    uname = run_capture(["uname", "-r"]) or "?"
    arch = run_capture(["uname", "-m"]) or "?"
    row(0, "Host", socket.gethostname())
    row(1, "Utente", os.getenv("USER", "nexus"))
    _alpine = run_capture(["sh", "-c", "cat /etc/alpine-release 2>/dev/null"]) or "?"
    row(2, "Sistema", f"NexusSec OS (Alpine {_alpine})")
    row(3, "Kernel", uname)
    row(4, "Architettura", arch)
    row(5, "CPU", f"{_cpu_model()}  ({_cpu_count()} core)")
    up = row(6, "Uptime", run_capture(["uptime", "-p"]) or run_capture(["uptime"]))

    # RAM
    body.pack_start(Gtk.Separator(), False, False, 6)
    ram_lbl = Gtk.Label(); ram_lbl.set_xalign(0)
    ram_lbl.get_style_context().add_class("nxs-key")
    ram_bar = Gtk.ProgressBar(); ram_bar.set_show_text(True)
    body.pack_start(ram_lbl, False, False, 0)
    body.pack_start(ram_bar, False, False, 0)

    # Disco /
    disk_lbl = Gtk.Label(); disk_lbl.set_xalign(0)
    disk_lbl.get_style_context().add_class("nxs-key")
    disk_bar = Gtk.ProgressBar(); disk_bar.set_show_text(True)
    body.pack_start(disk_lbl, False, False, 0)
    body.pack_start(disk_bar, False, False, 0)

    # Pacchetti apk installati
    tcz = row(7, "Pacchetti apk",
              run_capture(["sh", "-c", "apk info 2>/dev/null | wc -l"]))

    def refresh(*_a):
        used, total = _meminfo()
        if total:
            frac = used / total
            ram_bar.set_fraction(frac)
            ram_bar.set_text(f"{_human(used)} / {_human(total)}  ({frac*100:.0f}%)")
        ram_lbl.set_text("Memoria RAM")
        try:
            du = shutil.disk_usage("/")
            frac = du.used / du.total if du.total else 0
            disk_bar.set_fraction(frac)
            disk_bar.set_text(f"{du.used//(1024**2)} MB / {du.total//(1024**2)} MB  ({frac*100:.0f}%)")
        except OSError:
            disk_bar.set_text("n/d")
        disk_lbl.set_text("Disco /")
        up.set_text(run_capture(["uptime", "-p"]) or run_capture(["uptime"]))

    refresh()

    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    btn_r = Gtk.Button(label="Aggiorna")
    btn_r.connect("clicked", refresh)
    btn_c = Gtk.Button(label="Chiudi")
    btn_c.connect("clicked", lambda _b: win.destroy())
    bar.pack_start(btn_r, False, False, 0)
    bar.pack_end(btn_c, False, False, 0)
    body.pack_end(bar, False, False, 0)

    win.show_all()


# ---------------------------------------------------------------------------
# Monitor risorse (live, nativo)
# ---------------------------------------------------------------------------
GRAPH_N = 60


class _Graph(Gtk.DrawingArea):
    """Grafico a scorrimento (linea + area riempita + griglia), stile Monitor di
    sistema MATE. hist tiene 0..1 (CPU/RAM) o byte/s grezzi (Rete/Disco: autoscale)."""
    def __init__(self, rgb, autoscale=False):
        super().__init__()
        self.rgb = rgb
        self.autoscale = autoscale
        self.hist = [0.0] * GRAPH_N
        self.set_size_request(-1, 68)
        self.connect("draw", self._draw)

    def push(self, v):
        self.hist.append(v if v > 0 else 0.0)
        del self.hist[0]
        self.queue_draw()

    def _draw(self, _w, cr):
        w = self.get_allocated_width(); h = self.get_allocated_height()
        r, g, b = self.rgb
        cr.set_source_rgba(0.02, 0.06, 0.10, 1.0)
        cr.rectangle(0, 0, w, h); cr.fill()
        cr.set_source_rgba(0.10, 0.23, 0.32, 0.55); cr.set_line_width(1)
        for i in range(1, 4):
            y = round(h * i / 4.0) + 0.5
            cr.move_to(0, y); cr.line_to(w, y); cr.stroke()
        if self.autoscale:
            peak = max(self.hist); peak = peak if peak > 1 else 1.0
            vals = [min(1.0, v / peak) for v in self.hist]
        else:
            vals = [min(1.0, v) for v in self.hist]
        n = len(vals)
        if n >= 2:
            step = w / (n - 1); pad = 2
            def yv(v):
                return h - pad - v * (h - 2 * pad)
            cr.move_to(0, h)
            for i, v in enumerate(vals):
                cr.line_to(i * step, yv(v))
            cr.line_to((n - 1) * step, h); cr.close_path()
            grad = cairo.LinearGradient(0, 0, 0, h)
            grad.add_color_stop_rgba(0, r, g, b, 0.42)
            grad.add_color_stop_rgba(1, r, g, b, 0.04)
            cr.set_source(grad); cr.fill()
            cr.set_source_rgba(r, g, b, 0.95); cr.set_line_width(1.6)
            cr.set_line_join(cairo.LINE_JOIN_ROUND)
            for i, v in enumerate(vals):
                (cr.move_to if i == 0 else cr.line_to)(i * step, yv(v))
            cr.stroke()
        cr.set_source_rgba(0.10, 0.23, 0.32, 0.9); cr.set_line_width(1)
        cr.rectangle(0.5, 0.5, w - 1, h - 1); cr.stroke()


def _filesystems():
    """Filesystem montati REALI: (device, mount, tipo, tot, usato, libero)."""
    pseudo = {"proc", "sysfs", "devtmpfs", "devpts", "cgroup", "cgroup2",
              "mqueue", "debugfs", "tracefs", "securityfs", "pstore", "bpf",
              "configfs", "fusectl", "hugetlbfs", "autofs", "binfmt_misc",
              "ramfs", "efivarfs"}
    seen = set(); rows = []
    try:
        with open("/proc/mounts") as f:
            lines = f.readlines()
    except OSError:
        return rows
    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        dev, mnt, fstype = parts[0], parts[1], parts[2]
        if fstype in pseudo or mnt in seen:
            continue
        seen.add(mnt)
        mnt_dec = mnt.replace("\\040", " ")
        try:
            st = os.statvfs(mnt)
        except OSError:
            continue
        total = st.f_blocks * st.f_frsize
        if total == 0:
            continue
        used = (st.f_blocks - st.f_bfree) * st.f_frsize
        free = st.f_bavail * st.f_frsize
        rows.append((dev, mnt_dec, fstype, total, used, free))
    return rows


def open_monitor(_btn=None):
    win, body = panel_window("Monitor risorse", 540, 600)
    nb = Gtk.Notebook()
    body.pack_start(nb, True, True, 0)

    # ===== Scheda RISORSE: grafici a scorrimento =====
    res = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    res.set_border_width(8)
    nb.append_page(res, Gtk.Label(label="Risorse"))

    def make_graph(title, rgb, autoscale=False):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        card.get_style_context().add_class("nxs-card")
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        t = Gtk.Label(label=title); t.set_xalign(0)
        t.get_style_context().add_class("nxs-card-title")
        val = Gtk.Label(); val.set_xalign(1)
        val.get_style_context().add_class("nxs-val")
        hdr.pack_start(t, True, True, 0)
        hdr.pack_end(val, False, False, 0)
        gr = _Graph(rgb, autoscale)
        card.pack_start(hdr, False, False, 0)
        card.pack_start(gr, False, False, 0)
        res.pack_start(card, False, False, 0)
        return gr, val

    cpu_g, cpu_v = make_graph("CPU", (0.00, 0.898, 1.00))
    ram_g, ram_v = make_graph("Memoria RAM", (0.40, 0.95, 0.65))
    net_g, net_v = make_graph("Rete (rx+tx)", (1.00, 0.72, 0.25), True)
    disk_g, disk_v = make_graph("Disco (lettura+scrittura)", (0.66, 0.55, 1.00), True)

    load_lbl = Gtk.Label(); load_lbl.set_xalign(0)
    load_lbl.get_style_context().add_class("nxs-val")
    res.pack_start(load_lbl, False, False, 2)

    state = {"idle": 0, "total": 0}
    state["idle"], state["total"] = _read_cpu_times()
    state["net"] = _read_net_total()
    state["disk"] = _read_disk_total()

    def tick():
        idle, total = _read_cpu_times()
        di = idle - state["idle"]; dt = total - state["total"]
        state["idle"], state["total"] = idle, total
        cpu = min(max((1 - di / dt) if dt > 0 else 0, 0), 1)
        cpu_g.push(cpu); cpu_v.set_text(f"{cpu*100:.0f}%")

        used, tot = _meminfo()
        frac = used / tot if tot else 0
        ram_g.push(frac)
        ram_v.set_text(f"{_human(used)} / {_human(tot)}  ({frac*100:.0f}%)")

        ncur = _read_net_total()
        nrate = max(0.0, ncur - state["net"]); state["net"] = ncur
        net_g.push(nrate); net_v.set_text(_human_bps(nrate))

        dcur = _read_disk_total()
        drate = max(0.0, dcur - state["disk"]); state["disk"] = dcur
        disk_g.push(drate); disk_v.set_text(_human_bps(drate))

        try:
            la = os.getloadavg()
            load_lbl.set_text(f"Load average:  {la[0]:.2f}   {la[1]:.2f}   {la[2]:.2f}")
        except OSError:
            pass
        return True

    # ===== Scheda FILE SYSTEM: spazio dischi/partizioni =====
    fs_scroll = Gtk.ScrolledWindow()
    fs_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    fs_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    fs_box.set_border_width(8)
    fs_scroll.add(fs_box)
    nb.append_page(fs_scroll, Gtk.Label(label="File system"))

    def refresh_fs():
        for c in fs_box.get_children():
            fs_box.remove(c)
        rows = _filesystems()
        if not rows:
            lbl = Gtk.Label(label="Nessun filesystem montato."); lbl.set_xalign(0)
            fs_box.pack_start(lbl, False, False, 0)
        for dev, mnt, fstype, total, used, free in rows:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            card.get_style_context().add_class("nxs-card")
            top = Gtk.Label(); top.set_xalign(0)
            top.set_markup("<b>%s</b>  <small>%s · %s</small>" % (
                GLib.markup_escape_text(mnt),
                GLib.markup_escape_text(dev), GLib.markup_escape_text(fstype)))
            card.pack_start(top, False, False, 0)
            frac = used / total if total else 0
            bar = Gtk.ProgressBar(); bar.set_fraction(min(1.0, frac))
            bar.set_show_text(True)
            bar.set_text("%s / %s  (%.0f%%)  ·  liberi %s" % (
                _human_bytes(used), _human_bytes(total), frac * 100,
                _human_bytes(free)))
            ctx = bar.get_style_context()
            if frac >= 0.9:
                ctx.add_class("nxs-alert")
            elif frac >= 0.75:
                ctx.add_class("nxs-warn")
            card.pack_start(bar, False, False, 0)
            fs_box.pack_start(card, False, False, 0)
        fs_box.show_all()

    refresh_fs()
    tick()
    src1 = GLib.timeout_add_seconds(1, tick)
    src2 = GLib.timeout_add_seconds(5, lambda: (refresh_fs(), True)[1])
    win.connect("destroy", lambda *_a: (GLib.source_remove(src1),
                                        GLib.source_remove(src2)))

    btn_c = Gtk.Button(label="Chiudi")
    btn_c.connect("clicked", lambda _b: win.destroy())
    bbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    bbox.pack_end(btn_c, False, False, 0)
    body.pack_end(bbox, False, False, 0)

    win.show_all()


# ---------------------------------------------------------------------------
# Rete
# ---------------------------------------------------------------------------
def _parse_interfaces() -> list[tuple[str, str, str]]:
    """Ritorna lista (interfaccia, ipv4, stato)."""
    out = run_capture(["ip", "-o", "-4", "addr", "show"])
    rows: dict[str, list[str]] = {}
    if out:
        for line in out.splitlines():
            m = re.match(r"\d+:\s+(\S+)\s+inet\s+(\S+)", line)
            if m:
                rows.setdefault(m.group(1), []).append(m.group(2))
    # stato up/down
    res = []
    for iface, ips in rows.items():
        state_out = run_capture(["sh", "-c", f"cat /sys/class/net/{iface}/operstate 2>/dev/null"])
        res.append((iface, ", ".join(ips), state_out or "?"))
    if not res:
        # fallback ifconfig
        ic = run_capture(["ifconfig"])
        cur = None
        for line in ic.splitlines():
            if line and not line[0].isspace():
                cur = line.split()[0].rstrip(":")
            m = re.search(r"inet (?:addr:)?(\S+)", line)
            if m and cur:
                res.append((cur, m.group(1), "?"))
    return res


def _net_ifaces() -> list[str]:
    """Interfacce di rete configurabili (esclusa loopback)."""
    names = []
    base = Path("/sys/class/net")
    if base.is_dir():
        for p in sorted(base.iterdir()):
            if p.name != "lo":
                names.append(p.name)
    return names


def _valid_ipv4(s: str) -> bool:
    parts = s.split(".")
    if len(parts) != 4:
        return False
    for p in parts:
        if not p.isdigit() or not 0 <= int(p) <= 255:
            return False
    return True


def open_network(_btn=None):
    win, body = panel_window("Rete", 600, 560)

    store = Gtk.ListStore(str, str, str)
    tree = Gtk.TreeView(model=store)
    for i, title in enumerate(("Interfaccia", "Indirizzo IPv4", "Stato")):
        col = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=i)
        col.set_expand(i == 1)
        tree.append_column(col)
    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    sw.set_min_content_height(120)
    sw.add(tree)
    body.pack_start(sw, True, True, 0)

    def refresh(*_a):
        store.clear()
        for r in _parse_interfaces():
            store.append(list(r))
        if not len(store):
            store.append(("(nessuna)", "-", "-"))

    refresh()

    # --- Configurazione interfaccia -------------------------------------
    frame = Gtk.Frame(label="Configurazione")
    grid = Gtk.Grid(row_spacing=8, column_spacing=8)
    grid.set_margin_top(8); grid.set_margin_bottom(8)
    grid.set_margin_start(8); grid.set_margin_end(8)
    frame.add(grid)

    grid.attach(Gtk.Label(label="Interfaccia:", xalign=0), 0, 0, 1, 1)
    cb_if = Gtk.ComboBoxText()
    for name in _net_ifaces() or ["eth0"]:
        cb_if.append_text(name)
    cb_if.set_active(0)
    grid.attach(cb_if, 1, 0, 2, 1)

    rb_dhcp = Gtk.RadioButton.new_with_label_from_widget(None, "Automatico (DHCP)")
    rb_static = Gtk.RadioButton.new_with_label_from_widget(rb_dhcp, "Statico")
    grid.attach(rb_dhcp, 0, 1, 3, 1)
    grid.attach(rb_static, 0, 2, 3, 1)

    def mk_row(label, row, placeholder):
        grid.attach(Gtk.Label(label=label, xalign=0), 0, row, 1, 1)
        e = Gtk.Entry()
        e.set_placeholder_text(placeholder)
        grid.attach(e, 1, row, 2, 1)
        return e

    e_ip = mk_row("Indirizzo IP:", 3, "es. 192.168.1.50")
    e_mask = mk_row("Maschera:", 4, "es. 255.255.255.0")
    e_gw = mk_row("Gateway:", 5, "es. 192.168.1.1")
    e_dns = mk_row("DNS:", 6, "es. 1.1.1.1")

    def on_mode(*_a):
        static = rb_static.get_active()
        for e in (e_ip, e_mask, e_gw, e_dns):
            e.set_sensitive(static)

    rb_dhcp.connect("toggled", on_mode)
    on_mode()
    body.pack_start(frame, False, False, 0)

    ping_lbl = Gtk.Label(label="Connettivita': non testata")
    ping_lbl.set_xalign(0)
    ping_lbl.get_style_context().add_class("nxs-val")
    body.pack_start(ping_lbl, False, False, 0)

    spinner = Gtk.Spinner()

    def set_status(txt):
        ping_lbl.set_text(txt)
        return False

    def do_ping(_b):
        spinner.start()
        ping_lbl.set_text("Test in corso...")

        def worker():
            out = run_capture(["ping", "-c", "2", "-W", "2", "1.1.1.1"], timeout=8)
            ok = "0% packet loss" in out or " 0% packet" in out
            m = re.search(r"min/avg/max\S*\s*=\s*[\d.]+/([\d.]+)", out)
            avg = f"  (avg {m.group(1)} ms)" if m else ""
            txt = ("Connessione OK" + avg) if ok else "Nessuna connettivita' (1.1.1.1 irraggiungibile)"
            GLib.idle_add(finish, txt)

        def finish(txt):
            spinner.stop()
            ping_lbl.set_text("Connettivita': " + txt)
            return False

        threading.Thread(target=worker, daemon=True).start()

    def do_apply(_b):
        iface = cb_if.get_active_text()
        if not iface:
            info_dialog("Rete", "Nessuna interfaccia selezionata.", level="warn", parent=win)
            return
        if rb_static.get_active():
            ip = e_ip.get_text().strip()
            mask = e_mask.get_text().strip() or "255.255.255.0"
            gw = e_gw.get_text().strip()
            dns = e_dns.get_text().strip()
            if not _valid_ipv4(ip):
                info_dialog("Rete", "Indirizzo IP non valido.", level="warn", parent=win)
                return
            if not _valid_ipv4(mask):
                info_dialog("Rete", "Maschera non valida.", level="warn", parent=win)
                return
            if gw and not _valid_ipv4(gw):
                info_dialog("Rete", "Gateway non valido.", level="warn", parent=win)
                return
            if dns and not _valid_ipv4(dns):
                info_dialog("Rete", "DNS non valido.", level="warn", parent=win)
                return
            script = (
                f"pkill -f 'udhcpc.*{iface}' 2>/dev/null; "
                f"ifconfig {iface} {ip} netmask {mask} up && "
                f"{{ [ -n '{gw}' ] && {{ route del default 2>/dev/null; route add default gw {gw}; }}; }}; "
                f"{{ [ -n '{dns}' ] && echo 'nameserver {dns}' > /etc/resolv.conf; }}; true"
            )
            descr = f"IP statico {ip}/{mask} su {iface}"
        else:
            script = (
                f"pkill -f 'udhcpc.*{iface}' 2>/dev/null; "
                f"ifconfig {iface} up; "
                f"udhcpc -b -i {iface} -t 8 -T 2 2>&1"
            )
            descr = f"DHCP su {iface}"

        spinner.start()
        ping_lbl.set_text("Applico: " + descr + " ...")

        def worker():
            out = run_capture(["sudo", "sh", "-c", script], timeout=25)
            def finish():
                spinner.stop()
                refresh()
                ping_lbl.set_text("Applicato: " + descr)
                if out:
                    print("[rete] " + out, flush=True)
                return False
            GLib.idle_add(finish)

        threading.Thread(target=worker, daemon=True).start()

    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    b_apply = icon_button("Applica", "emblem-ok", primary=True)
    b_apply.connect("clicked", do_apply)
    b_ping = icon_button("Test connessione", "network-transmit-receive")
    b_ping.connect("clicked", do_ping)
    b_ref = icon_button("Aggiorna", "view-refresh")
    b_ref.connect("clicked", refresh)
    b_close = icon_button("Chiudi", "window-close")
    b_close.connect("clicked", lambda _b: win.destroy())
    bar.pack_start(b_apply, False, False, 0)
    bar.pack_start(b_ping, False, False, 0)
    bar.pack_start(spinner, False, False, 0)
    bar.pack_start(b_ref, False, False, 0)
    bar.pack_end(b_close, False, False, 0)
    body.pack_end(bar, False, False, 0)

    win.show_all()


# ---------------------------------------------------------------------------
# Pacchetti (gestore apk nativo di Alpine)
# ---------------------------------------------------------------------------
def _priv():
    """Comando per privilegi (doas su Alpine, fallback sudo)."""
    import shutil
    if shutil.which("doas"):
        return ["doas"]
    if shutil.which("sudo"):
        return ["sudo"]
    return []


def open_packages(_btn=None):
    win, body = panel_window("Gestore pacchetti (apk)", 720, 540)
    priv = _priv()

    # Barra di ricerca
    top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    entry = Gtk.Entry()
    entry.set_placeholder_text("Cerca un pacchetto Alpine (es. nmap, ripgrep)...")
    entry.set_hexpand(True)
    btn_search = Gtk.Button(label="Cerca")
    btn_search.get_style_context().add_class("nxs-primary")
    spinner = Gtk.Spinner()
    top.pack_start(entry, True, True, 0)
    top.pack_start(btn_search, False, False, 0)
    top.pack_start(spinner, False, False, 0)
    body.pack_start(top, False, False, 0)

    # Risultati
    store = Gtk.ListStore(str, str, str)  # nome, versione, descrizione
    tree = Gtk.TreeView(model=store)
    for i, title in enumerate(("Pacchetto", "Versione", "Descrizione")):
        rend = Gtk.CellRendererText()
        if i == 2:
            rend.set_property("ellipsize", Pango.EllipsizeMode.END)
        col = Gtk.TreeViewColumn(title, rend, text=i)
        col.set_resizable(True)
        col.set_expand(i == 2)
        tree.append_column(col)
    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    sw.add(tree)
    body.pack_start(sw, True, True, 0)

    # Console output
    out_view = Gtk.TextView()
    out_view.set_editable(False)
    out_view.set_monospace(True)
    out_buf = out_view.get_buffer()
    out_sw = Gtk.ScrolledWindow()
    out_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    out_sw.set_min_content_height(120)
    out_sw.add(out_view)
    body.pack_start(out_sw, False, False, 0)

    def log(text):
        end = out_buf.get_end_iter()
        out_buf.insert(end, text)
        out_view.scroll_to_iter(out_buf.get_end_iter(), 0.0, False, 0, 0)

    busy = {"on": False}

    def set_busy(on):
        busy["on"] = on
        btn_search.set_sensitive(not on)
        btn_install.set_sensitive(not on)
        (spinner.start if on else spinner.stop)()

    def do_search(*_a):
        q = entry.get_text().strip()
        if not q or busy["on"]:
            return
        store.clear()
        set_busy(True)
        log(f"\n$ apk search -v {q}\n")

        def worker():
            out = run_capture(["apk", "search", "-v", q], timeout=60)
            GLib.idle_add(finish, out)

        def finish(out):
            count = 0
            for line in out.splitlines():
                # formato apk: "<nome>-<versione> - <descrizione>" oppure
                # "<nome>-<versione> <descrizione>"; la versione inizia con cifra.
                m = re.match(r"(\S+?)-(\d\S*)\s+-?\s*(.*)", line)
                if m:
                    store.append([m.group(1), m.group(2), m.group(3)])
                    count += 1
                elif line.strip():
                    store.append([line.split()[0], "", ""])
                    count += 1
            log(f"  {count} risultati.\n" if count else "  Nessun risultato (serve rete? prova 'Aggiorna indice').\n")
            set_busy(False)
            return False

        threading.Thread(target=worker, daemon=True).start()

    def do_install(*_a):
        sel = tree.get_selection().get_selected()
        if not sel[1] or busy["on"]:
            info_dialog("Nessuna selezione", "Seleziona un pacchetto dalla lista.", parent=win)
            return
        name = store.get_value(sel[1], 0)
        set_busy(True)
        log(f"\n$ {' '.join(priv)} apk add {name}\n")

        def worker():
            try:
                proc = subprocess.Popen(
                    priv + ["apk", "add", name],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for line in proc.stdout:
                    GLib.idle_add(log, line)
                proc.wait()
                GLib.idle_add(log, f"\n[exit {proc.returncode}]\n")
            except Exception as e:  # noqa: BLE001
                GLib.idle_add(log, f"\nerrore: {e}\n")
            GLib.idle_add(lambda: (set_busy(False), False)[1])

        threading.Thread(target=worker, daemon=True).start()

    btn_search.connect("clicked", do_search)
    entry.connect("activate", do_search)

    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    btn_install = Gtk.Button(label="Installa selezionato")
    btn_install.get_style_context().add_class("nxs-primary")
    btn_install.connect("clicked", do_install)
    btn_update = Gtk.Button(label="Aggiorna indice")
    def do_update(*_a):
        if busy["on"]:
            return
        set_busy(True)
        log(f"\n$ {' '.join(priv)} apk update\n")
        def worker():
            out = run_capture(priv + ["apk", "update"], timeout=120)
            GLib.idle_add(log, out + "\n")
            GLib.idle_add(lambda: (set_busy(False), False)[1])
        threading.Thread(target=worker, daemon=True).start()
    btn_update.connect("clicked", do_update)
    btn_close = Gtk.Button(label="Chiudi")
    btn_close.connect("clicked", lambda _b: win.destroy())
    bar.pack_start(btn_install, False, False, 0)
    bar.pack_start(btn_update, False, False, 0)
    bar.pack_end(btn_close, False, False, 0)
    body.pack_start(bar, False, False, 0)

    win.show_all()


# ---------------------------------------------------------------------------
# Hotkey (tabella)
# ---------------------------------------------------------------------------
HOTKEYS = [
    ("Super + T", "Terminale"),
    ("Super + E", "File manager"),
    ("Super + C", "Centro di Controllo"),
    ("Super + D", "Mostra / nascondi desktop"),
    ("Super + Up", "Massimizza finestra"),
    ("Super + Down", "Riduci a icona"),
    ("Super + Left / Right", "Aggancia a meta' schermo"),
    ("Super + F", "Schermo intero"),
    ("Super + S", "Arrotola (shade) la titlebar"),
    ("Alt + F4", "Chiudi finestra"),
    ("Alt + Tab", "Finestra successiva"),
    ("Alt + Shift + Tab", "Finestra precedente"),
    ("Alt + trascina", "Sposta la finestra"),
    ("Alt + tasto dx trascina", "Ridimensiona la finestra"),
    ("Print", "Screenshot fullscreen in /tmp"),
    ("XF86Audio Raise/Lower/Mute", "Volume (amixer/pactl)"),
    ("Super + F1 / F2 / F3", "Volume mute / giu' / su'"),
    ("XF86MonBrightness Up/Down", "Luminosita'"),
    ("Super + F5 / F6", "Luminosita' giu' / su'"),
    ("Super + L", "Blocca schermo (xtrlock)"),
    ("Tasto dx desktop", "Menu NexusSec"),
    ("Tasto centrale desktop", "Lista finestre"),
]


def open_hotkeys(_btn=None):
    win, body = panel_window("Tasti rapidi", 560, 560)
    store = Gtk.ListStore(str, str)
    for k, v in HOTKEYS:
        store.append([k, v])
    tree = Gtk.TreeView(model=store)
    tree.set_headers_visible(True)
    c0 = Gtk.TreeViewColumn("Tasto", Gtk.CellRendererText(), text=0)
    c0.set_min_width(220)
    rend = Gtk.CellRendererText()
    c1 = Gtk.TreeViewColumn("Azione", rend, text=1)
    c1.set_expand(True)
    tree.append_column(c0)
    tree.append_column(c1)
    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    sw.add(tree)
    body.pack_start(sw, True, True, 0)

    btn = Gtk.Button(label="Chiudi")
    btn.connect("clicked", lambda _b: win.destroy())
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    box.pack_end(btn, False, False, 0)
    body.pack_end(box, False, False, 0)
    win.show_all()


# ---------------------------------------------------------------------------
# Pannello inferiore (nxs-panel) - gestione
# ---------------------------------------------------------------------------
def _panel_running() -> bool:
    out = run_capture(["pgrep", "-f", "nxs_cc.panel"])
    return bool(out.strip())


def _panel_start():
    subprocess.Popen(["sh", "-c", "nxs-panel >/tmp/nxs-panel.log 2>&1 &"])


def _panel_stop():
    subprocess.Popen(["pkill", "-f", "nxs_cc.panel"])


def _panel_restart():
    # pkill DIRETTO (si auto-esclude) + launcher il cui argv NON contiene
    # "nxs_cc.panel" (altrimenti pkill -f ucciderebbe la shell del rilancio).
    subprocess.run(["pkill", "-f", "nxs_cc.panel"])
    subprocess.Popen(["sh", "-c", "sleep 0.4; exec nxs-panel"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)


def open_statusbar(_btn=None):
    win, body = panel_window("Pannello inferiore", 520, 360)

    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    card.get_style_context().add_class("nxs-card")
    title = Gtk.Label(label="Pannello nativo stile MATE")
    title.set_xalign(0)
    title.get_style_context().add_class("nxs-card-title")
    card.pack_start(title, False, False, 0)
    desc = Gtk.Label(label=(
        "Barra GTK3 con icone, larga quanto lo schermo, agganciabile in\n"
        "basso o in alto. A sinistra: menu NexusSec e lanciatori (Terminale,\n"
        "File, Centro). Al centro: la lista delle finestre aperte (clic per\n"
        "attivare, clic sulla finestra attiva per minimizzarla). A destra:\n"
        "orologio e pulsante \"mostra desktop\".\n\n"
        "Lo spazio sul bordo e' riservato da Openbox (rc.xml) cosi' le\n"
        "finestre massimizzate non coprono il pannello."))
    desc.set_xalign(0)
    desc.get_style_context().add_class("nxs-val")
    card.pack_start(desc, False, False, 0)
    body.pack_start(card, False, False, 0)

    # Posizione (basso / alto)
    frame_pos = Gtk.Frame(label="Posizione")
    pbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    pbox.set_margin_top(8); pbox.set_margin_bottom(8)
    pbox.set_margin_start(10); pbox.set_margin_end(10)
    rb_bottom = Gtk.RadioButton.new_with_label_from_widget(None, "In basso")
    rb_top = Gtk.RadioButton.new_with_label_from_widget(rb_bottom, "In alto")
    if panelcfg.get_position() == "top":
        rb_top.set_active(True)
    pbox.pack_start(rb_bottom, False, False, 0)
    pbox.pack_start(rb_top, False, False, 0)
    b_applypos = Gtk.Button(label="Applica posizione")
    b_applypos.get_style_context().add_class("nxs-primary")

    def apply_pos(_b):
        pos = "top" if rb_top.get_active() else "bottom"
        panelcfg.move_panel(pos)
        info_dialog("Pannello spostato",
                    "Posizione: %s. Openbox ricaricato e pannello riavviato."
                    % ("in alto" if pos == "top" else "in basso"), parent=win)
    b_applypos.connect("clicked", apply_pos)
    pbox.pack_end(b_applypos, False, False, 0)
    frame_pos.add(pbox)
    body.pack_start(frame_pos, False, False, 0)

    # Stato
    state = Gtk.Label()
    state.set_xalign(0)

    def refresh_state():
        running = _panel_running()
        state.set_markup(
            "Stato: <span foreground='%s'>in esecuzione</span>" % COL_ACCENT
            if running else
            "Stato: <span foreground='%s'>non attivo</span>" % COL_ALERT)
    refresh_state()
    body.pack_start(state, False, False, 4)

    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    b_restart = Gtk.Button(label="Riavvia pannello")
    b_restart.get_style_context().add_class("nxs-primary")

    def do_restart(_b):
        _panel_restart()
        GLib.timeout_add(700, lambda: (refresh_state(), False)[1])
    b_restart.connect("clicked", do_restart)

    b_start = Gtk.Button(label="Avvia")
    b_start.connect("clicked", lambda _b: (_panel_start(),
                    GLib.timeout_add(700, lambda: (refresh_state(), False)[1])))
    b_stop = Gtk.Button(label="Termina")
    b_stop.connect("clicked", lambda _b: (_panel_stop(),
                   GLib.timeout_add(700, lambda: (refresh_state(), False)[1])))
    b_close = Gtk.Button(label="Chiudi")
    b_close.connect("clicked", lambda _b: win.destroy())
    bar.pack_start(b_restart, False, False, 0)
    bar.pack_start(b_start, False, False, 0)
    bar.pack_start(b_stop, False, False, 0)
    bar.pack_end(b_close, False, False, 0)
    body.pack_end(bar, False, False, 0)

    win.show_all()


# ---------------------------------------------------------------------------
# Openbox: temi finestra e menu tasto destro
# ---------------------------------------------------------------------------
RC_XML = HOME / ".config/openbox/rc.xml"
MENU_XML = HOME / ".config/openbox/menu.xml"
THEME_DIRS = [
    HOME / ".themes",
    HOME / ".local/share/themes",
    Path("/usr/local/share/themes"),
    Path("/usr/share/themes"),
]


def _ob_list_themes() -> list[str]:
    """Nomi dei temi Openbox installati (cartelle con openbox-3/themerc)."""
    found = set()
    for d in THEME_DIRS:
        try:
            for sub in d.iterdir():
                if (sub / "openbox-3" / "themerc").is_file():
                    found.add(sub.name)
        except OSError:
            pass
    return sorted(found)


def _ob_current_theme() -> str:
    try:
        m = re.search(r"<theme>.*?<name>([^<]+)</name>", RC_XML.read_text(),
                      re.DOTALL)
        if m:
            return m.group(1).strip()
    except OSError:
        pass
    return ""


def _ob_set_theme(name: str):
    try:
        txt = RC_XML.read_text()
    except OSError:
        return
    txt = re.sub(r"(<theme>.*?<name>)[^<]*(</name>)",
                 r"\g<1>" + name + r"\g<2>", txt, count=1, flags=re.DOTALL)
    RC_XML.write_text(txt)
    panelcfg.openbox_reconfigure()


def open_openbox_theme(_btn=None):
    print("[cc] ob-theme: start", flush=True)
    win, body = panel_window("Temi finestre (Openbox)", 480, 460)
    print("[cc] ob-theme: finestra creata", flush=True)

    lab = Gtk.Label(label="Bordi e decorazioni delle finestre. "
                          "Doppio clic per applicare.")
    lab.set_xalign(0)
    lab.get_style_context().add_class("nxs-val")
    body.pack_start(lab, False, False, 0)

    store = Gtk.ListStore(str)
    cur = _ob_current_theme()
    themes = _ob_list_themes()
    for t in themes:
        store.append([t + ("   (attuale)" if t == cur else "")])
    tree = Gtk.TreeView(model=store)
    tree.set_headers_visible(False)
    col = Gtk.TreeViewColumn("Tema", Gtk.CellRendererText(), text=0)
    tree.append_column(col)
    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    sw.add(tree)
    body.pack_start(sw, True, True, 0)

    def selected_theme():
        model, it = tree.get_selection().get_selected()
        if it is None:
            return None
        return model[it][0].split("   ")[0].strip()

    def apply(_w=None, *_a):
        name = selected_theme()
        if not name:
            return
        _ob_set_theme(name)
        # aggiorna l'etichetta (attuale)
        store.clear()
        for t in themes:
            store.append([t + ("   (attuale)" if t == name else "")])
        info_dialog("Tema applicato", "Tema finestre: %s" % name, parent=win)

    tree.connect("row-activated", apply)

    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    b_apply = Gtk.Button(label="Applica")
    b_apply.get_style_context().add_class("nxs-primary")
    b_apply.connect("clicked", apply)
    bar.pack_start(b_apply, False, False, 0)
    if have("obconf"):
        b_adv = Gtk.Button(label="Configurazione avanzata (obconf)")
        b_adv.connect("clicked", lambda _b: run_bg(["obconf"]))
        bar.pack_start(b_adv, False, False, 0)
    b_close = Gtk.Button(label="Chiudi")
    b_close.connect("clicked", lambda _b: win.destroy())
    bar.pack_end(b_close, False, False, 0)
    body.pack_end(bar, False, False, 0)

    print("[cc] ob-theme: prima di show_all", flush=True)
    win.show_all()
    print("[cc] ob-theme: show_all OK", flush=True)


def open_menu_editor(_btn=None):
    # Versione autonoma e strumentata (i print con flush localizzano un
    # eventuale crash nativo in /tmp/nxs-cc.log).
    print("[cc] menu-editor: start", flush=True)
    win, body = panel_window("Menu tasto destro (Openbox)", 760, 560)
    print("[cc] menu-editor: finestra creata", flush=True)
    tv = Gtk.TextView()
    tv.set_monospace(True)
    tv.set_left_margin(8)
    tv.set_top_margin(6)
    txt = read_file(MENU_XML)
    print("[cc] menu-editor: letto menu.xml (%d bytes)" % len(txt), flush=True)
    tv.get_buffer().set_text(txt)
    print("[cc] menu-editor: buffer impostato", flush=True)
    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    sw.add(tv)
    body.pack_start(sw, True, True, 0)

    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    b_save = Gtk.Button(label="Salva e ricarica Openbox")
    b_save.get_style_context().add_class("nxs-primary")

    def save(_b):
        try:
            buf = tv.get_buffer()
            s, e = buf.get_bounds()
            MENU_XML.write_text(buf.get_text(s, e, False))
            panelcfg.openbox_reconfigure()
            info_dialog("Salvato", "Menu aggiornato e Openbox ricaricato.",
                        parent=win)
        except Exception as err:                       # noqa: BLE001
            info_dialog("Errore", str(err), level="error", parent=win)

    b_save.connect("clicked", save)
    b_close = Gtk.Button(label="Chiudi")
    b_close.connect("clicked", lambda _b: win.destroy())
    bar.pack_start(b_save, False, False, 0)
    bar.pack_end(b_close, False, False, 0)
    body.pack_end(bar, False, False, 0)

    print("[cc] menu-editor: prima di show_all", flush=True)
    win.show_all()
    print("[cc] menu-editor: show_all OK", flush=True)


# ---------------------------------------------------------------------------
# Editor di testo (autostart, rc.xml)
# ---------------------------------------------------------------------------
def open_text_editor(title: str, path: Path, on_save=None):
    win, body = panel_window(title, 760, 560)
    tv = Gtk.TextView()
    tv.set_monospace(True)
    tv.set_left_margin(8); tv.set_top_margin(6)
    tv.get_buffer().set_text(read_file(path))
    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    sw.add(tv)
    body.pack_start(sw, True, True, 0)

    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    b_save = Gtk.Button(label="Salva")
    b_save.get_style_context().add_class("nxs-primary")

    def save(_b):
        buf = tv.get_buffer()
        s, e = buf.get_bounds()
        try:
            Path(path).write_text(buf.get_text(s, e, False))
            if on_save is not None:
                on_save()
            info_dialog("Salvato", f"Scritto: {path}", parent=win)
        except OSError as err:
            info_dialog("Errore", str(err), level="error", parent=win)

    b_save.connect("clicked", save)
    b_close = Gtk.Button(label="Chiudi")
    b_close.connect("clicked", lambda _b: win.destroy())
    bar.pack_start(b_save, False, False, 0)
    bar.pack_end(b_close, False, False, 0)
    body.pack_end(bar, False, False, 0)
    win.show_all()


AUTOSTART = HOME / ".config/openbox/autostart"
_AS_BEGIN = "# >>> NexusSec autostart utente (Centro di Controllo)"
_AS_END = "# <<< NexusSec autostart utente"


def _autostart_read_user():
    """Legge le voci utente nel blocco delimitato: lista di (abilitato, cmd)."""
    entries = []
    try:
        lines = AUTOSTART.read_text().splitlines()
    except OSError:
        return entries
    inside = False
    for ln in lines:
        s = ln.strip()
        if s == _AS_BEGIN:
            inside = True
            continue
        if s == _AS_END:
            break
        if not inside or not s:
            continue
        enabled = True
        cmd = s
        if cmd.startswith("#"):
            enabled = False
            cmd = cmd.lstrip("#").strip()
        if cmd.endswith("&"):
            cmd = cmd[:-1].strip()
        if cmd:
            entries.append((enabled, cmd))
    return entries


def _autostart_write_user(entries):
    """Riscrive SOLO il blocco utente, preservando il resto dell'autostart."""
    block = [_AS_BEGIN]
    for enabled, cmd in entries:
        cmd = cmd.strip()
        if not cmd:
            continue
        line = "%s &" % cmd
        block.append(line if enabled else "# " + line)
    block.append(_AS_END)
    block_txt = "\n".join(block)

    try:
        txt = AUTOSTART.read_text()
    except OSError:
        txt = "#!/bin/sh\n"
    if _AS_BEGIN in txt and _AS_END in txt:
        pat = re.compile(re.escape(_AS_BEGIN) + r".*?" + re.escape(_AS_END),
                         re.DOTALL)
        txt = pat.sub(block_txt, txt, count=1)
    else:
        if not txt.endswith("\n"):
            txt += "\n"
        txt += "\n" + block_txt + "\n"
    AUTOSTART.write_text(txt)


def open_autostart(_btn=None):
    print("[cc] autostart: start", flush=True)
    win, body = panel_window("Avvio automatico (Autostart)", 660, 480)

    intro = Gtk.Label(label=(
        "Programmi avviati con la sessione. Spunta per abilitare, scrivi il "
        "comando, poi premi Salva. Le voci di sistema (sfondo, pannello, "
        "desktop) restano gestite a parte."))
    intro.set_xalign(0)
    intro.set_line_wrap(True)
    intro.get_style_context().add_class("nxs-val")
    body.pack_start(intro, False, False, 0)

    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    listbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    listbox.set_margin_top(4)
    sw.add(listbox)
    body.pack_start(sw, True, True, 0)

    rows = []

    def add_row(enabled=True, cmd=""):
        rb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        chk = Gtk.CheckButton()
        chk.set_active(enabled)
        chk.set_tooltip_text("Abilitato all'avvio")
        ent = Gtk.Entry()
        ent.set_text(cmd)
        ent.set_hexpand(True)
        ent.set_placeholder_text("comando da avviare, es: nm-applet")
        rm = Gtk.Button(label="−")     # segno meno
        rm.set_tooltip_text("Rimuovi questa voce")
        rb.pack_start(chk, False, False, 0)
        rb.pack_start(ent, True, True, 0)
        rb.pack_start(rm, False, False, 0)
        listbox.pack_start(rb, False, False, 0)
        entry = {"chk": chk, "ent": ent, "box": rb}

        def remove(_b):
            listbox.remove(rb)
            if entry in rows:
                rows.remove(entry)
        rm.connect("clicked", remove)
        rows.append(entry)
        rb.show_all()

    for en, cmd in _autostart_read_user():
        add_row(en, cmd)
    if not rows:
        add_row(True, "")

    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    b_add = Gtk.Button(label="Aggiungi")
    b_add.connect("clicked", lambda _b: add_row(True, ""))
    b_save = Gtk.Button(label="Salva")
    b_save.get_style_context().add_class("nxs-primary")

    def save(_b):
        ents = [(r["chk"].get_active(), r["ent"].get_text().strip())
                for r in rows if r["ent"].get_text().strip()]
        try:
            _autostart_write_user(ents)
            info_dialog("Salvato",
                        "Voci di autostart memorizzate in:\n%s\n\n"
                        "Avranno effetto al prossimo avvio della sessione."
                        % AUTOSTART, parent=win)
        except OSError as e:
            info_dialog("Errore", str(e), level="error", parent=win)

    b_save.connect("clicked", save)
    b_raw = Gtk.Button(label="Modifica file grezzo")
    b_raw.connect("clicked",
                  lambda _b: open_text_editor("autostart (avanzato)", AUTOSTART))
    b_close = Gtk.Button(label="Chiudi")
    b_close.connect("clicked", lambda _b: win.destroy())
    bar.pack_start(b_add, False, False, 0)
    bar.pack_start(b_save, False, False, 0)
    bar.pack_start(b_raw, False, False, 0)
    bar.pack_end(b_close, False, False, 0)
    body.pack_end(bar, False, False, 0)

    print("[cc] autostart: prima di show_all", flush=True)
    win.show_all()
    print("[cc] autostart: show_all OK", flush=True)


# ---------------------------------------------------------------------------
# Log di sistema (viewer a schede)
# ---------------------------------------------------------------------------
def open_logs(_btn=None):
    win, body = panel_window("Log di sistema", 820, 560)
    nb = Gtk.Notebook()
    body.pack_start(nb, True, True, 0)
    sources = [
        ("autostart", "/tmp/nxs-autostart.log"),
        ("pannello", "/tmp/nxs-panel.log"),
        ("Xorg", os.path.expanduser("~/.local/share/xorg/Xorg.0.log")),
        ("boot", "/var/log/nxs-boot.log"),
    ]
    for label, path in sources:
        sw = Gtk.ScrolledWindow()
        tv = Gtk.TextView()
        tv.set_editable(False); tv.set_monospace(True); tv.set_left_margin(6)
        tv.get_buffer().set_text(read_file(path))
        sw.add(tv)
        nb.append_page(sw, Gtk.Label(label=label))
    win.show_all()


# ---------------------------------------------------------------------------
# Aspetto: tema GTK (lxappearance) e wallpaper
# ---------------------------------------------------------------------------
def open_gtk_theme(_btn=None):
    if have("nxs-lxappearance"):
        run_bg(["nxs-lxappearance"])
    elif have("lxappearance"):
        run_bg(["lxappearance"])
    else:
        info_dialog("lxappearance assente", "Eseguire: doas apk add lxappearance", level="warn")


def open_wallpaper(_btn=None):
    dlg = Gtk.FileChooserDialog(title="Scegli sfondo", action=Gtk.FileChooserAction.OPEN, modal=True)
    dlg.add_button("Annulla", Gtk.ResponseType.CANCEL)
    dlg.add_button("Imposta", Gtk.ResponseType.ACCEPT)
    flt = Gtk.FileFilter(); flt.set_name("Immagini")
    flt.add_mime_type("image/png"); flt.add_mime_type("image/jpeg")
    dlg.add_filter(flt)
    default = HOME / ".themes/NexusSec-Core/backgrounds"
    if default.is_dir():
        dlg.set_current_folder(str(default))
    if dlg.run() == Gtk.ResponseType.ACCEPT:
        path = dlg.get_filename()
        if have("feh"):
            run_bg(["feh", "--bg-fill", path])
        else:
            info_dialog("feh assente", "Eseguire: doas apk add feh", level="warn")
    dlg.destroy()


# ---------------------------------------------------------------------------
# Tastiera
# ---------------------------------------------------------------------------
def open_keyboard(_btn=None):
    win, body = panel_window("Tastiera", 480, 420)
    info = Gtk.Label(label="Layout tastiera per la sessione grafica.")
    info.set_xalign(0)
    info.get_style_context().add_class("nxs-val")
    body.pack_start(info, False, False, 0)

    def set_layout(name):
        if name == "it" and (HOME / ".Xmodmap-it").exists():
            subprocess.Popen(["xmodmap", str(HOME / ".Xmodmap-it")])
            info_dialog("Layout", "Impostato: italiano", parent=win)
        else:
            subprocess.Popen(["sh", "-c", "setxkbmap us 2>/dev/null || true"])
            info_dialog("Layout", "Impostato: US (best effort)", parent=win)

    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    b_it = icon_button("Italiano", "preferences-desktop-locale")
    b_it.connect("clicked", lambda _b: set_layout("it"))
    b_us = icon_button("US", "preferences-desktop-keyboard")
    b_us.connect("clicked", lambda _b: set_layout("us"))
    row.pack_start(b_it, False, False, 0)
    row.pack_start(b_us, False, False, 0)
    body.pack_start(row, False, False, 0)

    # --- Prova tastiera: verifica caratteri e corrispondenze dei tasti -----
    frame = Gtk.Frame(label="Prova tastiera")
    fbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    fbox.set_margin_top(8); fbox.set_margin_bottom(8)
    fbox.set_margin_start(8); fbox.set_margin_end(8)
    frame.add(fbox)

    hint = Gtk.Label(
        label="Scrivi qui per controllare che i caratteri corrispondano ai tasti:")
    hint.set_xalign(0)
    fbox.pack_start(hint, False, False, 0)

    entry = Gtk.Entry()
    entry.set_placeholder_text("es. è à ù ò ì @ # \\ | tasti accentati...")
    fbox.pack_start(entry, False, False, 0)

    detail = Gtk.Label(label="Premi un tasto: qui appare la corrispondenza.")
    detail.set_xalign(0)
    detail.set_selectable(True)
    detail.get_style_context().add_class("nxs-key")
    fbox.pack_start(detail, False, False, 0)

    def on_key(_w, ev):
        name = Gdk.keyval_name(ev.keyval) or "?"
        uni = Gdk.keyval_to_unicode(ev.keyval)
        ch = chr(uni) if uni and uni >= 32 else ""
        mods = []
        if ev.state & Gdk.ModifierType.CONTROL_MASK: mods.append("Ctrl")
        if ev.state & Gdk.ModifierType.MOD1_MASK:    mods.append("Alt")
        if ev.state & Gdk.ModifierType.SHIFT_MASK:   mods.append("Shift")
        if ev.state & Gdk.ModifierType.MOD4_MASK:    mods.append("Super")
        modstr = " + ".join(mods + [name]) if mods else name
        car = f"  carattere: '{ch}'" if ch else ""
        detail.set_text(
            f"tasto: {modstr}   keysym: {name}   keycode: {ev.hardware_keycode}{car}")
        return False  # lascia che l'entry riceva comunque il tasto

    entry.connect("key-press-event", on_key)
    body.pack_start(frame, True, True, 0)

    b_close = icon_button("Chiudi", "window-close")
    b_close.connect("clicked", lambda _b: win.destroy())
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    box.pack_end(b_close, False, False, 0)
    body.pack_end(box, False, False, 0)
    win.show_all()
    entry.grab_focus()
