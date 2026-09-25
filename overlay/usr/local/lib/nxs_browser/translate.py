# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""Traduzione delle pagine, come in Chrome.

Pulsante nella barra (dopo Stealth): si illumina quando la pagina e' in una
lingua diversa da quella scelta; al clic un pannello mostra la lingua della
pagina, la lingua di arrivo, Traduci / Mostra originale e il servizio usato.

Come funziona: uno script raccoglie i testi della pagina (non codice, campi,
elementi marcati translate="no"/notranslate), Python li traduce a blocchi e lo
script li rimette al loro posto, conservando l'impaginazione; "Mostra
originale" ripristina i testi salvati. Il lavoro di rete gira in un thread.

Servizi: Google (predefinito, come Chrome, nessuna chiave) oppure
LibreTranslate (software libero, anche su un server proprio: URL e chiave
nelle Impostazioni). Il testo della pagina viene inviato al servizio: il
pannello lo dice. In modalita' anonima la richiesta passa via Tor (curl
--socks5-hostname), come il resto della navigazione.
"""
import json
import subprocess
import threading

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, GLib  # noqa: E402

from nxs_browser.config import config

try:
    from nxs_i18n import t as _t, current_lang
except Exception:                # noqa: BLE001
    def _t(key, **kw):
        return key

    def current_lang():
        return "it"

# lingue di arrivo: nome nella lingua stessa (non serve tradurlo)
LINGUE = [
    ("it", "Italiano"), ("en", "English"), ("fr", "Français"), ("es", "Español"),
    ("de", "Deutsch"), ("pt", "Português"), ("nl", "Nederlands"), ("pl", "Polski"),
    ("ro", "Română"), ("sv", "Svenska"), ("el", "Ελληνικά"), ("ru", "Русский"),
    ("uk", "Українська"), ("tr", "Türkçe"), ("ar", "العربية"),
]
# Cinese, giapponese, coreano e hindi NON ci sono di proposito: la distro non ha
# font per quelle scritture (i CJK da soli pesano oltre 100 MB) e sia il nome
# nell'elenco sia la pagina tradotta sarebbero quadratini illeggibili.
NOMI = dict(LINGUE)
BLOCCO = 3500          # caratteri per richiesta

# --- script nella pagina ------------------------------------------------------------
JS_RACCOGLI = r"""
(function () {
  var S = window.__nxsTr;
  if (!S) {
    S = window.__nxsTr = {nodi: [], orig: []};
    var salta = {SCRIPT:1, STYLE:1, NOSCRIPT:1, CODE:1, PRE:1, TEXTAREA:1,
                 INPUT:1, SELECT:1, OPTION:1, SVG:1, MATH:1, KBD:1, SAMP:1};
    var w = document.createTreeWalker(document.body || document.documentElement,
      NodeFilter.SHOW_TEXT, {acceptNode: function (n) {
        if (!/[^\s\d.,:;!?()\[\]{}'"«»%+\-*/=<>|_@#&€$£]/.test(n.nodeValue))
          return NodeFilter.FILTER_REJECT;
        for (var e = n.parentElement; e; e = e.parentElement) {
          if (salta[e.tagName] || e.isContentEditable ||
              e.getAttribute('translate') === 'no' ||
              (e.classList && e.classList.contains('notranslate')))
            return NodeFilter.FILTER_REJECT;
        }
        return NodeFilter.FILTER_ACCEPT; }});
    var n;
    while ((n = w.nextNode())) { S.nodi.push(n); S.orig.push(n.nodeValue); }
  }
  return JSON.stringify(S.orig.map(function (t) {
    return t.replace(/\s+/g, ' ').trim(); }));
})();
"""

JS_APPLICA = r"""
(function (ini, tr) {
  var S = window.__nxsTr; if (!S) return 0;
  for (var i = 0; i < tr.length; i++) {
    var n = S.nodi[ini + i], o = S.orig[ini + i];
    if (!n || tr[i] == null) continue;
    var a = o.match(/^\s*/)[0], z = o.match(/\s*$/)[0];
    n.nodeValue = a + tr[i] + z;
  }
  return 1;
})(%d, %s);
"""

JS_ORIGINALE = r"""
(function () {
  var S = window.__nxsTr; if (!S) return 0;
  for (var i = 0; i < S.nodi.length; i++) S.nodi[i].nodeValue = S.orig[i];
  return 1;
})();
"""

JS_LINGUA = "(document.documentElement.lang || '').toLowerCase()"


# --- servizi ---------------------------------------------------------------------------
def _curl(args, dati, via_tor):
    cmd = ["curl", "-sS", "--max-time", "40"]
    if via_tor:
        cmd += ["--socks5-hostname", "127.0.0.1:9050"]
    r = subprocess.run(cmd + args, input=dati.encode("utf-8"),
                       capture_output=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace").strip() or "curl")
    return r.stdout.decode("utf-8", "replace")


def _google(testi, dest, via_tor):
    """Blocco di testi separati da a-capo -> (traduzioni, lingua rilevata)."""
    q = "\n".join(testi)
    out = _curl(["--data-urlencode", "q@-",
                 "https://translate.googleapis.com/translate_a/single"
                 "?client=gtx&sl=auto&dt=t&tl=" + dest], q, via_tor)
    d = json.loads(out)
    pezzi = "".join(seg[0] or "" for seg in (d[0] or []))
    return pezzi.split("\n"), (d[2] if len(d) > 2 else "") or ""


def _libre(testi, dest, via_tor):
    url = (config.get("translate_url", "") or "https://libretranslate.com").rstrip("/")
    corpo = {"q": testi, "source": "auto", "target": dest.split("-")[0],
             "format": "text"}
    if config.get("translate_key", ""):
        corpo["api_key"] = config.get("translate_key")
    out = _curl(["-H", "Content-Type: application/json", "--data-binary", "@-",
                 url + "/translate"], json.dumps(corpo), via_tor)
    d = json.loads(out)
    if "error" in d:
        raise RuntimeError(d["error"])
    tr = d.get("translatedText", [])
    rilev = d.get("detectedLanguage", [{}])
    lingua = (rilev[0] if isinstance(rilev, list) and rilev else rilev or {}).get("language", "")
    return (tr if isinstance(tr, list) else [tr]), lingua


def traduci_blocco(testi, dest, via_tor):
    servizio = config.get("translate_service", "google")
    f = _libre if servizio == "libre" else _google
    tr, lingua = f(testi, dest, via_tor)
    if len(tr) != len(testi):
        # il servizio ha unito/spezzato righe: si ripiega testo per testo
        tr = [f([t], dest, via_tor)[0][0] if t else t for t in testi]
    return tr, lingua


def nome_servizio():
    if config.get("translate_service", "google") == "libre":
        return "LibreTranslate (%s)" % ((config.get("translate_url", "") or
                                          "libretranslate.com").split("//")[-1])
    return "Google Translate"


# --- pulsante e pannello --------------------------------------------------------------------
class Traduttore:
    def __init__(self, browser):
        self.browser = browser
        self.stato = {}                 # view -> "originale" | "tradotta" | "in corso"
        self.pulsante = Gtk.Button()
        self.pulsante.set_relief(Gtk.ReliefStyle.NONE)
        self.pulsante.set_tooltip_text(_t("br.tr.tip"))
        self.pulsante.get_style_context().add_class("nxs-nav-btn")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        box.pack_start(Gtk.Image.new_from_icon_name(
            "preferences-desktop-locale-symbolic", Gtk.IconSize.BUTTON), False, False, 0)
        self.etichetta = Gtk.Label(label=_t("br.tr.short"))
        box.pack_start(self.etichetta, False, False, 0)
        self.pulsante.add(box)
        self.pulsante.connect("clicked", lambda _w: self._pannello())
        self._pop = None

    def destinazione(self):
        d = config.get("translate_to", "") or current_lang() or "it"
        return d if d in NOMI else "it"

    # la pagina e' in un'altra lingua? il pulsante si illumina
    def pagina_caricata(self, view):
        self.stato.pop(view, None)
        if view is not self.browser.current_view():
            return
        self.aggiorna(view)

    def aggiorna(self, view):
        ctx = self.pulsante.get_style_context()
        ctx.remove_class("nxs-tr-offer")
        ctx.remove_class("nxs-tr-on")
        if view is None:
            return
        if self.stato.get(view) == "tradotta":
            ctx.add_class("nxs-tr-on")
            return

        def fatto(v, res):
            try:
                lingua = v.run_javascript_finish(res).get_js_value().to_string()
            except Exception:        # noqa: BLE001
                return
            lingua = (lingua or "").split("-")[0]
            if lingua and lingua != self.destinazione().split("-")[0]:
                ctx.add_class("nxs-tr-offer")
        try:
            view.run_javascript(JS_LINGUA, None, fatto)
        except Exception:            # noqa: BLE001
            pass

    def _pannello(self):
        v = self.browser.current_view()
        if v is None:
            return
        pop = Gtk.Popover.new(self.pulsante)
        pop.get_style_context().add_class("nxs-dl-pop")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(12)
        tit = Gtk.Label(label=_t("br.tr.title"))
        tit.set_xalign(0)
        tit.get_style_context().add_class("nxs-dl-title")
        box.pack_start(tit, False, False, 0)
        riga = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        riga.pack_start(Gtk.Label(label=_t("br.tr.to")), False, False, 0)
        combo = Gtk.ComboBoxText()
        for k, nome in LINGUE:
            combo.append(k, nome)
        combo.set_active_id(self.destinazione())
        riga.pack_start(combo, True, True, 0)
        box.pack_start(riga, False, False, 0)
        self.info = Gtk.Label()
        self.info.set_xalign(0)
        self.info.set_line_wrap(True)
        self.info.set_max_width_chars(44)
        self.info.get_style_context().add_class("nxs-dl-info")
        box.pack_start(self.info, False, False, 0)
        tasti = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        b_tr = Gtk.Button(label=_t("br.tr.do"))
        b_or = Gtk.Button(label=_t("br.tr.original"))
        tasti.pack_start(b_tr, False, False, 0)
        tasti.pack_start(b_or, False, False, 0)
        box.pack_start(tasti, False, False, 0)
        nota = Gtk.Label(label=_t("br.tr.privacy") % nome_servizio()
                         + ("\n" + _t("br.tr.via_tor") if self._via_tor(v) else ""))
        nota.set_xalign(0)
        nota.set_line_wrap(True)
        nota.set_max_width_chars(44)
        nota.get_style_context().add_class("nxs-dl-info")
        box.pack_start(nota, False, False, 0)

        def traduci(_w):
            config.set("translate_to", combo.get_active_id() or "it")
            self.traduci(v)
        b_tr.connect("clicked", traduci)
        b_or.connect("clicked", lambda _w: self.originale(v))
        b_or.set_sensitive(self.stato.get(v) == "tradotta")
        self._b_or = b_or
        if self.stato.get(v) == "tradotta":
            self.info.set_text(_t("br.tr.done") % NOMI.get(self.destinazione(), ""))
        box.show_all()
        pop.add(box)
        pop.popup()
        self._pop = pop

    def _via_tor(self, view):
        return bool(self.browser._view_mode.get(view)) and bool(self.browser._tor_ok)

    def _messaggio(self, testo):
        try:
            self.info.set_text(testo)
        except Exception:            # noqa: BLE001
            pass

    # --- traduzione -----------------------------------------------------------------------
    def traduci(self, view):
        if self.stato.get(view) == "in corso":
            return
        if self.stato.get(view) == "tradotta":
            self.originale(view, silenzioso=True)
        self.stato[view] = "in corso"
        self._messaggio(_t("br.tr.working") % 0)

        def raccolti(v, res):
            try:
                testi = json.loads(v.run_javascript_finish(res).get_js_value().to_string())
            except Exception as e:   # noqa: BLE001
                self.stato[view] = "originale"
                self._messaggio(str(e))
                return
            threading.Thread(target=self._lavora, args=(view, testi),
                             daemon=True).start()
        view.run_javascript(JS_RACCOGLI, None, raccolti)

    def _lavora(self, view, testi):
        dest = self.destinazione()
        via_tor = self._via_tor(view)
        blocchi, cur, lung, ini = [], [], 0, 0
        for i, t in enumerate(testi):
            if cur and lung + len(t) > BLOCCO:
                blocchi.append((ini, cur))
                ini, cur, lung = i, [], 0
            cur.append(t)
            lung += len(t) + 1
        if cur:
            blocchi.append((ini, cur))
        lingua = ""
        try:
            for k, (ini, pezzo) in enumerate(blocchi):
                tr, l = traduci_blocco(pezzo, dest, via_tor)
                lingua = lingua or l
                js = JS_APPLICA % (ini, json.dumps(tr, ensure_ascii=False))
                GLib.idle_add(self._applica, view, js)
                pct = int(100 * (k + 1) / max(1, len(blocchi)))
                GLib.idle_add(self._messaggio, _t("br.tr.working") % pct)
        except Exception as e:       # noqa: BLE001
            GLib.idle_add(self._errore, view, str(e))
            return
        GLib.idle_add(self._finito, view, lingua, dest)

    def _applica(self, view, js):
        try:
            view.run_javascript(js, None, None)
        except Exception:            # noqa: BLE001
            pass
        return False

    def _finito(self, view, lingua, dest):
        self.stato[view] = "tradotta"
        da = NOMI.get(lingua, lingua or "?")
        self._messaggio(_t("br.tr.done_from") % (da, NOMI.get(dest, dest)))
        try:
            self._b_or.set_sensitive(True)
        except Exception:            # noqa: BLE001
            pass
        self.aggiorna(view)
        return False

    def _errore(self, view, msg):
        self.stato[view] = "originale"
        self._messaggio(_t("br.tr.failed") % msg)
        return False

    def originale(self, view, silenzioso=False):
        try:
            view.run_javascript(JS_ORIGINALE, None, None)
        except Exception:            # noqa: BLE001
            pass
        self.stato[view] = "originale"
        if not silenzioso:
            self._messaggio(_t("br.tr.restored"))
            try:
                self._b_or.set_sensitive(False)
            except Exception:        # noqa: BLE001
                pass
            self.aggiorna(view)
