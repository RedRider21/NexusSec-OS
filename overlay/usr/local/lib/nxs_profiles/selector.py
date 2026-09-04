"""Selettore grafico del profilo operativo NexusSec (GTK3).

Mostrato all'avvio (e richiamabile da menu/pannello). Presenta i profili
come schede; selezionandone uno applica il profilo: imposta il profilo
corrente, cambia lo SFONDO inerente alla modalita' e fa si' che il menu del
pannello mostri solo i tool pertinenti (il pannello rilegge il profilo alla
prossima apertura del menu).
"""
from __future__ import annotations

import sys

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk  # noqa: E402

from . import model

# Riusa CSS/tema del Centro di Controllo (stesso /usr/local/lib).
try:
    from nxs_cc.common import apply_css
except Exception:                     # noqa: BLE001
    def apply_css():
        pass

_EXTRA_CSS = b"""
.nxs-profilo-card {
  background-color: #0a1422; border: 1px solid #1a3a52;
  border-radius: 4px; padding: 14px; margin: 6px; min-width: 210px;
}
.nxs-profilo-card:hover { background-color: #0c1a2a; }
.nxs-profilo-name { font-weight: bold; font-size: 13pt; }
.nxs-profilo-desc { color: #5a8a9a; font-size: 9pt; }
.nxs-profilo-accent { min-height: 5px; border-radius: 2px; margin-bottom: 8px; }
"""


def _hex_to_rgba(h: str, a: float) -> str:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        r, g, b = 0, 229, 255
    return "rgba(%d,%d,%d,%.2f)" % (r, g, b, a)


def _card_css(accent: str) -> bytes:
    # Hover/selezione: si applicano al BOTTONE (la scheda stessa), quindi il
    # provider agganciato al contesto della scheda li colpisce correttamente.
    # NB: la barretta accent NON puo' stare qui: e' un widget FIGLIO del bottone
    # e in GTK3 un provider agganciato a un widget vale solo per quel widget, non
    # per i suoi figli -> il colore non la raggiungerebbe (banda trasparente).
    return (
        ".nxs-profilo-card:hover { border-color: %s; }"
        ".nxs-profilo-card.sel { border-color: %s; background-color: %s; }"
        % (accent, accent, _hex_to_rgba(accent, 0.12))
    ).encode()


def _accent_css(accent: str) -> bytes:
    # Colore della barretta accent: provider agganciato alla BARRETTA stessa,
    # cosi' ogni scheda mostra la banda col colore del proprio profilo.
    return (".nxs-profilo-accent { background-color: %s; }" % accent).encode()


