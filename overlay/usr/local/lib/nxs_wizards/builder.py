"""Costruttore di wizard personalizzati (GTK3).

Editor grafico che compone una ricetta (schema v2) e la salva in
~/.config/nxs/wizards/<id>.json tramite recipes.save_custom(). Gli standard
restano intatti: i personalizzati si aggiungono all'elenco (e possono
sovrascrivere uno standard solo se l'utente usa lo stesso id, cosa che qui
evitiamo generando un id univoco dal nome).

Struttura editabile:
  - base      : nome, descrizione, icona, profilo;
  - campi     : input testuali/file richiesti all'utente (chiave -> {chiave});
  - modalita' : intensita' a scelta singola, ognuna con variabili name=value
                usabili negli args (es. timing=-T4);
  - opzioni   : spunte indipendenti che abilitano step (needs);
  - step      : tool del catalogo + argomenti + gate (solo modalita' / richiede
                opzioni). L'ordine conta: si puo' riordinare.

Niente dipendenza da gui.py (nessun ciclo di import).
"""
from __future__ import annotations

import json
import re

from nxs_cc import common
from gi.repository import Gtk

from nxs_profiles import model
from . import recipes

_PROFILES = [("(nessuno / generico)", None), ("Pen Testing", "pentest"),
             ("OSINT", "osint"), ("Forensics", "forensics"),
             ("Web", "web"), ("Base", "base")]


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return s or "wizard"


def _split_csv(text: str) -> list[str]:
    return [x.strip() for x in (text or "").split(",") if x.strip()]


def _tool_ids() -> list[str]:
    try:
        return sorted(json.loads(model.REPO_JSON.read_text())["tools"].keys())
    except Exception:
        return []


# --------------------------------------------------------------- righe dinamiche
class _FieldRow:
    def __init__(self, builder, data=None):
        self.builder = builder
        data = data or {}
        self.widget = Gtk.Frame()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(6); box.set_margin_bottom(6)
        box.set_margin_start(6); box.set_margin_end(6)
        self.widget.add(box)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.key = Gtk.Entry(); self.key.set_placeholder_text("chiave (es. target)")
        self.key.set_text(data.get("key", ""))
        self.type = Gtk.ComboBoxText()
        self.type.append("text", "testo"); self.type.append("file", "file")
        self.type.set_active_id(data.get("type", "text"))
        self.req = Gtk.CheckButton.new_with_label("obbligatorio")
        self.req.set_active(bool(data.get("required", True)))
        rm = common.icon_button("", "list-remove-symbolic")
        rm.connect("clicked", lambda _b: builder._remove(builder.field_rows, self))
        top.pack_start(Gtk.Label(label="Chiave:"), False, False, 0)
        top.pack_start(self.key, True, True, 0)
        top.pack_start(self.type, False, False, 0)
        top.pack_start(self.req, False, False, 0)
        top.pack_end(rm, False, False, 0)
        box.pack_start(top, False, False, 0)

        self.label = Gtk.Entry()
        self.label.set_placeholder_text("etichetta mostrata (es. IP o dominio)")
        self.label.set_text(data.get("label", ""))
        self.ph = Gtk.Entry()
        self.ph.set_placeholder_text("suggerimento/placeholder (opz.)")
        self.ph.set_text(data.get("placeholder", ""))
        box.pack_start(self.label, False, False, 0)
        box.pack_start(self.ph, False, False, 0)

    def to_dict(self):
        key = _slug(self.key.get_text())
        return {"key": key,
                "label": self.label.get_text().strip() or key,
                "placeholder": self.ph.get_text().strip(),
                "type": self.type.get_active_id() or "text",
                "required": self.req.get_active()}


