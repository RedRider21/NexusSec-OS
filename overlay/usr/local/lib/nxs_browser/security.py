# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""Sicurezza di NexusSec Browser: lucchetto, solo-HTTPS, antitracciamento.

- Lucchetto della barra indirizzi: riflette lo stato della connessione
  (cifrata / non cifrata / certificato con problemi) e al clic apre le
  informazioni sul sito: host, stato, certificato (intestatario, emittente,
  validita') ed eventuali errori.
- Solo HTTPS (predefinito acceso, come in Firefox): i link http:// si provano
  prima in https://; se il sito non lo supporta compare una pagina che lo
  spiega e permette di continuare in HTTP. ESCLUSI di proposito indirizzi IP,
  reti locali, nomi senza dominio, .local e .onion: in una distro da pentest si
  lavora spesso in HTTP su macchine di laboratorio.
- Antitracciamento: blocca le richieste di TERZE PARTI verso domini di
  tracciamento noti (elenco curato da NexusSec in trackers.txt, nessuna lista
  di terzi con licenze non compatibili), tramite i content filter di WebKit.
- Popup: le finestre aperte da script senza un clic dell'utente sono bloccate.
"""
import hashlib
import html
import ipaddress
import os
from pathlib import Path
from urllib.parse import urlparse

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, Gio, GLib, WebKit2  # noqa: E402

from nxs_browser.config import config

try:
    from nxs_i18n import t as _t
except Exception:                # noqa: BLE001
    def _t(key, **kw):
        return key

TRACKERS = Path(__file__).with_name("trackers.txt")
FILTRI_DIR = Path.home() / ".nxs-browser" / "filters"


# ----------------------------------------------------------------- solo HTTPS
def _esente(host: str) -> bool:
    host = (host or "").strip("[]").lower()
    if not host or "." not in host:
        return True                                  # localhost, nomi di rete
    if host.endswith((".local", ".onion", ".lan", ".home", ".internal", ".test")):
        return True
    try:
        ipaddress.ip_address(host)
        return True                                  # indirizzi IP: laboratorio
    except ValueError:
        return False


class SoloHttps:
    def __init__(self, browser):
        self.browser = browser
        self.eccezioni = set()       # host per cui l'utente ha scelto HTTP
        self.promossi = {}           # url https tentato -> url http originale

    def attivo(self):
        return bool(config.get("https_only", True))

    def aggancia(self, view):
        view.connect("decide-policy", self._decidi)
        view.connect("load-failed", self._fallito)

    def _decidi(self, view, decisione, tipo):
        if tipo != WebKit2.PolicyDecisionType.NAVIGATION_ACTION or not self.attivo():
            return False
        try:
            uri = decisione.get_navigation_action().get_request().get_uri()
        except Exception:            # noqa: BLE001
            return False
        u = urlparse(uri or "")
        if u.scheme != "http" or _esente(u.hostname) or u.hostname in self.eccezioni:
            return False
        sicuro = "https" + uri[4:]
        self.promossi[sicuro] = uri
        decisione.ignore()
        GLib.idle_add(lambda: (view.load_uri(sicuro), False)[1])
        return True

    def _fallito(self, view, _evento, uri, errore):
        originale = self.promossi.pop(uri or "", None)
        if not originale:
            return False
        try:
            if errore.matches(WebKit2.NetworkError.quark(),
                              WebKit2.NetworkError.CANCELLED):
                return False
        except Exception:            # noqa: BLE001
            pass
        host = urlparse(originale).hostname or ""
        # la pagina spiega e offre il link: l'eccezione vale per questo host
        # e per questa sessione soltanto
        self.eccezioni.add(host)
        pagina = """<!doctype html><meta charset="utf-8"><title>%(t)s</title>
<style>body{font-family:sans-serif;background:#1c1b22;color:#fbfbfe;
display:flex;justify-content:center;padding-top:12vh}
.b{max-width:620px}h1{font-size:22px}p{color:#cfcfd8;line-height:1.5}
a.c{display:inline-block;margin-top:14px;padding:9px 16px;border-radius:8px;
background:#3a3944;color:#fbfbfe;text-decoration:none}
code{color:#ffb000}</style><div class="b"><h1>%(t)s</h1>
<p>%(d)s</p><p><code>%(h)s</code></p>
<a class="c" href="%(u)s">%(c)s</a></div>""" % {
            "t": html.escape(_t("br.https.title")),
            "d": html.escape(_t("br.https.body")),
            "h": html.escape(host), "u": html.escape(originale, quote=True),
            "c": html.escape(_t("br.https.continue"))}
        view.load_alternate_html(pagina, uri, None)
        return True


# ------------------------------------------------------------- antitracciamento
def _domini():
    try:
        righe = TRACKERS.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [r.strip().lower() for r in righe if r.strip() and not r.startswith("#")]


def _regole(domini):
    """Regole content-filter di WebKit (formato Safari): blocca le richieste di
    terze parti verso il dominio e i suoi sottodomini."""
    import json
    import re
    return json.dumps([{
        "trigger": {"url-filter": "^[a-z]+://([^/]*\\.)?" + re.escape(d) + "[:/]",
                    "load-type": ["third-party"]},
        "action": {"type": "block"}} for d in domini])


class Antitracciamento:
    """Compila una volta il filtro (cache in ~/.nxs-browser/filters, rifatta
    solo se l'elenco cambia) e lo applica a ogni scheda."""

    def __init__(self):
        self.filtro = None
        self.in_attesa = []
        self.domini = _domini()
        firma = hashlib.sha1("\n".join(self.domini).encode()).hexdigest()[:12]
        self.ident = "nxs-trackers-" + firma
        if not self.domini:
            return
        try:
            FILTRI_DIR.mkdir(parents=True, exist_ok=True)
            self.store = WebKit2.UserContentFilterStore.new(str(FILTRI_DIR))
            self.store.load(self.ident, None, self._caricato)
        except Exception:            # noqa: BLE001
            self.store = None

    def attivo(self):
        return bool(config.get("tracking_protection", True))

    def _caricato(self, store, res):
        try:
            self._pronto(store.load_finish(res))
        except Exception:            # noqa: BLE001 - non in cache: compila
            dati = GLib.Bytes.new(_regole(self.domini).encode())
            store.save(self.ident, dati, None, self._salvato)

    def _salvato(self, store, res):
        try:
            self._pronto(store.save_finish(res))
        except Exception:            # noqa: BLE001
            self.filtro = None

    def _pronto(self, filtro):
        self.filtro = filtro
        for v in self.in_attesa:
            self.applica(v)
        self.in_attesa = []

    def applica(self, view):
        if not self.attivo() or not self.domini:
            return
        if self.filtro is None:
            self.in_attesa.append(view)
            return
        try:
            view.get_user_content_manager().add_filter(self.filtro)
        except Exception:            # noqa: BLE001
            pass

    def togli_da(self, view):
        try:
            view.get_user_content_manager().remove_all_filters()
        except Exception:            # noqa: BLE001
            pass


def blocca_popup(view):
    try:
        view.get_settings().set_property(
            "javascript-can-open-windows-automatically", False)
    except Exception:                # noqa: BLE001
        pass


# ----------------------------------------------------------------- lucchetto
def stato(view):
    """("https"|"http"|"errore"|"altro", certificato, flag errori)."""
    uri = view.get_uri() or ""
    if uri.startswith("http://"):
        return "http", None, 0
    if not uri.startswith("https://"):
        return "altro", None, 0
    try:
        ok, cert, errori = view.get_tls_info()
    except Exception:                # noqa: BLE001
        ok, cert, errori = False, None, 0
    if not ok:
        return "altro", None, 0
    return ("errore" if int(errori) else "https"), cert, errori


def icona(view):
    s = stato(view)[0]
    return {"https": "security-high-symbolic", "http": "security-low-symbolic",
            "errore": "dialog-warning-symbolic"}.get(s, "text-html-symbolic")


def _data(d):
    try:
        return d.to_local().format("%d/%m/%Y") if d is not None else "—"
    except Exception:                # noqa: BLE001
        return "—"


def _errori_testo(flag):
    nomi = []
    for f, k in ((Gio.TlsCertificateFlags.UNKNOWN_CA, "br.site.e_ca"),
                 (Gio.TlsCertificateFlags.BAD_IDENTITY, "br.site.e_identity"),
                 (Gio.TlsCertificateFlags.NOT_ACTIVATED, "br.site.e_notyet"),
                 (Gio.TlsCertificateFlags.EXPIRED, "br.site.e_expired"),
                 (Gio.TlsCertificateFlags.REVOKED, "br.site.e_revoked"),
                 (Gio.TlsCertificateFlags.INSECURE, "br.site.e_insecure")):
        if int(flag) & int(f):
            nomi.append(_t(k))
    return nomi


def info_sito(browser, relativo):
    """Popover sotto il lucchetto con lo stato del sito corrente."""
    v = browser.current_view()
    if v is None:
        return
    s, cert, errori = stato(v)
    host = urlparse(v.get_uri() or "").hostname or (v.get_uri() or "")
    pop = Gtk.Popover.new(relativo)
    pop.get_style_context().add_class("nxs-dl-pop")
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    box.set_border_width(12)

    def riga(testo, classe=None):
        l = Gtk.Label(label=testo)
        l.set_xalign(0)
        l.set_line_wrap(True)
        l.set_max_width_chars(46)
        l.set_selectable(True)
        if classe:
            l.get_style_context().add_class(classe)
        box.pack_start(l, False, False, 0)
        return l

    riga(host, "nxs-dl-title")
    titoli = {"https": _t("br.site.secure"), "http": _t("br.site.insecure"),
              "errore": _t("br.site.cert_problem"), "altro": _t("br.site.local")}
    testo = {"https": _t("br.site.secure_d"), "http": _t("br.site.insecure_d"),
             "errore": _t("br.site.cert_problem_d"), "altro": ""}
    img = Gtk.Image.new_from_icon_name(icona(v), Gtk.IconSize.LARGE_TOOLBAR)
    testa = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    testa.pack_start(img, False, False, 0)
    l = Gtk.Label(label=titoli[s]); l.set_xalign(0)
    l.get_style_context().add_class("nxs-dl-name")
    testa.pack_start(l, False, False, 0)
    box.pack_start(testa, False, False, 0)
    if testo[s]:
        riga(testo[s], "nxs-dl-info")
    if cert is not None:
        def prop(nome):
            try:
                return cert.get_property(nome)
            except Exception:        # noqa: BLE001
                return None
        riga("%s: %s" % (_t("br.site.subject"), prop("subject-name") or "—"))
        riga("%s: %s" % (_t("br.site.issuer"), prop("issuer-name") or "—"))
        riga(_t("br.site.valid") % (_data(prop("not-valid-before")),
                                    _data(prop("not-valid-after"))))
    for e in _errori_testo(errori):
        riga("• " + e, "nxs-find-none-text")
    if config.get("tracking_protection", True):
        riga(_t("br.site.tracking_on"), "nxs-dl-info")
    box.show_all()
    pop.add(box)
    pop.popup()