class Selector(Gtk.Window):
    def __init__(self):
        super().__init__(title="NexusSec - Profilo operativo")
        apply_css()
        prov = Gtk.CssProvider()
        prov.load_from_data(_EXTRA_CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        # Altezza generosa: con 5 profili su 3 colonne la seconda riga deve
        # vedersi interamente (prima l'ultima riga risultava tagliata a meta').
        self.set_default_size(760, 660)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_keep_above(True)
        self.connect("destroy", Gtk.main_quit)

        self._selected = model.current_profile()
        self._cards = {}

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(outer)

        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        header.get_style_context().add_class("nxs-headerbar")
        eb = Gtk.Label(label="NEXUSSEC OS  ·  PROFILO OPERATIVO"); eb.set_xalign(0)
        eb.get_style_context().add_class("nxs-eyebrow")
        header.pack_start(eb, False, False, 0)
        t = Gtk.Label(label="Seleziona la modalita' operativa"); t.set_xalign(0)
        t.get_style_context().add_class("title")
        s = Gtk.Label(label="Il menu e lo sfondo si adattano al profilo scelto")
        s.set_xalign(0); s.get_style_context().add_class("subtitle")
        header.pack_start(t, False, False, 0)
        header.pack_start(s, False, False, 0)
        outer.pack_start(header, False, False, 0)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        outer.pack_start(sw, True, True, 0)

        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_max_children_per_line(3)
        flow.set_min_children_per_line(1)
        flow.set_homogeneous(True)
        flow.set_margin_top(10); flow.set_margin_bottom(10)
        flow.set_margin_start(12); flow.set_margin_end(12)
        sw.add(flow)

        for key, d in model.profiles().items():
            flow.add(self._make_card(key, d))

        # Pulsanti
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.get_style_context().add_class("nxs-footer")
        self.hint = Gtk.Label(label=""); self.hint.set_xalign(0)
        bar.pack_start(self.hint, True, True, 0)
        self._clean = Gtk.CheckButton(label="Pulisci profilo precedente")
        self._clean.set_tooltip_text(
            "Monomissione: rimuove il meta-pacchetto del profilo precedente (apk del)")
        bar.pack_start(self._clean, False, False, 0)
        cancel = Gtk.Button(label="Annulla")
        cancel.connect("clicked", lambda *_: self.destroy())
        bar.pack_start(cancel, False, False, 0)
        apply_btn = Gtk.Button(label="Applica profilo")
        apply_btn.get_style_context().add_class("nxs-primary")
        apply_btn.connect("clicked", self._on_apply)
        bar.pack_start(apply_btn, False, False, 0)
        outer.pack_start(bar, False, False, 0)

        self._highlight(self._selected)

    def _make_card(self, key, d):
        btn = Gtk.Button()
        btn.set_relief(Gtk.ReliefStyle.NONE)
        ctx = btn.get_style_context()
        ctx.add_class("nxs-profilo-card")

        # Provider col colore del profilo agganciato alla SCHEDA (btn): tinge
        # barretta, hover e selezione di questa sola scheda col suo accent.
        accent = d.get("accent", "#00e5ff")
        prov = Gtk.CssProvider(); prov.load_from_data(_card_css(accent))
        ctx.add_provider(prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        bar = Gtk.Box()
        bctx = bar.get_style_context()
        bctx.add_class("nxs-profilo-accent")
        # Il colore va sul provider della barretta stessa (i provider di widget
        # non ereditano ai figli: sul bottone non la raggiungerebbe).
        bprov = Gtk.CssProvider(); bprov.load_from_data(_accent_css(accent))
        bctx.add_provider(bprov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        box.pack_start(bar, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        img = Gtk.Image.new_from_icon_name(d.get("icon", "preferences-system"),
                                           Gtk.IconSize.DND)
        row.pack_start(img, False, False, 0)
        name = Gtk.Label(label=d.get("name", key)); name.set_xalign(0)
        name.get_style_context().add_class("nxs-profilo-name")
        row.pack_start(name, True, True, 0)
        box.pack_start(row, False, False, 0)

        desc = Gtk.Label(label=d.get("desc", "")); desc.set_xalign(0)
        desc.set_line_wrap(True); desc.set_max_width_chars(28)
        desc.get_style_context().add_class("nxs-profilo-desc")
        box.pack_start(desc, False, False, 0)

        ntools = len(d.get("tools", []))
        cnt = Gtk.Label(label=("%d strumenti" % ntools) if ntools else "sistema base")
        cnt.set_xalign(0); cnt.get_style_context().add_class("nxs-profilo-desc")
        box.pack_start(cnt, False, False, 0)

        btn.add(box)
        btn.connect("clicked", lambda *_: self._highlight(key))
        self._cards[key] = btn
        return btn

    def _highlight(self, key):
        self._selected = key
        for k, b in self._cards.items():
            ctx = b.get_style_context()
            if k == key:
                ctx.add_class("sel")
            else:
                ctx.remove_class("sel")
        d = model.profile_data(key)
        self.hint.set_text("Profilo: %s" % d.get("name", key))

    def _on_apply(self, _btn):
        model.activate_profile(self._selected,
                               clean_previous=self._clean.get_active())
        # Riavvia il pannello cosi' l'accent del profilo viene ricaricato e il
        # menu si ripopola col profilo nuovo (il pannello e' un processo a se').
        #
        # ATTENZIONE (bug storico): NON mettere "pkill -f nxs_cc.panel" dentro la
        # stessa shell che poi rilancia, perche' "nxs_cc.panel" comparirebbe
        # nell'argv di quella shell e "pkill -f" la ucciderebbe (suicidio) PRIMA
        # del rilancio -> la barra spariva e non tornava. Quindi: pkill DIRETTO
        # (si auto-esclude sempre), poi un launcher separato il cui argv NON
        # contiene il pattern ("nxs-panel" != "nxs_cc.panel").
        try:
            import subprocess
            subprocess.run(["pkill", "-f", "nxs_cc.panel"])
            subprocess.Popen(
                ["sh", "-c", "sleep 0.4; exec nxs-panel"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True)
        except Exception:                # noqa: BLE001
            pass
        self.destroy()


def run(argv=None) -> int:
    apply_css()
    _ = argv
    w = Selector()
    w.show_all()
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