class _ModeRow:
    def __init__(self, builder, data=None):
        self.builder = builder
        data = data or {}
        self.widget = Gtk.Frame()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(6); box.set_margin_bottom(6)
        box.set_margin_start(6); box.set_margin_end(6)
        self.widget.add(box)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.label = Gtk.Entry()
        self.label.set_placeholder_text("nome modalita' (es. Leggero)")
        self.label.set_text(data.get("label", ""))
        self.default = Gtk.CheckButton.new_with_label("predefinita")
        self.default.set_active(bool(data.get("default")))
        rm = common.icon_button("", "list-remove-symbolic")
        rm.connect("clicked", lambda _b: builder._remove(builder.mode_rows, self))
        top.pack_start(Gtk.Label(label="Modalita':"), False, False, 0)
        top.pack_start(self.label, True, True, 0)
        top.pack_start(self.default, False, False, 0)
        top.pack_end(rm, False, False, 0)
        box.pack_start(top, False, False, 0)

        self.desc = Gtk.Entry()
        self.desc.set_placeholder_text("descrizione breve (opz.)")
        self.desc.set_text(data.get("desc", ""))
        box.pack_start(self.desc, False, False, 0)

        self.vars = Gtk.Entry()
        self.vars.set_placeholder_text("variabili: nome=valore, nome2=valore2 (usabili come {nome} negli args)")
        vv = data.get("vars") or {}
        self.vars.set_text(", ".join(f"{k}={v}" for k, v in vv.items()))
        box.pack_start(self.vars, False, False, 0)

    def to_dict(self):
        label = self.label.get_text().strip()
        varmap = {}
        for pair in _split_csv(self.vars.get_text()):
            if "=" in pair:
                k, v = pair.split("=", 1)
                if k.strip():
                    varmap[k.strip()] = v.strip()
        return {"id": _slug(label), "label": label or "Modalita'",
                "desc": self.desc.get_text().strip(),
                "default": self.default.get_active(), "vars": varmap}


class _OptionRow:
    def __init__(self, builder, data=None):
        self.builder = builder
        data = data or {}
        self.widget = Gtk.Frame()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(6); box.set_margin_bottom(6)
        box.set_margin_start(6); box.set_margin_end(6)
        self.widget.add(box)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.label = Gtk.Entry()
        self.label.set_placeholder_text("nome opzione (es. Rilevamento OS)")
        self.label.set_text(data.get("label", ""))
        self.default = Gtk.CheckButton.new_with_label("attiva di default")
        self.default.set_active(bool(data.get("default")))
        rm = common.icon_button("", "list-remove-symbolic")
        rm.connect("clicked", lambda _b: builder._remove(builder.option_rows, self))
        top.pack_start(Gtk.Label(label="Opzione:"), False, False, 0)
        top.pack_start(self.label, True, True, 0)
        top.pack_start(self.default, False, False, 0)
        top.pack_end(rm, False, False, 0)
        box.pack_start(top, False, False, 0)

        self.desc = Gtk.Entry()
        self.desc.set_placeholder_text("descrizione breve (opz.)")
        self.desc.set_text(data.get("desc", ""))
        box.pack_start(self.desc, False, False, 0)
        # id calcolato (mostrato per usarlo in 'richiede opzioni')
        self.idlbl = Gtk.Label()
        self.idlbl.set_xalign(0)
        self.idlbl.get_style_context().add_class("nxs-dim")
        self.label.connect("changed", lambda _e: self._sync_id())
        box.pack_start(self.idlbl, False, False, 0)
        self._sync_id()

    def _sync_id(self):
        self.idlbl.set_text(f"id: {_slug(self.label.get_text())}")

    def to_dict(self):
        label = self.label.get_text().strip()
        return {"id": _slug(label), "label": label or "Opzione",
                "desc": self.desc.get_text().strip(),
                "default": self.default.get_active()}


