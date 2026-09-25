# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""Permessi per sito (come Firefox): microfono/fotocamera, notifiche, posizione.

- Richiesta di un sito: dialogo Consenti / Blocca con la spunta "Ricorda la
  scelta per questo sito"; le scelte ricordate stanno in
  ~/.nxs-browser/permissions.json (host -> tipo -> "allow"|"deny").
- Dal lucchetto (security.info_sito) si vedono e si cambiano: Chiedi /
  Consenti / Blocca.
- Modalita' anonima: tutto negato sempre, senza chiedere e senza ricordare.
- Le altre richieste (es. accesso ai media criptati, puntatore) si negano.
"""
import json
from pathlib import Path
from urllib.parse import urlparse

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, WebKit2  # noqa: E402

try:
    from nxs_i18n import t as _t
except Exception:                # noqa: BLE001
    def _t(key, **kw):
        return key

FILE = Path.home() / ".nxs-browser" / "permissions.json"
TIPI = ("media", "notifications", "geolocation")


def _carica():
    try:
        d = json.loads(FILE.read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _salva(d):
    try:
        FILE.parent.mkdir(exist_ok=True)
        FILE.write_text(json.dumps(d, indent=1, sort_keys=True))
    except OSError:
        pass


def host_di(uri):
    return (urlparse(uri or "").hostname or "").lower()


def scelta(host, tipo):
    return _carica().get(host, {}).get(tipo, "")


def imposta(host, tipo, valore):
    """valore: "allow" | "deny" | "" (= chiedi di nuovo)."""
    d = _carica()
    voce = d.setdefault(host, {})
    if valore:
        voce[tipo] = valore
    else:
        voce.pop(tipo, None)
    if not voce:
        d.pop(host, None)
    _salva(d)


def permessi_sito(host):
    return dict(_carica().get(host, {}))


def cancella_tutti():
    _salva({})


def _tipo(req):
    try:
        if isinstance(req, WebKit2.UserMediaPermissionRequest):
            return "media"
        if isinstance(req, WebKit2.NotificationPermissionRequest):
            return "notifications"
        if isinstance(req, WebKit2.GeolocationPermissionRequest):
            return "geolocation"
    except Exception:            # noqa: BLE001
        pass
    return ""


def gestisci(browser, view, req, anonima):
    """Handler di "permission-request": decide, chiede o applica il ricordato."""
    tipo = _tipo(req)
    if anonima or not tipo:
        req.deny()
        return True
    host = host_di(view.get_uri())
    ricordata = scelta(host, tipo)
    if ricordata:
        req.allow() if ricordata == "allow" else req.deny()
        return True
    d = Gtk.MessageDialog(transient_for=browser, modal=True,
                          message_type=Gtk.MessageType.QUESTION,
                          text=_t("br.perm.q_" + tipo))
    d.format_secondary_text((_t("br.perm.site") % host) if host else "")
    d.add_buttons(_t("br.perm.deny"), Gtk.ResponseType.NO,
                  _t("br.perm.allow"), Gtk.ResponseType.YES)
    d.set_default_response(Gtk.ResponseType.NO)   # Invio = Blocca: niente consensi per sbaglio
    ricorda = Gtk.CheckButton(label=_t("br.perm.remember"))
    ricorda.set_active(True)
    ricorda.set_margin_start(12)
    d.get_content_area().pack_start(ricorda, False, False, 6)
    ricorda.show()
    risposta = d.run()
    tieni = ricorda.get_active()
    d.destroy()
    ok = risposta == Gtk.ResponseType.YES
    if tieni and host:
        imposta(host, tipo, "allow" if ok else "deny")
    req.allow() if ok else req.deny()
    return True


def riquadro(host):
    """Righe per il pannello del lucchetto: un selettore per tipo."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    tit = Gtk.Label(label=_t("br.perm.title"))
    tit.set_xalign(0)
    tit.get_style_context().add_class("nxs-dl-name")
    box.pack_start(tit, False, False, 0)
    attuali = permessi_sito(host)
    for tipo in TIPI:
        riga = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lab = Gtk.Label(label=_t("br.perm.t_" + tipo))
        lab.set_xalign(0)
        riga.pack_start(lab, True, True, 0)
        combo = Gtk.ComboBoxText()
        combo.append("", _t("br.perm.ask"))
        combo.append("allow", _t("br.perm.allow"))
        combo.append("deny", _t("br.perm.deny"))
        combo.set_active_id(attuali.get(tipo, ""))
        combo.connect("changed", lambda c, t=tipo: imposta(host, t, c.get_active_id() or ""))
        riga.pack_end(combo, False, False, 0)
        box.pack_start(riga, False, False, 0)
    return box