class _StepRow:
    def __init__(self, builder, data=None):
        self.builder = builder
        data = data or {}
        self.widget = Gtk.Frame()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(6); box.set_margin_bottom(6)
        box.set_margin_start(6); box.set_margin_end(6)
        self.widget.add(box)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.tool = Gtk.ComboBoxText()
        for t in builder.tools:
            self.tool.append(t, t)
        if data.get("tool"):
            self.tool.set_active_id(data["tool"])
        elif builder.tools:
            self.tool.set_active(0)
        up = common.icon_button("", "go-up-symbolic")
        down = common.icon_button("", "go-down-symbolic")
        rm = common.icon_button("", "list-remove-symbolic")
        up.connect("clicked", lambda _b: builder._move(self, -1))
        down.connect("clicked", lambda _b: builder._move(self, +1))
        rm.connect("clicked", lambda _b: builder._remove(builder.step_rows, self))
        top.pack_start(Gtk.Label(label="Tool:"), False, False, 0)
        top.pack_start(self.tool, False, False, 0)
        top.pack_end(rm, False, False, 0)
        top.pack_end(down, False, False, 0)
        top.pack_end(up, False, False, 0)
        box.pack_start(top, False, False, 0)

        self.desc = Gtk.Entry()
        self.desc.set_placeholder_text("descrizione dello step")
        self.desc.set_text(data.get("desc", ""))
        box.pack_start(self.desc, False, False, 0)

        self.args = Gtk.Entry()
        self.args.set_placeholder_text("argomenti (usa {campo}, {variabile}, {outdir}, {loot})")
        self.args.set_text(data.get("args", ""))
        box.pack_start(self.args, False, False, 0)

        gate = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.modes = Gtk.Entry()
        self.modes.set_placeholder_text("solo modalita' (id, virgola; vuoto=sempre)")
        self.modes.set_text(", ".join(data.get("modes", []) or []))
        self.needs = Gtk.Entry()
        self.needs.set_placeholder_text("richiede opzioni (id, virgola)")
        self.needs.set_text(", ".join(data.get("needs", []) or []))
        gate.pack_start(self.modes, True, True, 0)
        gate.pack_start(self.needs, True, True, 0)
        box.pack_start(gate, False, False, 0)

        # --- stealth per-step ---
        s = data.get("stealth") or {}
        srow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.anon = Gtk.ComboBoxText()
        for k, lab in (("tor", "via Tor"), ("raw", "non anonimizz. (raw)"),
                       ("container", "container"), ("local", "locale")):
            self.anon.append(k, lab)
        self.anon.set_active_id(s.get("anon", "tor"))
        self.sonly = Gtk.ComboBoxText()
        for k, lab in (("", "sempre"), ("on", "solo stealth ON"),
                       ("off", "solo stealth OFF")):
            self.sonly.append(k, lab)
        self.sonly.set_active_id(s.get("only", "") or "")
        self.sskip = Gtk.CheckButton.new_with_label("salta in stealth")
        self.sskip.set_active(bool(s.get("skip")))
        self.sflags = Gtk.Entry()
        self.sflags.set_placeholder_text("flag extra in stealth (es. -sT)")
        self.sflags.set_text(s.get("flags", ""))
        srow.pack_start(Gtk.Label(label="Stealth:"), False, False, 0)
        srow.pack_start(self.anon, False, False, 0)
        srow.pack_start(self.sonly, False, False, 0)
        srow.pack_start(self.sskip, False, False, 0)
        srow.pack_start(self.sflags, True, True, 0)
        box.pack_start(srow, False, False, 0)

        # --- catena dati (produces) ---
        pr = data.get("produces") or {}
        prow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.pvar = Gtk.Entry()
        self.pvar.set_placeholder_text("produce variabile (opz., es. vivi)")
        self.pvar.set_text(pr.get("var", ""))
        self.pextract = Gtk.ComboBoxText()
        for k, lab in (("lines", "righe"), ("nmap_up", "host vivi (nmap)"),
                       ("subdomains", "sottodomini"), ("urls", "URL"),
                       ("regex", "regex...")):
            self.pextract.append(k, lab)
        ex = pr.get("extract", "lines")
        self.pextract.set_active_id(
            "regex" if ex.startswith("regex:")
            else (ex if ex in ("lines", "nmap_up", "subdomains", "urls") else "lines"))
        self.pfrom = Gtk.Entry()
        self.pfrom.set_placeholder_text("da: stdout oppure {outdir}/file")
        self.pfrom.set_text(pr.get("from", "stdout"))
        self.pregex = Gtk.Entry()
        self.pregex.set_placeholder_text("pattern (se estratto=regex)")
        if ex.startswith("regex:"):
            self.pregex.set_text(ex[6:])
        prow.pack_start(Gtk.Label(label="Produce:"), False, False, 0)
        prow.pack_start(self.pvar, True, True, 0)
        prow.pack_start(self.pextract, False, False, 0)
        prow.pack_start(self.pfrom, True, True, 0)
        prow.pack_start(self.pregex, True, True, 0)
        box.pack_start(prow, False, False, 0)

    def to_dict(self):
        d = {"tool": self.tool.get_active_id() or "",
             "desc": self.desc.get_text().strip(),
             "args": self.args.get_text().strip()}
        m = _split_csv(self.modes.get_text())
        n = _split_csv(self.needs.get_text())
        if m:
            d["modes"] = m
        if n:
            d["needs"] = n
        st = {"anon": self.anon.get_active_id() or "tor"}
        only = self.sonly.get_active_id()
        if only:
            st["only"] = only
        if self.sskip.get_active():
            st["skip"] = True
        if self.sflags.get_text().strip():
            st["flags"] = self.sflags.get_text().strip()
        d["stealth"] = st
        var = self.pvar.get_text().strip()
        if var:
            ex = self.pextract.get_active_id() or "lines"
            if ex == "regex":
                ex = "regex:" + self.pregex.get_text().strip()
            d["produces"] = {"var": _slug(var),
                             "from": self.pfrom.get_text().strip() or "stdout",
                             "extract": ex}
        return d


# ------------------------------------------------------------------- schermata
class BuilderScreen:
    def __init__(self, win, body, on_done, edit_id=None):
        self.win = win
        self.body = body
        self.on_done = on_done
        self.tools = _tool_ids()
        self.field_rows = []
        self.mode_rows = []
        self.option_rows = []
        self.step_rows = []
        self._containers = {}
        self.prefill = (recipes.get(edit_id)
                        if edit_id and recipes.is_custom(edit_id) else None)
        self.edit_id = edit_id if self.prefill else None

    # ---- gestione righe ----
    def _remove(self, lst, row):
        if row in lst:
            lst.remove(row)
        row.widget.destroy()

    def _move(self, row, delta):
        rows = self.step_rows
        i = rows.index(row)
        j = i + delta
        if 0 <= j < len(rows):
            rows[i], rows[j] = rows[j], rows[i]
            cont = self._containers["steps"]
            for idx, r in enumerate(rows):
                cont.reorder_child(r.widget, idx)

    def _add(self, lst, cls, container, data=None):
        row = cls(self, data)
        lst.append(row)
        container.pack_start(row.widget, False, False, 0)
        container.show_all()
        return row

    # ---- costruzione UI ----
    def _clear(self):
        for c in self.body.get_children():
            self.body.remove(c)

    def _section(self, parent, text, adder=None):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lab = Gtk.Label(label=text); lab.set_xalign(0)
        lab.get_style_context().add_class("title")
        bar.pack_start(lab, True, True, 0)
        if adder:
            add = common.icon_button("Aggiungi", "list-add-symbolic")
            add.connect("clicked", lambda _b: adder())
            bar.pack_end(add, False, False, 0)
        parent.pack_start(bar, False, False, 0)

    def show(self):
        self._clear()
        p = self.prefill or {}

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        sw.add(form)
        self.body.pack_start(sw, True, True, 0)

        head = Gtk.Label(label=("Modifica wizard personalizzato" if self.edit_id
                                else "Nuovo wizard personalizzato"))
        head.set_xalign(0); head.get_style_context().add_class("title")
        form.pack_start(head, False, False, 0)

        # --- base ---
        grid = Gtk.Grid(); grid.set_row_spacing(6); grid.set_column_spacing(8)
        self.name = Gtk.Entry(); self.name.set_hexpand(True)
        self.name.set_placeholder_text("es. Ricognizione Active Directory")
        self.name.set_text(p.get("name", ""))
        self.desc = Gtk.Entry(); self.desc.set_hexpand(True)
        self.desc.set_placeholder_text("a cosa serve questa procedura")
        self.desc.set_text(p.get("description", ""))
        self.icon = Gtk.Entry()
        self.icon.set_placeholder_text("nome icona (opz., es. system-run-symbolic)")
        self.icon.set_text(p.get("icon", "system-run-symbolic"))
        self.profile = Gtk.ComboBoxText()
        for lab, val in _PROFILES:
            self.profile.append(val or "", lab)
        self.profile.set_active_id(p.get("profile") or "")
        grid.attach(Gtk.Label(label="Nome:", xalign=0), 0, 0, 1, 1)
        grid.attach(self.name, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label="Descrizione:", xalign=0), 0, 1, 1, 1)
        grid.attach(self.desc, 1, 1, 1, 1)
        grid.attach(Gtk.Label(label="Icona:", xalign=0), 0, 2, 1, 1)
        grid.attach(self.icon, 1, 2, 1, 1)
        grid.attach(Gtk.Label(label="Profilo:", xalign=0), 0, 3, 1, 1)
        grid.attach(self.profile, 1, 3, 1, 1)
        form.pack_start(grid, False, False, 0)

        self.stealthdef = Gtk.CheckButton.new_with_label(
            "Stealth attivo di default (l'utente puo' comunque spegnerlo)")
        self.stealthdef.set_active(bool(p.get("stealth_default")))
        form.pack_start(self.stealthdef, False, False, 0)

        # --- campi ---
        cont_f = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._containers["fields"] = cont_f
        self._section(form, "Campi richiesti all'utente",
                      adder=lambda: self._add(self.field_rows, _FieldRow, cont_f))
        form.pack_start(cont_f, False, False, 0)

        # --- modalita' ---
        cont_m = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._containers["modes"] = cont_m
        self._section(form, "Modalita' (intensita', scelta singola)",
                      adder=lambda: self._add(self.mode_rows, _ModeRow, cont_m))
        std = Gtk.Button(label="Aggiungi le 3 standard (Leggero/Approfondito/Stealth)")
        std.connect("clicked", lambda _b: self._add_standard_modes())
        form.pack_start(std, False, False, 0)
        form.pack_start(cont_m, False, False, 0)

        # --- opzioni ---
        cont_o = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._containers["options"] = cont_o
        self._section(form, "Opzioni (spunte)",
                      adder=lambda: self._add(self.option_rows, _OptionRow, cont_o))
        form.pack_start(cont_o, False, False, 0)

        # --- step ---
        cont_s = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._containers["steps"] = cont_s
        self._section(form, "Step (catena di tool, in ordine)",
                      adder=lambda: self._add(self.step_rows, _StepRow, cont_s))
        form.pack_start(cont_s, False, False, 0)

        # prefill dei contenuti dinamici
        for fd in p.get("fields", []):
            self._add(self.field_rows, _FieldRow, cont_f, fd)
        for md in p.get("modes", []):
            self._add(self.mode_rows, _ModeRow, cont_m, md)
        for od in p.get("options", []):
            self._add(self.option_rows, _OptionRow, cont_o, od)
        for sd in p.get("steps", []):
            self._add(self.step_rows, _StepRow, cont_s, sd)
        if not self.prefill:
            # un campo iniziale d'esempio per partire subito
            self._add(self.field_rows, _FieldRow, cont_f,
                      {"key": "target", "label": "Bersaglio", "required": True})

        # --- barra pulsanti (fuori dallo scroll) ---
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        cancel = common.icon_button("Annulla", "go-previous-symbolic")
        cancel.connect("clicked", lambda _b: self.on_done())
        save = common.icon_button("Salva wizard", "document-save-symbolic",
                                  primary=True)
        save.connect("clicked", lambda _b: self._save())
        bar.pack_start(cancel, False, False, 0)
        bar.pack_end(save, False, False, 0)
        self.body.pack_start(bar, False, False, 0)

        self.body.show_all()

    def _add_standard_modes(self):
        cont = self._containers["modes"]
        presets = [
            {"label": "Leggero", "desc": "Veloce e poco invasivo.",
             "default": True, "vars": {}},
            {"label": "Approfondito", "desc": "Piu' completo e aggressivo.",
             "vars": {}},
            {"label": "Stealth", "desc": "Lento e discreto.", "vars": {}},
        ]
        for pr in presets:
            self._add(self.mode_rows, _ModeRow, cont, pr)

    # ---- salvataggio ----
    def _error(self, msg):
        common.info_dialog("Wizard non valido", msg, level="error", parent=self.win)

    def _save(self):
        name = self.name.get_text().strip()
        if not name:
            self._error("Dai un nome al wizard.")
            return
        fields = [r.to_dict() for r in self.field_rows]
        fields = [f for f in fields if f["key"]]
        steps = [r.to_dict() for r in self.step_rows]
        steps = [s for s in steps if s["tool"]]
        if not steps:
            self._error("Aggiungi almeno uno step con un tool.")
            return
        modes = [r.to_dict() for r in self.mode_rows]
        options = [r.to_dict() for r in self.option_rows]

        # una sola modalita' predefinita
        if modes and not any(m["default"] for m in modes):
            modes[0]["default"] = True

        wiz = {"name": name,
               "description": self.desc.get_text().strip(),
               "icon": self.icon.get_text().strip() or "system-run-symbolic",
               "profile": (self.profile.get_active_id() or None),
               "stealth_default": self.stealthdef.get_active(),
               "fields": fields,
               "modes": modes,
               "options": options,
               "steps": steps}

        wid = self.edit_id or self._unique_id(_slug(name))
        if recipes.save_custom(wid, wiz):
            common.info_dialog(
                "Wizard salvato",
                f"\"{name}\" e' ora nell'elenco delle procedure guidate.",
                parent=self.win)
            self.on_done()
        else:
            self._error("Impossibile scrivere il file del wizard "
                        "(~/.config/nxs/wizards/).")

    def _unique_id(self, base):
        existing = set(recipes.all_wizards().keys())
        if base not in existing:
            return base
        i = 2
        while f"{base}-{i}" in existing:
            i += 1
        return f"{base}-{i}"
