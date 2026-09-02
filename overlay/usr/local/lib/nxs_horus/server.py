"""HORUS - backend locale.

Un piccolo http.server legato SOLO a 127.0.0.1 (loopback): serve la SPA
vendorizzata e fa da proxy verso i feed pubblici mondiali. Sta in locale per due
motivi concreti:

  1. CORS: il browser non puo' chiamare da se' USGS/OpenSky/... da una pagina
     servita in locale; il proxy aggira il problema una volta sola.
  2. Anonimato: se Tor e' su (127.0.0.1:9050, come per nxs-browser) le richieste
     ai feed escono dal circuito Tor. Best-effort: serve PySocks; senza, le
     richieste restano dirette ma SEMPRE in HTTPS.

REGOLA: il socket ascolta su loopback. Quel traffico non tocca la rete, quindi
NON serve (ne' avrebbe senso) l'HTTPS sul lato browser<->backend. I feed esterni
invece sono tutti https://.

Il pannello recon esegue SOLO strumenti in whitelist, con l'obiettivo validato
per tipo e passato come LISTA di argomenti (mai una stringa di shell): niente
shell=True, niente interpolazione. Timeout e output troncato.
"""
from __future__ import annotations

import json
import os
import re
import base64
import struct
import tempfile
import hashlib
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from urllib.parse import parse_qs, quote, urlparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from nxs_horus import recorder   # storico in background (SQLite): NON importa server

WEB = Path(__file__).resolve().parent / "web"
# PySocks vendorizzato (BSD): serve a instradare i feed via Tor senza dover
# installare un pacchetto. Lo metto su sys.path cosi' "import socks" lo trova.
_PYSOCKS = str(Path(__file__).resolve().parent / "vendor" / "pysocks")
if _PYSOCKS not in sys.path:
    sys.path.insert(0, _PYSOCKS)
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
TOR_HOST, TOR_PORT = "127.0.0.1", 9050
TIMEOUT = 20            # timeout richieste feed (s)
RECON_TIMEOUT = 150     # timeout esecuzione tool recon (s)
OUT_MAX = 40000         # troncamento output recon (caratteri)

# ---------------------------------------------------------------------------
# Feed globali. Nessun cap regionale: sono tutti mondiali. `kind` dice al
# gestore come trattare la risposta (passthrough JSON o normalizzazione EONET).
# Tutte le sorgenti sono KEYLESS (EONET rimpiazza FIRMS che voleva una MAP_KEY).
# ---------------------------------------------------------------------------
FEEDS = {
    "quakes": {
        "url": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson",
        "kind": "json",
    },
    "flights": {
        "url": "https://opensky-network.org/api/states/all",
        "kind": "json",
    },
    "cables": {
        "url": "https://www.submarinecablemap.com/api/v3/cable/cable-geo.json",
        "kind": "json",
    },
    "iss": {
        "url": "https://api.wheretheiss.at/v1/satellites/25544",
        "kind": "json",
    },
    "volcano": {
        # Smithsonian GVP: molto piu' completo di EONET per i vulcani ATTIVI
        # (EONET curato e lacunoso: mancava l'Etna, in eruzione). Filtriamo per
        # anno d'ultima eruzione recente (vedi _feed): cosi' escono Etna,
        # Stromboli, Kilauea... {year} sostituito a runtime.
        "url": ("https://webservices.volcano.si.edu/geoserver/GVP-VOTW/ows"
                "?service=WFS&version=2.0.0&request=GetFeature"
                "&typeNames=GVP-VOTW:Smithsonian_VOTW_Holocene_Volcanoes"
                "&outputFormat=application/json&CQL_FILTER=Last_Eruption_Year%3E%3D{year}"),
        "kind": "gvp",
    },
    "fires": {
        "url": "https://eonet.gsfc.nasa.gov/api/v3/events?category=wildfires&status=open&limit=500",
        "kind": "eonet",
    },
    "cameras": {
        # Telecamere del traffico da enti PUBBLICI ufficiali (TfL Londra,
        # Caltrans California, Ontario 511): tutte KEYLESS, con immagine in
        # diretta. Stesso approccio di OSIRIS (reti di sorveglianza reali, non
        # webcam turistiche). Aggregazione e cache in _cameras_official().
        "url": "",
        "kind": "cameras",
    },
    "ships": {
        # Digitraffic (Fintraffic): AIS pubblico KEYLESS. Copre Baltico/Nord
        # Europa (l'AIS globale senza chiave non esiste). GeoJSON di posizioni;
        # il nome nave arriva dall'endpoint /vessels (unito in _ships_geojson).
        # Digitraffic chiede di identificarsi con l'header Digitraffic-User.
        # UN SOLO layer navi: se c'e' la chiave aisstream (~/.config/nxs/aisstream.key)
        # si usa l'AIS GLOBALE (aisstream, WebSocket); altrimenti si ripiega su
        # Digitraffic keyless (solo Baltico/Nord EU). Gestito in _feed.
        "url": "https://meri.digitraffic.fi/api/ais/v1/locations",
        "kind": "ships",
        "headers": {"Digitraffic-User": "NexusSec/HORUS", "Accept-Encoding": "gzip"},
    },
}

_DIGI_HDR = {"Digitraffic-User": "NexusSec/HORUS", "Accept-Encoding": "gzip"}
_VESSELS = {"ts": 0, "map": {}}


def _vessels_map():
    """Mappa MMSI -> metadati nave (nome, IMO, call sign, destinazione).

    Cache 5 min: i metadati cambiano lenti e l'elenco e' grosso, inutile
    riscaricarlo a ogni refresh delle posizioni."""
    now = time.time()
    if _VESSELS["map"] and now - _VESSELS["ts"] < 300:
        return _VESSELS["map"]
    try:
        arr = _fetch("https://meri.digitraffic.fi/api/ais/v1/vessels", headers=_DIGI_HDR)
        m = {}
        for v in arr:
            m[v.get("mmsi")] = {
                "name": (v.get("name") or "").strip(),
                "imo": v.get("imo") or "",
                "callSign": (v.get("callSign") or "").strip(),
                "destination": (v.get("destination") or "").strip(),
                "shipType": v.get("shipType"),
            }
        _VESSELS["map"] = m
        _VESSELS["ts"] = now
    except Exception:
        pass
    return _VESSELS["map"]


def _ships_geojson(data):
    """Inietta nome/IMO/destinazione (da /vessels) nelle posizioni AIS."""
    vm = _vessels_map()
    for f in data.get("features", []):
        p = f.get("properties") or {}
        meta = vm.get(p.get("mmsi"))
        if meta:
            for k, v in meta.items():
                if v not in (None, ""):
                    p[k] = v
        f["properties"] = p
    return data


def _aisstream_key():
    """Chiave aisstream.io (gratuita): da NXS_AISSTREAM_KEY o ~/.config/nxs/aisstream.key."""
    k = os.environ.get("NXS_AISSTREAM_KEY", "").strip()
    if k:
        return k
    try:
        return (Path.home() / ".config" / "nxs" / "aisstream.key").read_text().strip()
    except OSError:
        return ""


def _aisstream_snapshot(key, seconds=8, bbox=None, cap=4000):
    """Fotografia delle navi via aisstream.io (WebSocket, chiave gratuita).

    aisstream e' uno stream continuo: apriamo, ci sottoscriviamo a un RIQUADRO,
    raccogliamo per qualche secondo e deduplichiamo per MMSI. Il riquadro e'
    decisivo: sul mondo intero in pochi secondi si prende solo un campione
    sottile e sparso (una zona densa come lo Stretto di Hormuz resterebbe vuota);
    passando il bbox della vista corrente, aisstream manda SOLO quell'area e la
    si popola davvero. bbox = (sud, ovest, nord, est); None = mondo intero.
    Best-effort: aisstream puo' tornare vuoto se ha problemi a monte.
    """
    from nxs_horus import wsmini
    if bbox:
        s, w, n, e = bbox
        boxes = [[[s, w], [n, e]]]
    else:
        boxes = [[[-90, -180], [90, 180]]]
    sub = json.dumps({
        "APIKey": key,
        "BoundingBoxes": boxes,
        "FilterMessageTypes": ["PositionReport"],
    })
    tor = (TOR_HOST, TOR_PORT) if _tor_up() else None
    msgs = wsmini.snapshot("stream.aisstream.io", "/v0/stream", sub,
                           seconds=seconds, tor=tor)
    seen = {}
    for raw in msgs:
        try:
            d = json.loads(raw)
        except ValueError:
            continue
        if isinstance(d, dict) and d.get("error"):
            raise IOError(str(d["error"]))
        meta = d.get("MetaData") or {}
        pr = (d.get("Message") or {}).get("PositionReport") or {}
        mmsi = meta.get("MMSI")
        lat = meta.get("latitude", pr.get("Latitude"))
        lon = meta.get("longitude", pr.get("Longitude"))
        if mmsi is None or lat is None or lon is None:
            continue
        seen[mmsi] = {
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "mmsi": mmsi, "name": (meta.get("ShipName") or "").strip(),
                "sog": pr.get("Sog"), "cog": pr.get("Cog"),
                "heading": pr.get("TrueHeading"),
                "navStat": pr.get("NavigationalStatus"),
            },
        }
        if len(seen) >= cap:
            break
    feats = [{"type": "Feature", "geometry": v["geometry"],
              "properties": v["properties"]} for v in seen.values()]
    return {"type": "FeatureCollection", "features": feats}


class AisStream:
    """Flusso AIS CONTINUO via aisstream.io. Un thread tiene aperta la
    connessione WebSocket, aggiorna di continuo uno store {MMSI -> nave} e
    riaggancia da solo se cade. La vista chiede lo snapshot corrente (istantaneo,
    niente attese) e puo' spostare il riquadro sottoscritto: cosi' l'area che
    guardi si popola davvero (Hormuz, Malacca, Gibilterra...). Lato client le
    navi vengono accumulate in IndexedDB e restano tra un giro e l'altro."""

    STALE = 1800        # scarta le navi non viste da 30 min
    MAX = 40000         # tetto di sicurezza sullo store in memoria

    def __init__(self):
        self.lock = threading.Lock()
        self.vessels = {}       # mmsi -> {"geometry","properties","ts"}
        self.bbox = None        # (sud, ovest, nord, est) o None = mondo
        self.bbox_ver = 0
        self.running = False
        self.key = ""
        self.connected = False
        self.last_msg = 0
        self._ingested = 0

    def ensure(self, key):
        with self.lock:
            if self.running:
                return
            self.running = True
            self.key = key
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def set_bbox(self, bbox):
        with self.lock:
            if bbox != self.bbox:
                self.bbox = bbox
                self.bbox_ver += 1

    def _subscription(self):
        with self.lock:
            b = self.bbox
        boxes = [[[b[0], b[1]], [b[2], b[3]]]] if b else [[[-90, -180], [90, 180]]]
        return json.dumps({"APIKey": self.key, "BoundingBoxes": boxes,
                           "FilterMessageTypes": ["PositionReport"]})

    def snapshot(self):
        now = time.time()
        with self.lock:
            feats = [{"type": "Feature", "geometry": v["geometry"],
                      "properties": v["properties"]}
                     for v in self.vessels.values() if now - v["ts"] < self.STALE]
        return {"type": "FeatureCollection", "features": feats,
                "streaming": True, "connected": self.connected}

    def status(self):
        with self.lock:
            return {"running": self.running, "connected": self.connected,
                    "vessels": len(self.vessels), "last_msg": self.last_msg}

    def _prune(self):
        now = time.time()
        with self.lock:
            stale = [k for k, v in self.vessels.items() if now - v["ts"] >= self.STALE]
            for k in stale:
                del self.vessels[k]
            if len(self.vessels) > self.MAX:   # tieni le piu' recenti
                items = sorted(self.vessels.items(), key=lambda kv: kv[1]["ts"])
                for k, _ in items[:len(self.vessels) - self.MAX]:
                    del self.vessels[k]

    def _ingest(self, raw):
        try:
            d = json.loads(raw)
        except ValueError:
            return
        if not isinstance(d, dict):
            return
        meta = d.get("MetaData") or {}
        pr = (d.get("Message") or {}).get("PositionReport") or {}
        mmsi = meta.get("MMSI")
        lat = meta.get("latitude", pr.get("Latitude"))
        lon = meta.get("longitude", pr.get("Longitude"))
        if mmsi is None or lat is None or lon is None:
            return
        now = time.time()
        rec = {
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "mmsi": mmsi, "name": (meta.get("ShipName") or "").strip(),
                "sog": pr.get("Sog"), "cog": pr.get("Cog"),
                "heading": pr.get("TrueHeading"),
                "navStat": pr.get("NavigationalStatus"),
            },
            "ts": now,
        }
        with self.lock:
            self.vessels[mmsi] = rec
            self.last_msg = now
        self._ingested += 1
        if self._ingested % 2000 == 0:
            self._prune()

    def _run(self):
        from nxs_horus import wsmini
        backoff = 2
        while self.running:
            cli = None
            cur_ver = self.bbox_ver
            try:
                tor = (TOR_HOST, TOR_PORT) if _tor_up() else None
                cli = wsmini.WSClient("stream.aisstream.io", "/v0/stream", tor=tor)
                cli.send_text(self._subscription())
                cur_ver = self.bbox_ver
                with self.lock:
                    self.connected = True
                backoff = 2
                while self.running:
                    payload = cli.recv(1.5)
                    # riquadro cambiato -> riaggancia con la nuova sottoscrizione
                    if self.bbox_ver != cur_ver:
                        break
                    if payload:
                        self._ingest(payload)
            except Exception:
                pass
            finally:
                with self.lock:
                    self.connected = False
                if cli:
                    cli.close()
            if not self.running:
                break
            # backoff prima di riconnettere (a meno che sia solo un cambio bbox)
            if self.bbox_ver == cur_ver:
                for _ in range(int(backoff * 10)):
                    if not self.running:
                        break
                    time.sleep(0.1)
                backoff = min(backoff * 2, 20)


_AIS = AisStream()


# Le news sono uno STANDARD (RSS/Atom): qualunque sito con un feed si aggancia.
# Set di default + estendibile dall'utente in ~/.config/nxs/news-feeds.txt
# (una URL per riga, '#' per i commenti).
# Catalogo fonti news selezionabili dal pannello Impostazioni. Mix di testate
# internazionali (per non essere sbilanciati sull'Italia) + fonti italiane.
NEWS_CATALOG = [
    # --- Italia ---
    {"id": "gnews_it", "name": "Google News (Italia)", "region": "Italia",
     "url": "https://news.google.com/rss?hl=it&gl=IT&ceid=IT:it"},
    {"id": "ansa", "name": "ANSA", "region": "Italia",
     "url": "https://www.ansa.it/sito/ansait_rss.xml"},
    # --- Europa ---
    {"id": "bbc", "name": "BBC World", "region": "Europa",
     "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
    {"id": "guardian", "name": "The Guardian (World)", "region": "Europa",
     "url": "https://www.theguardian.com/world/rss"},
    {"id": "france24", "name": "France 24 (EN)", "region": "Europa",
     "url": "https://www.france24.com/en/rss"},
    {"id": "dw", "name": "Deutsche Welle (EN)", "region": "Europa",
     "url": "https://rss.dw.com/rdf/rss-en-all"},
    {"id": "euronews", "name": "Euronews", "region": "Europa",
     "url": "https://www.euronews.com/rss"},
    # --- Nord America ---
    {"id": "gnews_en", "name": "Google News (Mondo, EN)", "region": "Nord America",
     "url": "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"},
    {"id": "npr", "name": "NPR (World)", "region": "Nord America",
     "url": "https://feeds.npr.org/1004/rss.xml"},
    {"id": "cnn", "name": "CNN (World)", "region": "Nord America",
     "url": "http://rss.cnn.com/rss/edition_world.rss"},
    # --- America Latina ---
    {"id": "mercopress", "name": "MercoPress (EN)", "region": "America Latina",
     "url": "https://en.mercopress.com/rss/"},
    # --- Russia ---
    {"id": "tass", "name": "TASS (EN)", "region": "Russia",
     "url": "https://tass.com/rss/v2.xml"},
    {"id": "moscowtimes", "name": "The Moscow Times (EN)", "region": "Russia",
     "url": "https://www.themoscowtimes.com/rss/news"},
    # --- Cina ---
    {"id": "chinadaily", "name": "China Daily", "region": "Cina",
     "url": "http://www.chinadaily.com.cn/rss/world_rss.xml"},
    {"id": "globaltimes", "name": "Global Times", "region": "Cina",
     "url": "https://www.globaltimes.cn/rss/outbrain.xml"},
    # --- Medio Oriente ---
    {"id": "aljazeera", "name": "Al Jazeera", "region": "Medio Oriente",
     "url": "https://www.aljazeera.com/xml/rss/all.xml"},
    {"id": "timesofisrael", "name": "The Times of Israel", "region": "Medio Oriente",
     "url": "https://www.timesofisrael.com/feed/"},
    # --- Asia / Pacifico ---
    {"id": "toi", "name": "Times of India", "region": "Asia / Pacifico",
     "url": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms"},
    {"id": "japantimes", "name": "The Japan Times", "region": "Asia / Pacifico",
     "url": "https://www.japantimes.co.jp/feed/"},
    # --- Oceania ---
    {"id": "abc_au", "name": "ABC Australia", "region": "Oceania",
     "url": "https://www.abc.net.au/news/feed/51120/rss.xml"},
    {"id": "smh", "name": "Sydney Morning Herald", "region": "Oceania",
     "url": "https://www.smh.com.au/rss/feed.xml"},
    # --- Africa ---
    {"id": "allafrica", "name": "AllAfrica", "region": "Africa",
     "url": "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf"},
]
# Ordine di visualizzazione delle zone nel pannello.
NEWS_REGIONS = ["Italia", "Europa", "Nord America", "America Latina", "Russia",
                "Cina", "Medio Oriente", "Asia / Pacifico", "Oceania", "Africa"]
# Acceso di default: copertura MONDIALE (almeno una fonte per zona).
DEFAULT_NEWS_IDS = ["gnews_it", "ansa", "bbc", "guardian", "gnews_en",
                    "mercopress", "tass", "chinadaily", "aljazeera", "toi",
                    "abc_au", "allafrica"]


def _enabled_news_ids():
    txt = _read_conf_text("news-sources.txt")
    if not txt.strip():
        return set(DEFAULT_NEWS_IDS)     # file assente/vuoto -> default
    return set(l.strip() for l in txt.splitlines()
               if l.strip() and not l.startswith("#"))


def _news_sources_status():
    ids = _enabled_news_ids()
    return [{"id": c["id"], "name": c["name"], "region": c["region"],
             "on": c["id"] in ids} for c in NEWS_CATALOG]


def _news_feeds():
    ids = _enabled_news_ids()
    feeds = [c["url"] for c in NEWS_CATALOG if c["id"] in ids]
    # Feed RSS extra dell'utente (una URL per riga).
    try:
        txt = (Path.home() / ".config" / "nxs" / "news-feeds.txt").read_text()
        for line in txt.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                feeds.append(line)
    except OSError:
        pass
    return feeds


def _parse_rss(raw, source_hint=""):
    """Estrae gli item da un RSS/Atom. Ritorna lista di articoli."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(raw)
    out = []
    # RSS: .//item ; Atom: .//{ns}entry
    items = root.iterfind(".//item")
    arts = list(items)
    if not arts:
        arts = [e for e in root.iter() if e.tag.endswith("}entry") or e.tag == "entry"]
    for it in arts:
        title = (it.findtext("title") or "").strip()
        if not title:
            # Atom title puo' avere namespace
            for ch in it:
                if ch.tag.endswith("}title") or ch.tag == "title":
                    title = (ch.text or "").strip()
                    break
        if not title:
            continue
        link = (it.findtext("link") or "").strip()
        if not link:
            for ch in it:  # Atom: <link href="...">
                if ch.tag.endswith("}link") or ch.tag == "link":
                    link = (ch.get("href") or ch.text or "").strip()
                    break
        src = (it.findtext("source") or "").strip() or source_hint
        date = (it.findtext("pubDate") or it.findtext("{*}updated") or "").strip()
        out.append({"title": title, "url": link, "domain": src, "date": date})
    return out


def _gdelt(query, maxrecords=75):
    """Ricerca su GDELT DOC 2.0: database MONDIALE di notizie (migliaia di
    testate in 65+ lingue), keyless. Da' copertura a 360 gradi che i soli feed
    RSS non raggiungono. Ritorna articoli nello stesso formato di _parse_rss,
    arricchiti con paese e lingua della fonte. Best-effort."""
    from email.utils import formatdate
    from calendar import timegm
    q = (query or "").strip()
    if not q:
        return []
    # GDELT vuole le frasi tra virgolette; se ci sono spazi le racchiudiamo.
    if " " in q and '"' not in q:
        q = '"%s"' % q
    url = ("https://api.gdeltproject.org/api/v2/doc/doc?query=%s"
           "&mode=ArtList&format=json&sort=DateDesc&maxrecords=%d"
           % (quote(q), int(maxrecords)))
    try:
        # GDELT puo' essere lento (aggrega migliaia di fonti): timeout piu' largo.
        data = _fetch(url, timeout=35)
    except Exception:
        return []
    out = []
    for a in (data.get("articles") or []):
        title = (a.get("title") or "").strip()
        link = (a.get("url") or "").strip()
        if not title or not link:
            continue
        dom = (a.get("domain") or "").replace("www.", "")
        country = (a.get("sourcecountry") or "").strip()
        # seendate: "YYYYMMDDTHHMMSSZ" -> RFC 2822 (ordinabile come gli RSS)
        date = ""
        sd = (a.get("seendate") or "").strip()
        try:
            if sd:
                ts = timegm(time.strptime(sd, "%Y%m%dT%H%M%SZ"))
                date = formatdate(ts, usegmt=True)
        except Exception:
            pass
        item = {"title": title, "url": link,
                "domain": dom + ((" · " + country) if country else ""),
                "date": date, "via": "GDELT"}
        img = (a.get("socialimage") or "").strip()
        if img:
            item["image"] = img
        if a.get("language"):
            item["language"] = a["language"]
        out.append(item)
    return out


def _http_text(url, data=None, headers=None, timeout=None):
    """GET/POST che ritorna testo decodificato (segue l'opener Tor/diretto).
    Scompatta gzip. Usato dai resolver news (DuckDuckGo, Google News)."""
    h = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h)
    with _opener().open(req, timeout=(timeout or TIMEOUT)) as r:
        raw = r.read()
        if (r.headers.get("Content-Encoding", "") or "").lower() == "gzip":
            import gzip
            raw = gzip.decompress(raw)
    return raw.decode("utf-8", "replace")


def _ddg_locale(lang):
    """Mappa una lingua (it/en/fr/de/es/world) al codice locale DuckDuckGo."""
    return {"it": "it-it", "en": "us-en", "fr": "fr-fr", "de": "de-de",
            "es": "es-es", "world": "wt-wt"}.get((lang or "it"), "it-it")


def _ddg_news(query, maxrecords=40, df="", lang="it"):
    """Ricerca notizie su DuckDuckGo (verticale news, keyless). Restituisce URL
    DIRETTI (niente wrapper: apribili nel lettore) e fonti varie. `df` filtra la
    finestra temporale: '' (qualsiasi), 'd' (giorno), 'w' (settimana), 'm'
    (mese). Best-effort."""
    from email.utils import formatdate
    q = (query or "").strip()
    if not q:
        return []
    loc = _ddg_locale(lang)
    dfp = ("&df=" + df) if df in ("d", "w", "m") else ""
    try:
        # 1) token vqd (obbligatorio per l'endpoint news.js)
        seed = _http_text("https://duckduckgo.com/?q=%s&iar=news&ia=news" % quote(q),
                          timeout=12)
        m = re.search(r'vqd=["\']?([\d-]+)', seed) or re.search(r'vqd=([\w-]+)', seed)
        if not m:
            return []
        vqd = m.group(1)
        # 2) risultati news in JSON
        url = ("https://duckduckgo.com/news.js?l=%s&o=json&noamp=1%s"
               "&q=%s&vqd=%s&p=1" % (loc, dfp, quote(q), vqd))
        data = json.loads(_http_text(url, timeout=12))
    except Exception:
        return []
    out = []
    for a in (data.get("results") or [])[:maxrecords]:
        title = (a.get("title") or "").strip()
        link = (a.get("url") or "").strip()
        if not title or not link:
            continue
        dom = urlparse(link).netloc.replace("www.", "")
        date = ""
        try:
            if a.get("date"):
                date = formatdate(int(a["date"]), usegmt=True)
        except Exception:
            pass
        item = {"title": title, "url": link,
                "domain": (a.get("source") or dom), "date": date, "via": "DuckDuckGo"}
        if a.get("image"):
            item["image"] = a["image"]
        out.append(item)
    return out


def _gnews_resolve(url):
    """Google News RSS incapsula gli articoli in URL wrapper opachi
    (news.google.com/rss/articles/CBMi...): non sono ne' apribili ne' estraibili.
    Li risolve nell'URL reale via l'endpoint batchexecute. Best-effort: se
    fallisce ritorna None (si tiene il wrapper)."""
    m = re.search(r"/(?:rss/)?articles/([^?/]+)", url or "")
    if not m:
        return None
    b64 = m.group(1)
    try:
        html = _http_text("https://news.google.com/rss/articles/%s" % b64, timeout=12)
        sg = re.search(r'data-n-a-sg="([^"]+)"', html)
        ts = re.search(r'data-n-a-ts="([^"]+)"', html)
        if not (sg and ts):
            return None
        inner = json.dumps(["garturlreq",
                            [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None,
                              1, None, None, None, None, None, 0, 1],
                             "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
                            b64, int(ts.group(1)), sg.group(1)])
        freq = json.dumps([[["Fbv4je", inner, None, "1"]]])
        body = ("f.req=" + quote(freq)).encode()
        resp = _http_text("https://news.google.com/_/DotsSplashUi/data/batchexecute",
                          data=body, timeout=12,
                          headers={"Content-Type":
                                   "application/x-www-form-urlencoded;charset=UTF-8"})
        r = re.search(r'garturlres\\",\\"(https?:[^\\"]+)', resp)
        if r:
            return r.group(1).replace("\\/", "/").replace("\\u003d", "=")
    except Exception:
        return None
    return None


def _news_engine():
    """Motore di ricerca news scelto: 'google' | 'duckduckgo' | 'both'
    (default: both). Impostabile da Settings."""
    v = _read_conf_text("news-engine.txt").strip().lower()
    return v if v in ("google", "duckduckgo", "both") else "both"


def _norm_title_tokens(t):
    """Token significativi di un titolo (per raggruppare la stessa notizia)."""
    t = (t or "").lower()
    t = re.sub(r"[^\w\s]", " ", t, flags=re.U)
    return set(w for w in t.split() if len(w) > 3)


def _cluster_news(uniq):
    """Raggruppa titoli molto simili (stessa storia ripresa da piu' testate).
    Tiene il primo di ogni gruppo (il piu' recente, la lista arriva ordinata) e
    vi allega l'elenco delle fonti -> nel ticker compare '+N fonti'."""
    clusters = []
    for a in uniq:
        toks = _norm_title_tokens(a.get("title", ""))
        placed = False
        if toks:
            for c in clusters:
                inter = len(toks & c["toks"])
                base = min(len(toks), len(c["toks"])) or 1
                if inter / base >= 0.6:                # >=60% token in comune
                    c["sources"].append(a.get("domain", ""))
                    placed = True
                    break
        if not placed:
            clusters.append({"toks": toks, "rep": a,
                             "sources": [a.get("domain", "")]})
    out = []
    for c in clusters:
        rep = c["rep"]
        srcs = [s for s in dict.fromkeys(c["sources"]) if s]   # unici, in ordine
        rep["sources"] = srcs
        rep["sources_count"] = len(srcs)
        out.append(rep)
    return out


def _news(query="world", df="", lang="it"):
    """Notizie per il ticker. Aggrega piu' feed RSS (standard), le deduplica e
    le ordina dalla piu' recente. Con una query cerca su Google News e/o
    DuckDuckGo (verticale news) secondo il motore scelto nei Settings; `df`
    filtra la finestra temporale ('' /d /w /m) e `lang` la lingua."""
    from email.utils import parsedate_to_datetime
    if query and query != "world":
        from concurrent.futures import ThreadPoolExecutor
        engine = _news_engine()
        # Google News: hl/gl/ceid dalla lingua; finestra temporale via 'when:'.
        gl = {"it": ("it", "IT"), "en": ("en-US", "US"), "fr": ("fr", "FR"),
              "de": ("de", "DE"), "es": ("es", "ES"),
              "world": ("en-US", "US")}.get(lang, ("it", "IT"))
        gq = query + {"d": " when:1d", "w": " when:7d",
                      "m": " when:30d"}.get(df, "")
        gnews_url = ("https://news.google.com/rss/search?q=%s&hl=%s&gl=%s&ceid=%s:%s"
                     % (quote(gq), gl[0], gl[1], gl[1], gl[0].split("-")[0]))

        def _gn():
            try:
                return _parse_rss(_http_text(gnews_url, timeout=12).encode("utf-8",
                                                                            "replace"))
            except Exception:
                return []
        # Fonti in parallelo secondo il motore selezionato. DuckDuckGo da' URL
        # diretti (apribili); Google News e' ottimo per l'italiano.
        tasks = []
        with ThreadPoolExecutor(max_workers=2) as ex:
            if engine in ("google", "both"):
                tasks.append(ex.submit(_gn))
            if engine in ("duckduckgo", "both"):
                tasks.append(ex.submit(_ddg_news, query, 40, df, lang))
            arts = []
            for t in tasks:
                try:
                    arts += t.result(timeout=20)
                except Exception:
                    pass
        # dedup per titolo, poi per URL
        seen_t, seen_u, uniq = set(), set(), []
        for a in arts:
            t, u = a.get("title", ""), a.get("url", "")
            if t in seen_t or (u and u in seen_u):
                continue
            seen_t.add(t)
            if u:
                seen_u.add(u)
            uniq.append(a)

        def _key(a):
            try:
                return parsedate_to_datetime(a["date"]).timestamp()
            except (TypeError, ValueError):
                return 0
        uniq.sort(key=_key, reverse=True)
        if not uniq:
            return {"articles": [], "error": "nessun risultato"}
        # Raggruppa la stessa storia (piu' fonti) e poi taglia.
        return {"articles": _cluster_news(uniq)[:80]}
    def _one(feed):
        try:
            with _opener().open(urllib.request.Request(feed, headers={"User-Agent": UA}),
                                timeout=8) as r:
                dom = urlparse(feed).netloc.replace("www.", "").replace("feeds.", "")
                return _parse_rss(r.read(), source_hint=dom)
        except Exception:
            return []
    # Fetch in PARALLELO: con molte fonti mondiali, in serie sarebbe lento.
    from concurrent.futures import ThreadPoolExecutor
    feeds = _news_feeds()
    arts = []
    if feeds:
        with ThreadPoolExecutor(max_workers=min(12, len(feeds))) as ex:
            for res in ex.map(_one, feeds):
                arts += res
    # dedup per titolo
    seen, uniq = set(), []
    for a in arts:
        if a["title"] in seen:
            continue
        seen.add(a["title"])
        uniq.append(a)
    # ordina per data (chi non si parsa va in fondo)
    def _key(a):
        try:
            return parsedate_to_datetime(a["date"]).timestamp()
        except (TypeError, ValueError):
            return 0
    uniq.sort(key=_key, reverse=True)
    return {"articles": uniq[:60]}


# ---------------------------------------------------------------------------
# Arricchimento indicatori (keyless): per un IP o un dominio raccoglie RDAP
# (rete/ASN/registrar), DNS (A/reverse) e geolocalizzazione. Tutto da servizi
# liberi, best-effort: ogni pezzo che fallisce viene semplicemente omesso.
# ---------------------------------------------------------------------------
def _rdap(path):
    try:
        return json.loads(_http_text("https://rdap.org/" + path, timeout=10,
                                     headers={"Accept": "application/rdap+json"}))
    except Exception:
        return {}


def _geoip(ip):
    """Geolocalizzazione IP keyless (ipwho.is). Ritorna dict ridotto."""
    try:
        d = json.loads(_http_text("https://ipwho.is/%s" % quote(ip), timeout=10))
        if not d.get("success", True):
            return {}
        return {"lat": d.get("latitude"), "lon": d.get("longitude"),
                "city": d.get("city"), "region": d.get("region"),
                "country": d.get("country"), "country_code": d.get("country_code"),
                "asn": (d.get("connection") or {}).get("asn"),
                "org": (d.get("connection") or {}).get("org")
                       or (d.get("connection") or {}).get("isp")}
    except Exception:
        return {}


def _rdap_ip_summary(net):
    """Estrae rete/ASN/paese da un oggetto RDAP di tipo 'ip network'."""
    if not net:
        return {}
    out = {}
    if net.get("handle"):
        out["net_handle"] = net["handle"]
    if net.get("name"):
        out["net_name"] = net["name"]
    if net.get("country"):
        out["country"] = net["country"]
    start, end = net.get("startAddress"), net.get("endAddress")
    if start and end:
        out["range"] = "%s - %s" % (start, end)
    # nome dell'organizzazione dalle entita'
    for e in (net.get("entities") or []):
        for v in ((e.get("vcardArray") or [None, []])[1] or []):
            if v and v[0] == "fn" and len(v) > 3:
                out.setdefault("org", v[3])
    return out


def _enrich_ip(ip):
    from concurrent.futures import ThreadPoolExecutor
    out = {"kind": "ip", "value": ip}
    with ThreadPoolExecutor(max_workers=3) as ex:
        f_geo = ex.submit(_geoip, ip)
        f_rdap = ex.submit(_rdap, "ip/" + quote(ip))
        f_rev = ex.submit(lambda: _safe_reverse(ip))
        geo = f_geo.result()
        rdap = _rdap_ip_summary(f_rdap.result())
        rev = f_rev.result()
    if geo:
        out["geo"] = geo
        if geo.get("asn"):
            out["asn"] = "AS%s" % geo["asn"]
        if geo.get("org"):
            out["org"] = geo["org"]
    if rdap:
        out["rdap"] = rdap
        out.setdefault("org", rdap.get("org"))
    if rev:
        out["reverse_dns"] = rev
    return out


def _safe_reverse(ip):
    import socket
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return ""


def _enrich_domain(domain):
    import socket
    from concurrent.futures import ThreadPoolExecutor
    domain = domain.strip().lower().rstrip(".")
    out = {"kind": "domain", "value": domain}
    # A record(s)
    ips = []
    try:
        for fam, _, _, _, sa in socket.getaddrinfo(domain, None):
            ip = sa[0]
            if ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    out["ips"] = ips
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_rdap = ex.submit(_rdap, "domain/" + quote(domain))
        f_ip = ex.submit(_enrich_ip, ips[0]) if ips else None
        rdap = f_rdap.result()
        if f_ip:
            out["primary_ip"] = f_ip.result()
    if rdap:
        info = {}
        for ev in (rdap.get("events") or []):
            act = ev.get("eventAction", "")
            if act in ("registration", "expiration", "last changed"):
                info[act] = (ev.get("eventDate") or "")[:10]
        for e in (rdap.get("entities") or []):
            roles = e.get("roles") or []
            if "registrar" in roles:
                for v in ((e.get("vcardArray") or [None, []])[1] or []):
                    if v and v[0] == "fn" and len(v) > 3:
                        info["registrar"] = v[3]
        ns = [n.get("ldhName", "") for n in (rdap.get("nameservers") or []) if n.get("ldhName")]
        if ns:
            info["nameservers"] = ns
        if rdap.get("status"):
            info["status"] = rdap["status"]
        if info:
            out["rdap"] = info
    return out


def _enrich(kind, value):
    value = (value or "").strip()
    if not value:
        return {"error": "valore mancante"}
    if kind == "ip":
        return _enrich_ip(value)
    if kind == "domain":
        return _enrich_domain(value)
    return {"error": "tipo non supportato (usa ip|domain)"}


def _resolve_article(url):
    """Segue i redirect e dice se la pagina si puo' incorporare in un iframe
    (X-Frame-Options / CSP frame-ancestors). Serve al lettore in-window."""
    with _opener().open(urllib.request.Request(url, headers={"User-Agent": UA}),
                        timeout=TIMEOUT) as r:
        final = r.geturl()
        xfo = (r.headers.get("X-Frame-Options", "") or "").upper()
        csp = (r.headers.get("Content-Security-Policy", "") or "").lower()
    embeddable = ("DENY" not in xfo and "SAMEORIGIN" not in xfo
                  and "frame-ancestors" not in csp)
    return {"url": final, "embeddable": embeddable}


# Modalita' lettura: tanti siti vietano l'iframe (X-Frame-Options/CSP), quindi
# invece di incorporare la pagina ne ESTRAIAMO il testo qui e lo mostriamo
# pulito nella finestrella. Niente dipendenze: un piccolo HTMLParser che salta
# i blocchi di contorno (nav/footer/script...) e tiene i paragrafi veri.
from html.parser import HTMLParser


class _Reader(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "form", "nav", "header",
            "footer", "aside", "figure", "button", "iframe", "template"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.in_p = False
        self.in_title = False
        self.cur = []
        self.paras = []
        self.title_tag = ""
        self.og_title = ""
        self.og_image = ""
        self.date = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta":
            prop = (a.get("property") or a.get("name") or "").lower()
            cont = a.get("content", "") or ""
            if prop in ("og:title", "twitter:title") and not self.og_title:
                self.og_title = cont
            elif prop in ("og:image", "twitter:image", "twitter:image:src") and not self.og_image:
                self.og_image = cont
            elif prop in ("article:published_time", "datepublished", "date", "pubdate") and not self.date:
                self.date = cont
            return
        if tag in self.SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if tag == "title":
            self.in_title = True
        elif tag == "p":
            self.in_p = True
            self.cur = []
        elif tag == "br" and self.in_p:
            self.cur.append(" ")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
            return
        if self.skip:
            return
        if tag == "title":
            self.in_title = False
        elif tag == "p" and self.in_p:
            txt = re.sub(r"\s+", " ", "".join(self.cur)).strip()
            if len(txt) >= 40:
                self.paras.append(txt)
            self.in_p = False
            self.cur = []

    def handle_data(self, data):
        if self.skip:
            return
        if self.in_title and not self.title_tag:
            self.title_tag = data.strip()
        elif self.in_p:
            self.cur.append(data)


# ===========================================================================
# Intelligence fotografica: estrazione metadati EXIF (con GPS) dalle immagini.
# Parser JPEG NATIVO (nessuna dipendenza: gira su Alpine "nuda"); se e'
# disponibile `exiftool` lo usiamo per arricchire i campi.
# ===========================================================================
_EXIF_TAGS = {0x010F: "Make", 0x0110: "Model", 0x0112: "Orientation",
              0x0132: "DateTime", 0x9003: "DateTimeOriginal", 0x829A: "ExposureTime",
              0x8827: "ISO", 0xA002: "PixelXDimension", 0xA003: "PixelYDimension",
              0x0131: "Software"}
_TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8}


def _exif_read_ifd(buf, off, endian):
    """Legge una IFD TIFF; ritorna (dict tag->valore, next_ifd_offset)."""
    out = {}
    if off + 2 > len(buf):
        return out, 0
    n = struct.unpack(endian + "H", buf[off:off + 2])[0]
    p = off + 2
    for _ in range(n):
        if p + 12 > len(buf):
            break
        tag, typ, cnt = struct.unpack(endian + "HHI", buf[p:p + 8])
        size = _TYPE_SIZE.get(typ, 0) * cnt
        if size == 0:
            p += 12
            continue
        if size <= 4:
            valbytes = buf[p + 8:p + 8 + size]
        else:
            voff = struct.unpack(endian + "I", buf[p + 8:p + 12])[0]
            valbytes = buf[voff:voff + size]
        out[tag] = _exif_val(valbytes, typ, cnt, endian)
        p += 12
    nxt = 0
    if p + 4 <= len(buf):
        nxt = struct.unpack(endian + "I", buf[p:p + 4])[0]
    return out, nxt


def _exif_val(b, typ, cnt, endian):
    try:
        if typ == 2:                       # ASCII
            return b.split(b"\x00", 1)[0].decode("utf-8", "replace")
        if typ in (1, 7):                  # BYTE / UNDEFINED
            return list(b)
        if typ == 3:                       # SHORT
            v = [struct.unpack(endian + "H", b[i:i + 2])[0] for i in range(0, len(b), 2)]
            return v[0] if cnt == 1 else v
        if typ in (4, 9):                  # LONG / SLONG
            f = "i" if typ == 9 else "I"
            v = [struct.unpack(endian + f, b[i:i + 4])[0] for i in range(0, len(b), 4)]
            return v[0] if cnt == 1 else v
        if typ in (5, 10):                 # RATIONAL / SRATIONAL
            f = "ii" if typ == 10 else "II"
            r = []
            for i in range(0, len(b), 8):
                num, den = struct.unpack(endian + f, b[i:i + 8])
                r.append(num / den if den else 0.0)
            return r[0] if cnt == 1 else r
    except struct.error:
        return None
    return None


def _gps_decimal(vals, ref):
    """Converte [gradi,minuti,secondi] + rif (N/S/E/W) in decimale."""
    try:
        d = vals[0] + vals[1] / 60.0 + vals[2] / 3600.0
        if ref in ("S", "W"):
            d = -d
        return round(d, 6)
    except (TypeError, IndexError):
        return None


def _jpeg_exif(raw):
    """Estrae i metadati EXIF da un JPEG con parser nativo. Ritorna dict."""
    res = {"tags": {}, "gps": None}
    if raw[:2] != b"\xff\xd8":
        return res
    i, app1 = 2, None
    while i + 4 < len(raw):
        if raw[i] != 0xFF:
            break
        marker = raw[i + 1]
        seglen = struct.unpack(">H", raw[i + 2:i + 4])[0]
        if marker == 0xE1 and raw[i + 4:i + 10] == b"Exif\x00\x00":
            app1 = raw[i + 10:i + 2 + seglen]
            break
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        i += 2 + seglen
    if not app1 or len(app1) < 8:
        return res
    endian = "<" if app1[:2] == b"II" else ">"
    ifd0_off = struct.unpack(endian + "I", app1[4:8])[0]
    ifd0, _ = _exif_read_ifd(app1, ifd0_off, endian)
    tags = {}
    for t, name in _EXIF_TAGS.items():
        if t in ifd0:
            tags[name] = ifd0[t]
    # Exif sub-IFD (DateTimeOriginal ecc.)
    if 0x8769 in ifd0:
        sub, _ = _exif_read_ifd(app1, ifd0[0x8769], endian)
        for t, name in _EXIF_TAGS.items():
            if t in sub:
                tags[name] = sub[t]
    # GPS IFD
    if 0x8825 in ifd0:
        gps, _ = _exif_read_ifd(app1, ifd0[0x8825], endian)
        lat = _gps_decimal(gps.get(2), gps.get(1))
        lon = _gps_decimal(gps.get(4), gps.get(3))
        if lat is not None and lon is not None:
            alt = gps.get(6)
            if isinstance(alt, list):
                alt = alt[0] if alt else None
            if gps.get(5) == 1 and isinstance(alt, (int, float)):
                alt = -alt
            res["gps"] = {"lat": lat, "lon": lon, "alt": alt}
    res["tags"] = tags
    return res


def _exif_extract(raw, name="foto"):
    """Estrae metadati: parser nativo + arricchimento exiftool se presente."""
    out = {"name": name, "size": len(raw), "tags": {}, "gps": None, "source": "nativo"}
    try:
        native = _jpeg_exif(raw)
        out["tags"].update({k: v for k, v in native["tags"].items()
                            if isinstance(v, (str, int, float))})
        out["gps"] = native["gps"]
    except Exception as e:                 # parser difensivo: mai far crashare
        out["error"] = "parser nativo: %s" % e
    # Arricchimento con exiftool (tag molto piu' ricchi), se installato.
    tool = shutil.which("exiftool")
    if tool:
        tmp = None
        try:
            fd, tmp = tempfile.mkstemp(suffix=".img")
            os.write(fd, raw)
            os.close(fd)
            r = subprocess.run([tool, "-json", "-n", "-a", "-G", "--", tmp],
                               capture_output=True, timeout=15)
            data = json.loads(r.stdout.decode("utf-8", "replace") or "[]")
            if data:
                d = data[0]
                # Tag di interesse per l'analista (senza rumore)
                keep = ("Make", "Model", "Software", "DateTimeOriginal", "CreateDate",
                        "ModifyDate", "LensModel", "FNumber", "ExposureTime", "ISO",
                        "FocalLength", "ImageWidth", "ImageHeight", "GPSAltitude",
                        "GPSDateTime", "Orientation", "SerialNumber")
                for k, v in d.items():
                    short = k.split(":")[-1]
                    if short in keep and short not in out["tags"]:
                        out["tags"][short] = v
                # GPS da exiftool (numerico grazie a -n)
                glat = d.get("EXIF:GPSLatitude", d.get("Composite:GPSLatitude", d.get("GPSLatitude")))
                glon = d.get("EXIF:GPSLongitude", d.get("Composite:GPSLongitude", d.get("GPSLongitude")))
                if out["gps"] is None and isinstance(glat, (int, float)) and isinstance(glon, (int, float)):
                    out["gps"] = {"lat": round(glat, 6), "lon": round(glon, 6),
                                  "alt": d.get("EXIF:GPSAltitude", d.get("GPSAltitude"))}
                out["source"] = "exiftool"
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
        finally:
            if tmp:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
    return out


# ===========================================================================
# SOCMINT: enumerazione di uno username sulle principali piattaforme.
# Come sherlock/maigret ma integrato e keyless: per ogni sito costruiamo l'URL
# del profilo e deduciamo l'esistenza da status HTTP e/o da una stringa nel
# corpo. Le richieste escono dal TUO IP (o da Tor). NB: trovare un profilo NON
# prova che sia la stessa persona (username uguali != stessa identita').
# Chiavi sito: url ({u}=username); not_status (status = "non esiste", def 404);
# present (stringa presente SOLO se esiste); absent (stringa presente se NON esiste).
# ===========================================================================
SOCMINT_SITES = [
    {"name": "GitHub", "url": "https://github.com/{u}"},
    {"name": "GitLab", "url": "https://gitlab.com/{u}"},
    {"name": "Reddit", "url": "https://www.reddit.com/user/{u}"},
    {"name": "Instagram", "url": "https://www.instagram.com/{u}/"},
    {"name": "TikTok", "url": "https://www.tiktok.com/@{u}"},
    {"name": "YouTube", "url": "https://www.youtube.com/@{u}"},
    {"name": "Pinterest", "url": "https://www.pinterest.com/{u}/"},
    {"name": "Medium", "url": "https://medium.com/@{u}"},
    {"name": "Dev.to", "url": "https://dev.to/{u}"},
    {"name": "Keybase", "url": "https://keybase.io/{u}"},
    {"name": "SoundCloud", "url": "https://soundcloud.com/{u}"},
    {"name": "Vimeo", "url": "https://vimeo.com/{u}"},
    {"name": "Flickr", "url": "https://www.flickr.com/people/{u}"},
    {"name": "Replit", "url": "https://replit.com/@{u}"},
    {"name": "Behance", "url": "https://www.behance.net/{u}"},
    {"name": "Dribbble", "url": "https://dribbble.com/{u}"},
    {"name": "Chess.com", "url": "https://www.chess.com/member/{u}"},
    {"name": "Gravatar", "url": "https://gravatar.com/{u}"},
    {"name": "Steam", "url": "https://steamcommunity.com/id/{u}",
     "absent": "The specified profile could not be found"},
    {"name": "Hacker News", "url": "https://news.ycombinator.com/user?id={u}",
     "absent": "No such user."},
    {"name": "Telegram", "url": "https://t.me/{u}", "present": "tgme_page_title"},
    {"name": "Last.fm", "url": "https://www.last.fm/user/{u}"},
]


def _socmint_check(site, user):
    url = site["url"].format(u=user)
    need_body = bool(site.get("present") or site.get("absent"))
    status, body = None, ""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA, "Accept-Language": "en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,*/*"})
        with _opener().open(req, timeout=8) as r:
            status = getattr(r, "status", r.getcode())
            if need_body:
                body = r.read(200000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status = e.code
    except Exception:
        return {"site": site["name"], "url": url, "status": None, "found": None}
    if site.get("present"):
        found = (status == 200 and site["present"] in body)
    elif site.get("absent"):
        found = (status == 200 and site["absent"] not in body)
    elif status == 200:
        found = True
    elif status == site.get("not_status", 404):
        found = False
    else:
        found = None                      # ambiguo (blocco, redirect, rate-limit)
    return {"site": site["name"], "url": url, "status": status, "found": found}


def _socmint(username):
    username = (username or "").strip()
    if not re.match(r"^[A-Za-z0-9._-]{2,64}$", username):
        return {"error": "username non valido (lettere, numeri, . _ - ; 2-64 caratteri)"}
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=12) as ex:
        results = list(ex.map(lambda s: _socmint_check(s, username), SOCMINT_SITES))
    results.sort(key=lambda r: (r["found"] is not True, r["site"].lower()))
    return {"username": username, "checked": len(results),
            "found_count": sum(1 for r in results if r["found"] is True),
            "results": results}


def _email_intel(email):
    """OSINT su un'email, KEYLESS: violazioni (XposedOrNot, senza chiave; HIBP
    ora e' a pagamento) + Gravatar (l'email e' usata su Gravatar? profilo e
    account collegati?). Le query escono dal proprio IP o da Tor."""
    email = (email or "").strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return {"error": "email non valida"}
    out = {"email": email, "breaches": [], "breach_details": [], "gravatar": None}
    # Violazioni note (XposedOrNot check-email: 404 = nessuna).
    try:
        d = _fetch("https://api.xposedornot.com/v1/check-email/" + quote(email))
        b = d.get("breaches")
        if isinstance(b, list) and b and isinstance(b[0], list):
            out["breaches"] = [x for x in b[0] if x]
    except Exception as e:
        out["breach_error"] = str(e)
    # Dettagli arricchiti (best-effort): date, record, tipi di dato esposti.
    try:
        a = _fetch("https://api.xposedornot.com/v1/breach-analytics?email=" + quote(email))
        det = ((a.get("ExposedBreaches") or {}).get("breaches_details")) or []
        for x in det:
            out["breach_details"].append({
                "name": x.get("breach") or x.get("Name"),
                "date": x.get("xposed_date"), "domain": x.get("domain"),
                "records": x.get("xposed_records"),
                "data": x.get("xposed_data"), "industry": x.get("industry")})
    except Exception:
        pass
    # Gravatar: MD5 dell'email -> profilo pubblico se esiste.
    md5 = hashlib.md5(email.encode("utf-8")).hexdigest()
    try:
        g = _fetch("https://en.gravatar.com/" + md5 + ".json")
        entry = (g.get("entry") or [])
        if entry:
            e0 = entry[0]
            out["gravatar"] = {
                "name": e0.get("displayName") or e0.get("name", {}).get("formatted", "") or "",
                "username": e0.get("preferredUsername") or "",
                "location": e0.get("currentLocation") or "",
                "thumb": e0.get("thumbnailUrl") or "",
                "profile": e0.get("profileUrl") or "",
                "accounts": [{"name": a.get("shortname") or a.get("name") or "",
                              "shortname": a.get("shortname") or "",
                              "username": a.get("username") or a.get("shortname") or "",
                              "url": a.get("url") or ""}
                             for a in (e0.get("accounts") or []) if a.get("url")]}
    except Exception:
        pass
    out["found"] = bool(out["breaches"] or out["gravatar"])
    return out


def _live_video_id(url):
    """Risolve il videoId della diretta YouTube in corso a partire dalla pagina
    /live di un canale. Serve perche' l'embed 'live_stream?channel=' e' stato
    deprecato ("video non disponibile"), mentre embed/<videoId> funziona. Il
    videoId cambia a ogni diretta, quindi va risolto ogni volta."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "it,en;q=0.8",
        # cookie di consenso: senza, gli IP UE ricevono la pagina consent senza video
        "Cookie": "CONSENT=YES+1; SOCS=CAI"})
    with _opener().open(req, timeout=TIMEOUT) as r:
        raw = r.read()
        if (r.headers.get("Content-Encoding", "") or "").lower() == "gzip":
            import gzip
            raw = gzip.decompress(raw)
    html = raw.decode("utf-8", "replace")
    # 1) link canonico della diretta corrente (il piu' affidabile)
    m = re.search(r'rel="canonical" href="https://www\.youtube\.com/watch\?v='
                  r'([A-Za-z0-9_-]{11})"', html)
    if not m:  # 2) fallback: primo videoId nel payload
        m = re.search(r'"videoId":"([A-Za-z0-9_-]{11})"', html)
    return m.group(1) if m else ""


def _extract_article(url):
    """Scarica l'articolo e ne estrae titolo, immagine e paragrafi. Cosi' la
    finestrella lettura funziona ANCHE con i siti che vietano l'iframe."""
    # Se e' un wrapper Google News lo risolviamo nell'URL reale: il wrapper non
    # e' estraibile (ritornerebbe 0 paragrafi = "non visualizzabile").
    if "news.google.com" in (url or "") and "/articles/" in url:
        real = _gnews_resolve(url)
        if real:
            url = real
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Accept-Encoding": "gzip",
        "Accept-Language": "it,en;q=0.8"})
    with _opener().open(req, timeout=TIMEOUT) as r:
        final = r.geturl()
        ctype = (r.headers.get("Content-Type", "") or "").lower()
        raw = r.read()
        if (r.headers.get("Content-Encoding", "") or "").lower() == "gzip":
            import gzip
            raw = gzip.decompress(raw)
    if "html" not in ctype and b"<html" not in raw[:2000].lower():
        return {"url": final, "paragraphs": [], "error": "la pagina non e' HTML"}
    enc = "utf-8"
    m = re.search(rb'charset=["\']?([\w\-]+)', raw[:4000], re.I)
    if m:
        try:
            enc = m.group(1).decode("ascii")
        except (UnicodeDecodeError, LookupError):
            pass
    try:
        text = raw.decode(enc, "replace")
    except LookupError:
        text = raw.decode("utf-8", "replace")
    p = _Reader()
    try:
        p.feed(text)
    except Exception:
        pass
    title = (p.og_title or p.title_tag or "").strip()
    img = p.og_image or ""
    if img and img.startswith("//"):
        img = "https:" + img
    return {"url": final, "title": title, "image": img,
            "date": p.date.strip(), "paragraphs": p.paras[:60]}

# ---------------------------------------------------------------------------
# Recon: whitelist. Ogni voce dice quali binari cercare, di che tipo e'
# l'obiettivo (per la validazione) e come costruire gli argomenti (LISTA).
# ---------------------------------------------------------------------------
def _args_whois(b, t):      return [b, t]
def _args_dig(b, t):        return [b, t, "ANY", "+noall", "+answer"] if b == "dig" else [b, t]
def _args_nmap(b, t):       return [b, "-T4", "-F", "--", t]
def _args_maigret(b, t):    return [b, t, "--no-color", "--timeout", "15"]
def _args_h8mail(b, t):     return [b, "-t", t]
def _args_holehe(b, t):     return [b, t]
def _args_subfinder(b, t):  return [b, "-d", t, "-silent"]
def _args_harvester(b, t):  return [b, "-d", t, "-b", "duckduckgo"]

RECON = {
    "whois":       {"nome": "WHOIS dominio", "kind": "domain", "bins": ["whois"], "args": _args_whois},
    "dig":         {"nome": "DNS (dig)", "kind": "domain", "bins": ["dig", "drill"], "args": _args_dig},
    "nmap":        {"nome": "Nmap (port scan veloce)", "kind": "host", "bins": ["nmap"], "args": _args_nmap},
    "maigret":     {"nome": "Maigret (username, 3000+ siti)", "kind": "username", "bins": ["maigret"], "args": _args_maigret},
    "h8mail":      {"nome": "h8mail (email nei breach)", "kind": "email", "bins": ["h8mail"], "args": _args_h8mail},
    "holehe":      {"nome": "holehe (email su servizi)", "kind": "email", "bins": ["holehe"], "args": _args_holehe},
    "subfinder":   {"nome": "subfinder (sottodomini)", "kind": "domain", "bins": ["subfinder"], "args": _args_subfinder},
    "theharvester": {"nome": "theHarvester (email/host)", "kind": "domain", "bins": ["theHarvester", "theharvester"], "args": _args_harvester},
}

# Validatori per tipo di obiettivo. Rifiutano tutto cio' che non combacia:
# l'input non arriva mai a una shell, ma restiamo comunque severi.
_RE_DOMAIN = re.compile(r"^(?=.{1,253}$)([a-zA-Z0-9](-?[a-zA-Z0-9])*\.)+[a-zA-Z]{2,63}$")
_RE_USER = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")
_RE_EMAIL = re.compile(r"^[A-Za-z0-9._%+\-]{1,64}@(?=.{1,253}$)([a-zA-Z0-9](-?[a-zA-Z0-9])*\.)+[a-zA-Z]{2,63}$")


def _valido(kind, target):
    if kind == "domain":
        return bool(_RE_DOMAIN.match(target))
    if kind == "username":
        return bool(_RE_USER.match(target))
    if kind == "email":
        return bool(_RE_EMAIL.match(target))
    if kind in ("host", "ip"):
        import ipaddress
        try:
            ipaddress.ip_address(target)
            return True
        except ValueError:
            return kind == "host" and bool(_RE_DOMAIN.match(target))
    return False


def _bin_of(entry):
    for b in entry["bins"]:
        p = shutil.which(b)
        if p:
            return b
    return None


# Come installare on-demand un tool recon mancante. La distro e' on-demand per
# scelta (non gonfia la live): questi tool NON sono preinstallati, ma stanno nel
# catalogo (repo.json) e si tirano al volo. 'dig' non e' un tool di catalogo:
# arriva dal pacchetto apk bind-tools.
INSTALL_TIMEOUT = 900  # pip/container possono metterci minuti


def _install_argv(tool):
    if tool == "dig":
        base = ["apk", "add", "--no-cache", "bind-tools"]
        if shutil.which("doas"):
            return ["doas"] + base
        if shutil.which("sudo"):
            return ["sudo"] + base
        return base
    # tutti gli altri sono in repo.json: li gestisce nxs-tool (apk/pip/container)
    if shutil.which("nxs-tool"):
        return ["nxs-tool", "install", tool]
    return None


# ---------------------------------------------------------------------------
# Rete
# ---------------------------------------------------------------------------
def _port_up(host, port, timeout=0.6):
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return True
    except OSError:
        return False


def _tor_up():
    return _port_up(TOR_HOST, TOR_PORT)


# PhoneInfoga: OSINT sui numeri di telefono, ha una REST API + web client.
# Nella distro e' un tool 'container' (repo.json) che si avvia con "serve" su
# :5000. HORUS lo avvia on-demand e lo mostra in un iframe.
PHONE_PORT = 5000


def _phone_start_argv():
    if shutil.which("nxs-tool"):
        return ["nxs-tool", "run", "phoneinfoga"]   # gestisce il container
    if shutil.which("phoneinfoga"):
        return ["phoneinfoga", "serve", "--no-open"]
    return None


def _capture_screen():
    """Cattura lo schermo (scrot) e ritorna i byte PNG; b'' se non disponibile.

    Serve al pulsante 'Aggiungi schermata' del Report: allega al dossier cio' che
    l'analista sta vedendo (mappa + pannelli), utile come prova nel PDF/ZIP."""
    scrot = shutil.which("scrot")
    if not scrot:
        return b""
    fd, tmp = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        subprocess.run([scrot, "-o", tmp], timeout=15,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(tmp, "rb") as f:
            return f.read()
    except (OSError, subprocess.SubprocessError):
        return b""
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _opener():
    """Opener urllib: via Tor se disponibile e PySocks c'e', altrimenti diretto.

    In entrambi i casi le URL sono https:// (la cifratura non dipende da questo).
    """
    if _tor_up():
        try:
            import socks  # PySocks, opzionale
            from sockshandler import SocksiPyHandler
            return urllib.request.build_opener(
                SocksiPyHandler(socks.SOCKS5, TOR_HOST, TOR_PORT, rdns=True))
        except Exception:
            pass  # senza PySocks si esce diretti, ma sempre in HTTPS
    return urllib.request.build_opener()


def _fetch(url, headers=None, timeout=None):
    # Accept largo: alcune sorgenti (Digitraffic) servono application/geo+json e
    # rifiutano (406) un Accept troppo stretto.
    h = {"User-Agent": UA,
         "Accept": "application/json, application/geo+json, text/plain, */*"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with _opener().open(req, timeout=(timeout or TIMEOUT)) as r:
        raw = r.read()
        # Alcune sorgenti (Digitraffic) rispondono gzip; urllib non lo scompatta.
        if (r.headers.get("Content-Encoding", "") or "").lower() == "gzip":
            import gzip
            raw = gzip.decompress(raw)
        return json.loads(raw.decode("utf-8", "replace"))


def _eonet_to_geojson(data):
    """Normalizza gli eventi EONET (vulcani/incendi) in un FeatureCollection
    di punti: prende l'ULTIMA geometria di ogni evento (la piu' recente) e
    conserva piu' campi possibile per un fumetto ricco (data, fonte, entita')."""
    feats = []
    for ev in data.get("events", []):
        geoms = ev.get("geometry") or []
        if not geoms:
            continue
        g = geoms[-1]
        coords = g.get("coordinates")
        if not coords or g.get("type") != "Point":
            continue
        srcs = ev.get("sources") or []
        cats = ev.get("categories") or []
        mag = ""
        if g.get("magnitudeValue") is not None:
            mag = "%s %s" % (g.get("magnitudeValue"), g.get("magnitudeUnit") or "")
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": coords[:2]},
            "properties": {
                "name": ev.get("title", ""),
                "date": g.get("date", ""),
                "category": cats[0].get("title", "") if cats else "",
                "magnitude": mag,
                "source": srcs[0].get("url", "") if srcs else "",
                "link": ev.get("link", ""),
            },
        })
    return {"type": "FeatureCollection", "features": feats}


def _gvp_to_geojson(data):
    """Normalizza i vulcani Smithsonian GVP in punti con un fumetto ricco."""
    feats = []
    for f in data.get("features", []):
        p = f.get("properties") or {}
        geom = f.get("geometry")
        lat, lon = p.get("Latitude"), p.get("Longitude")
        if not geom and lat is not None and lon is not None:
            geom = {"type": "Point", "coordinates": [lon, lat]}
        if not geom:
            continue
        num = p.get("Volcano_Number")
        summ = (p.get("Geological_Summary") or "")
        if len(summ) > 320:
            summ = summ[:320] + "..."
        feats.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "name": p.get("Volcano_Name", "Vulcano"),
                "type": p.get("Primary_Volcano_Type", ""),
                "last": p.get("Last_Eruption_Year", ""),
                "country": p.get("Country", ""),
                "region": p.get("Region", ""),
                "elevation": p.get("Elevation", ""),
                "rock": p.get("Major_Rock_Type", ""),
                "summary": summ,
                "photo": p.get("Primary_Photo_Link", ""),
                "link": ("https://volcano.si.edu/volcano.cfm?vn=%s" % num) if num else "",
            },
        })
    return {"type": "FeatureCollection", "features": feats}


_CAMS = {"ts": 0, "data": None}
# Distretti Caltrans piu' densi (California): Bay Area (4), Los Angeles (7),
# San Diego (11). Tetti per rete: tante telecamere = tanti marker, e l'ambiente
# WebKit della distro rende in software; teniamo il totale gestibile.
_CALTRANS_DISTRICTS = (4, 7, 11)
_CAM_CAP = {"tfl": 300, "caltrans": 300, "ontario": 200, "finland": 260, "nz": 220}


def _cam_feat(lat, lon, title, network, image, url, view, video=""):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
        "properties": {"title": title or "Telecamera", "network": network,
                       "image": image, "url": url or image, "view": view or "",
                       "video": video or ""},
    }


def _cameras_official():
    """Telecamere del traffico da enti PUBBLICI ufficiali, tutte KEYLESS e con
    immagine in diretta (si aggiorna di continuo). Stesso approccio di OSIRIS:
    reti reali di sorveglianza stradale, non webcam turistiche. Cache 5 min:
    l'elenco (posizioni/URL) cambia lento, l'immagine invece e' sempre fresca."""
    now = time.time()
    if _CAMS["data"] and now - _CAMS["ts"] < 300:
        return _CAMS["data"]
    feats = []
    # TfL JamCams - Transport for London (Regno Unito). imageUrl = JPEG diretto.
    try:
        arr = _fetch("https://api.tfl.gov.uk/Place/Type/JamCam")
        cnt = 0
        for c in arr:
            lat, lon = c.get("lat"), c.get("lon")
            if lat is None or lon is None:
                continue
            ap = {a.get("key"): a.get("value")
                  for a in (c.get("additionalProperties") or [])}
            img = ap.get("imageUrl")
            if not img or str(ap.get("available", "true")).lower() == "false":
                continue
            # TfL fornisce anche una clip MP4 breve: la mostriamo animata.
            vid = ap.get("videoUrl", "")
            feats.append(_cam_feat(lat, lon, c.get("commonName", ""),
                                   "TfL · Londra", img,
                                   vid or img, ap.get("view", ""), vid))
            cnt += 1
            if cnt >= _CAM_CAP["tfl"]:
                break
    except Exception:
        pass
    # Caltrans - California DOT: piu' distretti, currentImageURL = JPEG diretto.
    ct = 0
    for d in _CALTRANS_DISTRICTS:
        try:
            data = _fetch("https://cwwp2.dot.ca.gov/data/d%d/cctv/cctvStatusD%02d.json"
                          % (d, d))
        except Exception:
            continue
        for row in data.get("data", []):
            c = row.get("cctv") or {}
            loc = c.get("location") or {}
            lat, lon = loc.get("latitude"), loc.get("longitude")
            img = ((c.get("imageData") or {}).get("static") or {}).get("currentImageURL")
            if not img or lat in (None, "") or lon in (None, ""):
                continue
            if str(c.get("inService", "true")).lower() == "false":
                continue
            try:
                feats.append(_cam_feat(lat, lon, loc.get("locationName", ""),
                                       "Caltrans · California", img, img,
                                       loc.get("route", "")))
            except (TypeError, ValueError):
                continue
            ct += 1
            if ct >= _CAM_CAP["caltrans"]:
                break
        if ct >= _CAM_CAP["caltrans"]:
            break
    # Ontario 511 - Ministero dei Trasporti dell'Ontario (Canada). La Url della
    # "View" e' gia' un JPEG diretto.
    try:
        arr = _fetch("https://511on.ca/api/v2/get/cameras")
        cnt = 0
        for c in arr:
            lat, lon = c.get("Latitude"), c.get("Longitude")
            if lat is None or lon is None:
                continue
            v = None
            for x in (c.get("Views") or []):
                if str(x.get("Status", "")).lower() == "enabled" and x.get("Url"):
                    v = x
                    break
            if not v:
                continue
            feats.append(_cam_feat(lat, lon, c.get("Location", ""),
                                   "Ontario 511 · Canada", v.get("Url"),
                                   v.get("Url"), v.get("Description", "")))
            cnt += 1
            if cnt >= _CAM_CAP["ontario"]:
                break
    except Exception:
        pass
    # Digitraffic - Finlandia (Europa del Nord). L'immagine di ogni "preset" e'
    # a https://weathercam.digitraffic.fi/{presetId}.jpg (gia' ricavabile
    # dall'elenco stazioni, senza chiamate per-stazione).
    try:
        data = _fetch("https://tie.digitraffic.fi/api/weathercam/v1/stations",
                      headers={"Accept-Encoding": "gzip"})
        cnt = 0
        for f in data.get("features", []):
            geom = f.get("geometry") or {}
            coord = geom.get("coordinates") or []
            if len(coord) < 2:
                continue
            props = f.get("properties") or {}
            preset = None
            for pr in (props.get("presets") or []):
                if pr.get("inCollection") and pr.get("id"):
                    preset = pr
                    break
            if not preset:
                continue
            img = "https://weathercam.digitraffic.fi/%s.jpg" % preset["id"]
            feats.append(_cam_feat(coord[1], coord[0], props.get("name", ""),
                                   "Digitraffic · Finlandia", img, img, ""))
            cnt += 1
            if cnt >= _CAM_CAP["finland"]:
                break
    except Exception:
        pass
    # NZTA - Nuova Zelanda (Oceania). Elenco XML; imageUrl relativo.
    try:
        import xml.etree.ElementTree as ET
        req = urllib.request.Request(
            "https://trafficnz.info/service/traffic/rest/4/cameras/all",
            headers={"User-Agent": UA, "Accept": "application/xml"})
        with _opener().open(req, timeout=TIMEOUT) as r:
            root = ET.fromstring(r.read())
        cnt = 0
        for c in root.findall(".//camera"):
            def _t(tag):
                e = c.find(tag)
                return e.text if e is not None else None
            if (_t("offline") or "").lower() == "true":
                continue
            lat, lon, iu = _t("latitude"), _t("longitude"), _t("imageUrl")
            if not lat or not lon or not iu:
                continue
            img = iu if iu.startswith("http") else ("https://trafficnz.info" + iu)
            feats.append(_cam_feat(lat, lon, _t("description") or _t("name") or "",
                                   "NZTA · Nuova Zelanda", img, img,
                                   _t("direction") or ""))
            cnt += 1
            if cnt >= _CAM_CAP["nz"]:
                break
    except Exception:
        pass
    fc = {"type": "FeatureCollection", "features": feats}
    _CAMS["data"] = fc
    _CAMS["ts"] = now
    return fc


_CONF_DIR = Path.home() / ".config" / "nxs"


def _read_conf_text(name):
    try:
        return (_CONF_DIR / name).read_text()
    except OSError:
        return ""


def _settings_status():
    """Stato delle impostazioni. NON restituisce MAI il valore delle chiavi,
    solo se sono presenti (le chiavi non lasciano il computer)."""
    return {
        "aisstream": bool(_aisstream_key()),
        "ais_premium": bool(_read_conf_text("ais-premium.key").strip()),
        "news_feeds": _read_conf_text("news-feeds.txt"),
        "news_engine": _news_engine(),
    }


def _save_settings(body):
    """Salva le chiavi/feed dell'UTENTE in ~/.config/nxs (solo su questa
    macchina, mai nella distro). Campo assente = non toccare; stringa vuota =
    cancella. Le chiavi sono file 0600."""
    _CONF_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for field, fname in (("aisstream_key", "aisstream.key"),
                         ("ais_premium_key", "ais-premium.key")):
        if field not in body:
            continue
        val = (body.get(field) or "").strip()
        p = _CONF_DIR / fname
        if val:
            p.write_text(val)
            try:
                os.chmod(p, 0o600)
            except OSError:
                pass
            written.append(fname)
        else:
            try:
                p.unlink()
            except OSError:
                pass
    if "news_feeds" in body:
        (_CONF_DIR / "news-feeds.txt").write_text(body.get("news_feeds") or "")
        written.append("news-feeds.txt")
    if "news_engine" in body:
        v = (body.get("news_engine") or "").strip().lower()
        if v not in ("google", "duckduckgo", "both"):
            v = "both"
        (_CONF_DIR / "news-engine.txt").write_text(v + "\n")
        written.append("news-engine.txt")
    if "news_sources" in body:
        ids = body.get("news_sources") or []
        valid = [c["id"] for c in NEWS_CATALOG]
        chosen = [i for i in ids if i in valid]
        # Scriviamo sempre (anche vuoto, con intestazione) per rispettare una
        # selezione esplicita di "nessuna fonte del catalogo".
        (_CONF_DIR / "news-sources.txt").write_text(
            "# fonti news attive (id)\n" + "\n".join(chosen) + "\n")
        written.append("news-sources.txt")
    return {"ok": True, "written": written}


_TLE = {"ts": 0, "data": None, "try": 0}
_TLE_LOCK = threading.Lock()
# Gruppi CelesTrak (keyless) utili e non enormi. NB: Starlink e' escluso di
# proposito (~6000 satelliti = troppi marker e troppa CPU di propagazione).
_TLE_GROUPS = ["stations", "gps-ops", "galileo", "glo-ops", "beidou",
               "weather", "noaa", "goes", "science", "geo"]


def _tle_load_file():
    try:
        d = json.loads((_CONF_DIR / "tle-cache.json").read_text())
        return d.get("sats") or []
    except Exception:
        return []


def _tle_save_file(sats):
    try:
        _CONF_DIR.mkdir(parents=True, exist_ok=True)
        (_CONF_DIR / "tle-cache.json").write_text(
            json.dumps({"ts": time.time(), "sats": sats}))
    except OSError:
        pass


def _tle():
    """Elementi orbitali (TLE) da CelesTrak, per calcolare le posizioni dei
    satelliti nel BROWSER (satellite.js). Cache 2h in memoria + cache su FILE
    (~/.config/nxs/tle-cache.json): se CelesTrak fa 503/rate-limit serviamo
    comunque l'ultima buona (i TLE degradano lenti). Lock NON bloccante: se un
    altro thread sta gia' scaricando, rispondiamo subito con quel che c'e'."""
    now = time.time()
    if _TLE["data"] and now - _TLE["ts"] < 7200:
        return _TLE["data"]
    if not _TLE_LOCK.acquire(blocking=False):
        return _TLE["data"] or _tle_load_file()
    try:
        now = time.time()
        if _TLE["data"] and now - _TLE["ts"] < 7200:
            return _TLE["data"]
        # Backoff: dopo un fallimento non martelliamo CelesTrak per 60s.
        if not _TLE["data"] and now - _TLE["try"] < 60:
            return _TLE["data"] or _tle_load_file()
        _TLE["try"] = now
        out = _tle_fetch()
        if out:
            _TLE["data"] = out
            _TLE["ts"] = time.time()
            _tle_save_file(out)
            return out
        # Rete non collabora: ripieghiamo sull'ultima cache su file (stantia ok).
        return _TLE["data"] or _tle_load_file()
    finally:
        _TLE_LOCK.release()


def _tle_fetch():
    out = []
    for g in _TLE_GROUPS:
        try:
            req = urllib.request.Request(
                "https://celestrak.org/NORAD/elements/gp.php?GROUP=%s&FORMAT=tle" % g,
                headers={"User-Agent": UA})
            with _opener().open(req, timeout=8) as r:   # timeout corto: no attese lunghe
                txt = r.read().decode("utf-8", "replace")
        except Exception:
            continue   # 503/timeout: salta questo gruppo
        lines = [l.rstrip() for l in txt.splitlines() if l.strip()]
        for i in range(0, len(lines) - 2, 3):
            name, l1, l2 = lines[i].strip(), lines[i + 1], lines[i + 2]
            if l1.startswith("1 ") and l2.startswith("2 "):
                out.append({"name": name, "l1": l1, "l2": l2, "group": g})
        time.sleep(0.25)   # gentile con CelesTrak (attenua i 503)
        if len(out) >= 900:
            break
    return out


def _resolve(target):
    """Restituisce l'IP di un target (IP o dominio), o None."""
    import ipaddress
    try:
        ipaddress.ip_address(target)
        return target
    except ValueError:
        pass
    try:
        return socket.getaddrinfo(target, None)[0][4][0]
    except (OSError, IndexError):
        return None


def _geoint(target):
    """Geolocalizza un IP/dominio (ipwho.is) e ne prende porte/CVE/hostname
    da Shodan InternetDB. Tutto keyless, HTTPS, instradabile via Tor."""
    ip = _resolve(target)
    if not ip:
        return {"error": "non risolvo '%s'" % target}
    out = {"target": target, "ip": ip}
    try:
        g = _fetch("https://ipwho.is/" + ip)
        if g.get("success"):
            conn = g.get("connection") or {}
            out.update({
                "lat": g.get("latitude"), "lon": g.get("longitude"),
                "city": g.get("city"), "region": g.get("region"),
                "country": g.get("country"), "flag": (g.get("flag") or {}).get("emoji"),
                "org": conn.get("org"), "isp": conn.get("isp"),
                "asn": conn.get("asn"), "domain": conn.get("domain"),
            })
        else:
            out["geo_error"] = g.get("message", "geolocalizzazione fallita")
    except Exception as e:
        out["geo_error"] = str(e)
    try:
        s = _fetch("https://internetdb.shodan.io/" + ip)
        # InternetDB risponde 404 (via urllib -> eccezione) se non ha dati.
        out["ports"] = s.get("ports", [])
        out["vulns"] = s.get("vulns", [])
        out["hostnames"] = s.get("hostnames", [])
        out["tags"] = s.get("tags", [])
        out["cpes"] = s.get("cpes", [])
    except Exception:
        out["ports"] = []
        out["shodan_note"] = "nessun dato Shodan per questo IP"
    return out


def _area(lamin, lomin, lamax, lomax):
    """Voli (OpenSky bbox) e terremoti (USGS bbox, 24h) in un riquadro."""
    res = {}
    try:
        res["flights"] = _fetch(
            "https://opensky-network.org/api/states/all"
            "?lamin=%s&lomin=%s&lamax=%s&lomax=%s" % (lamin, lomin, lamax, lomax))
    except Exception as e:
        res["flights"] = {"states": [], "error": str(e)}
    try:
        res["quakes"] = _fetch(
            "https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson"
            "&minlatitude=%s&maxlatitude=%s&minlongitude=%s&maxlongitude=%s"
            "&starttime=%s" % (lamin, lamax, lomin, lomax,
                               time.strftime("%Y-%m-%d", time.gmtime(time.time() - 86400))))
    except Exception as e:
        res["quakes"] = {"features": [], "error": str(e)}
    return res


_TYPE_LABEL = {
    "geoint": "GEOINT", "recon": "Ricognizione", "socmint": "SOCMINT",
    "email": "Email", "correlazione": "Correlazione", "area": "Area",
    "exif": "Metadati foto", "nota": "Nota",
}


def _leaflet_inline():
    """Legge Leaflet vendored per incorporarlo nel report (mappa offline-first:
    online mostra le tile OSM, offline i marcatori restano posizionati corretti).
    Ritorna (css, js) o (None, None) se non disponibile."""
    base = WEB / "vendor" / "leaflet"
    try:
        css = (base / "leaflet.css").read_text(encoding="utf-8")
        js = (base / "leaflet.js").read_text(encoding="utf-8")
        return css, js
    except Exception:
        return None, None


def _reports_dir():
    return Path.home() / "NexusSec-loot" / "horus"


def _list_reports():
    """Elenca i dossier salvati (.html) nella loot, dal piu' recente, con la
    presenza della copia JSON accanto e il titolo estratto dall'HTML."""
    d = _reports_dir()
    out = []
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.html"), key=lambda x: x.stat().st_mtime, reverse=True):
        title = ""
        try:
            head = p.read_text(encoding="utf-8", errors="ignore")[:4000]
            m = re.search(r"<b>Indagine:</b>\s*([^<]+)", head)
            if m:
                # il titolo nell'HTML e' escaped: lo riporto in testo grezzo,
                # cosi' il client lo ri-escape una sola volta.
                title = (m.group(1).strip()
                         .replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">"))
        except Exception:
            pass
        st = p.stat()
        jp = d / (p.stem + ".json")
        n_entries = None
        if jp.is_file():
            try:
                n_entries = len(json.loads(jp.read_text(encoding="utf-8")).get("entries") or [])
            except Exception:
                n_entries = None
        out.append({
            "name": p.name, "id": p.stem, "title": title, "size": st.st_size,
            "mtime": int(st.st_mtime), "entries": n_entries,
            "json": jp.is_file(),
            "demo": p.name.startswith("DEMO"),
        })
    return out


def _serve_report_file(handler, name, download=False):
    """Serve un file dossier dalla loot in modo sicuro (solo basename, solo
    .html/.json, risolto DENTRO la cartella loot)."""
    base = _reports_dir().resolve()
    safe = Path(name).name                      # scarta ogni componente di path
    p = (base / safe).resolve()
    if not str(p).startswith(str(base)) or p.suffix not in (".html", ".json") or not p.is_file():
        handler.send_error(404)
        return
    data = p.read_bytes()
    ctype = "text/html; charset=utf-8" if p.suffix == ".html" else "application/json"
    handler.send_response(200)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(len(data)))
    if download:
        handler.send_header("Content-Disposition", 'attachment; filename="%s"' % safe)
    handler.send_header("Cache-Control", "no-cache, must-revalidate")
    handler.end_headers()
    handler.wfile.write(data)


def _delete_report(name):
    """Elimina un fascicolo (html + json) dalla loot in sicurezza. Ritorna il
    numero di file rimossi."""
    base = _reports_dir().resolve()
    stem = Path(Path(name).name).stem            # solo basename, senza estensione
    if not stem:
        return 0
    removed = 0
    for ext in (".html", ".json"):
        p = (base / (stem + ext)).resolve()
        if str(p).startswith(str(base)) and p.is_file():
            try:
                p.unlink(); removed += 1
            except OSError:
                pass
    return removed


def _save_report(meta):
    """Scrive un dossier d'indagine come report HTML autonomo + copia JSON in
    ~/NexusSec-loot/horus/. `meta` = {title, operator, objective, via, entries}.

    Il report contiene: intestazione con metadati del caso, barra statistiche
    (conteggi per tipo), obiettivo, mini-mappa Leaflet coi punti geolocalizzati,
    tabella coordinate, timeline ordinata e sezioni raggruppate per tipo, con
    per ogni voce provenienza (Tor/IP), obiettivo dello scan, coordinate e tag."""
    if isinstance(meta, list):            # retrocompat: vecchio payload = lista
        meta = {"entries": meta}
    entries = meta.get("entries") or []
    case_title = (meta.get("title") or "").strip() or "Indagine senza titolo"
    operator = (meta.get("operator") or "").strip() or "n/d"
    objective = (meta.get("objective") or "").strip()
    via = (meta.get("via") or "").strip() or "n/d"

    d = Path.home() / "NexusSec-loot" / "horus"
    d.mkdir(parents=True, exist_ok=True)
    # Identita' del fascicolo: se il client passa un case_id (fascicolo gia'
    # esistente) si RISCRIVONO gli stessi file (continuazione dell'indagine);
    # altrimenti se ne conia uno nuovo, univoco. Il case_id e' il nome-base.
    raw_id = (meta.get("case_id") or "").strip()
    case_id = re.sub(r"[^A-Za-z0-9_-]", "", raw_id)[:64]
    if not case_id:
        ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        case_id = "caso-" + ts
        n = 1
        while (d / (case_id + ".html")).exists():
            n += 1
            case_id = "caso-%s-%d" % (ts, n)
    path = d / (case_id + ".html")
    jpath = d / (case_id + ".json")

    # Copia JSON grezza (interoperabile, re-importabile, per pipeline esterne).
    jpath.write_text(json.dumps({
        "tool": "HORUS", "format": "horus-dossier", "version": 1,
        "case_id": case_id,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "title": case_title, "operator": operator,
        "objective": objective, "scan_via": via, "entries": entries,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    def esc(s):
        return (str(s).replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;"))

    # --- Statistiche per tipo ---
    counts = {}
    geo_pts = []
    for e in entries:
        t = e.get("type", "?")
        counts[t] = counts.get(t, 0) + 1
        lat, lon = e.get("lat"), e.get("lon")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            geo_pts.append({"lat": lat, "lon": lon,
                            "title": e.get("title", ""),
                            "type": _TYPE_LABEL.get(t, t)})
    chips = ["<span class='chip tot'>%d voci</span>" % len(entries)]
    for t, n in counts.items():
        chips.append("<span class='chip'>%s: %d</span>" % (esc(_TYPE_LABEL.get(t, t)), n))
    if geo_pts:
        chips.append("<span class='chip geo'>&#128205; %d su mappa</span>" % len(geo_pts))

    # --- Mini-mappa Leaflet incorporata (solo se ci sono coordinate) ---
    map_html = ""
    css, js = _leaflet_inline()
    if geo_pts and css and js:
        pts_json = json.dumps(geo_pts, ensure_ascii=False)
        map_html = (
            "<h2>Mappa situazionale</h2>"
            "<div id='map' style='height:420px;border:1px solid #1a3a52;border-radius:8px'></div>"
            "<style>%s</style><script>%s</script>"
            "<script>(function(){var P=%s;"
            "var m=L.map('map',{attributionControl:false});"
            "try{L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}',{maxZoom:16}).addTo(m);}catch(e){}"
            "var g=[];P.forEach(function(p){var mk=L.circleMarker([p.lat,p.lon],"
            "{radius:6,color:'#00e5ff',weight:2,fillColor:'#00e5ff',fillOpacity:.6})"
            ".bindPopup('<b>'+p.type+'</b><br>'+p.title+'<br>'+p.lat.toFixed(4)+', '+p.lon.toFixed(4));"
            "mk.addTo(m);g.push([p.lat,p.lon]);});"
            "if(g.length===1){m.setView(g[0],6);}else{m.fitBounds(g,{padding:[30,30]});}"
            "})();</script>" % (css, js, pts_json))

    # --- Tabella coordinate (offline-safe, con link OSM) ---
    coord_html = ""
    if geo_pts:
        crows = []
        for p in geo_pts:
            osm = "https://www.openstreetmap.org/?mlat=%s&mlon=%s#map=8/%s/%s" % (
                p["lat"], p["lon"], p["lat"], p["lon"])
            crows.append("<tr><td>%s</td><td>%s</td><td class='mono'>%.5f, %.5f</td>"
                         "<td><a href='%s'>OSM</a></td></tr>" % (
                             esc(p["type"]), esc(p["title"]), p["lat"], p["lon"], esc(osm)))
        coord_html = ("<h2>Coordinate</h2><table class='tbl'><thead><tr>"
                      "<th>Tipo</th><th>Voce</th><th>Lat, Lon</th><th></th></tr></thead>"
                      "<tbody>%s</tbody></table>" % "".join(crows))

    # --- Timeline (ordinata per istante) ---
    def _key(e):
        return e.get("iso") or e.get("time") or ""
    tl = sorted(entries, key=_key)
    tl_rows = []
    for e in tl:
        tl_rows.append("<li><span class='tl-t'>%s</span> "
                       "<span class='tl-k'>%s</span> %s</li>" % (
                           esc(e.get("time", "")),
                           esc(_TYPE_LABEL.get(e.get("type"), e.get("type", ""))),
                           esc(e.get("title", ""))))
    timeline_html = ("<h2>Timeline</h2><ol class='tl'>%s</ol>" % "".join(tl_rows)) if tl_rows else ""

    # --- Grafo relazioni (SVG gia' renderizzato dal client) ---
    graph_html = ""
    gsvg = (meta.get("graph_svg") or "").strip()
    # Sanita' minima: accettiamo solo un <svg>...</svg> (niente script/foreign).
    if gsvg.startswith("<svg") and "</svg>" in gsvg and "<script" not in gsvg.lower():
        graph_html = ("<h2>Grafo relazioni</h2>"
                      "<p class='ghint'>Nodi = entità del dossier; archi = legami "
                      "dedotti (identificatore condiviso, vicinanza geografica, "
                      "finestra temporale).</p>"
                      "<div class='gwrap'>%s</div>" % gsvg)

    # --- Sezioni raggruppate per tipo ---
    sect = []
    for t in counts:
        items = [e for e in entries if e.get("type") == t]
        sect.append("<h2>%s <small>(%d)</small></h2>" % (esc(_TYPE_LABEL.get(t, t)), len(items)))
        for e in items:
            badges = ["<span class='b'>%s</span>" % esc(e.get("via", ""))]
            if e.get("target"):
                badges.append("<span class='b'>obiettivo: %s</span>" % esc(e["target"]))
            if e.get("lat") is not None:
                badges.append("<span class='b geo'>&#128205; %.4f, %.4f</span>" % (e["lat"], e["lon"]))
            for tag in (e.get("tags") or [])[:6]:
                badges.append("<span class='tag'>%s</span>" % esc(tag))
            sect.append(
                "<section class='e'><h3>%s</h3>"
                "<div class='badges'>%s</div>"
                "<div class='t'>%s</div><pre>%s</pre></section>" % (
                    esc(e.get("title", "")), " ".join(badges),
                    esc(e.get("time", "")), esc(e.get("detail", ""))))

    gen = time.strftime("%Y-%m-%d %H:%M", time.gmtime())
    html = (
        "<!DOCTYPE html><html lang='it'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>HORUS - %s</title><style>"
        "body{background:#050a14;color:#c8f5ff;font-family:system-ui,sans-serif;"
        "max-width:960px;margin:0 auto;padding:24px;line-height:1.5}"
        "h1{color:#00e5ff;letter-spacing:3px;margin:0}"
        "h2{color:#00e5ff;border-bottom:1px solid #1a3a52;padding-bottom:4px;margin-top:28px;font-size:16px}"
        "h3{margin:0 0 6px;font-size:14px}small{color:#5a8a9a;font-weight:normal}"
        ".head{border:1px solid #1a3a52;border-radius:10px;padding:16px 18px;margin:12px 0;background:#0a1a26}"
        ".kv{color:#5a8a9a;font-size:13px;margin:2px 0}.kv b{color:#c8f5ff;font-weight:600}"
        ".chips{margin:12px 0}.chip{display:inline-block;background:#0a1a26;border:1px solid #1a3a52;"
        "border-radius:20px;padding:3px 11px;margin:3px;font-size:12px;color:#c8f5ff}"
        ".chip.tot{border-color:#00e5ff;color:#00e5ff}.chip.geo{border-color:#ff5a8a;color:#ff5a8a}"
        ".obj{background:#030710;border-left:3px solid #00e5ff;padding:8px 12px;border-radius:4px;margin:10px 0}"
        ".e{border:1px solid #1a3a52;border-radius:8px;padding:12px 16px;margin:12px 0;background:#0a1a26}"
        ".t{color:#5a8a9a;font-size:12px;margin:6px 0}"
        ".badges{margin:2px 0 6px}.b{display:inline-block;background:#030710;border:1px solid #1a3a52;"
        "border-radius:5px;padding:1px 7px;margin:2px 3px 2px 0;font-size:11px;color:#5a8a9a}"
        ".b.geo{color:#ff5a8a;border-color:#3a2030}.tag{display:inline-block;background:#08202c;"
        "border-radius:5px;padding:1px 7px;margin:2px 3px 2px 0;font-size:11px;color:#00e5ff}"
        "pre{white-space:pre-wrap;word-break:break-word;background:#030710;border:1px solid #1a3a52;"
        "border-radius:6px;padding:10px;font-size:12px;color:#c8f5ff;overflow-x:auto}"
        ".tbl{width:100%%;border-collapse:collapse;font-size:12px}"
        ".tbl th,.tbl td{border:1px solid #1a3a52;padding:5px 8px;text-align:left}"
        ".tbl th{color:#5a8a9a;background:#0a1a26}.mono{font-family:monospace}"
        ".tbl a{color:#00e5ff}.tl{font-size:13px;padding-left:18px}"
        ".tl-t{color:#5a8a9a;font-size:11px}.tl-k{color:#00e5ff}"
        ".ghint{color:#5a8a9a;font-size:12px;margin:2px 0 8px}"
        ".gwrap{border:1px solid #1a3a52;border-radius:8px;background:#030710;padding:6px;overflow:auto}"
        ".gwrap svg{max-width:100%%;height:auto;display:block;margin:0 auto}"
        "footer{color:#5a8a9a;font-size:11px;margin-top:26px;border-top:1px solid #1a3a52;padding-top:10px}"
        "a{color:#00e5ff}"
        "</style></head><body>"
        "<h1>HORUS</h1><p style='color:#5a8a9a;margin:2px 0 0'>Dossier d'indagine OSINT / GEOINT</p>"
        "<div class='head'>"
        "<div class='kv'><b>Indagine:</b> %s</div>"
        "<div class='kv'><b>Analista:</b> %s</div>"
        "<div class='kv'><b>Generato:</b> %s UTC</div>"
        "<div class='kv'><b>Provenienza scan:</b> %s</div>"
        "</div>"
        "<div class='chips'>%s</div>"
        "%s"        # objective
        "%s"        # map
        "%s"        # graph
        "%s"        # coords
        "%s"        # timeline
        "<h2>Dettaglio voci</h2>%s"
        "<footer>Generato da HORUS &middot; NexusSec OS &middot; gli scan sono "
        "partiti da %s. Report autonomo: apribile offline (le tile mappa "
        "richiedono rete; i marcatori restano posizionati anche offline). "
        "Copia dati: %s</footer>"
        "</body></html>" % (
            esc(case_title), esc(case_title), esc(operator), gen, esc(via),
            "".join(chips),
            ("<h2>Obiettivo</h2><div class='obj'>%s</div>" % esc(objective)) if objective else "",
            map_html, graph_html, coord_html, timeline_html, "".join(sect),
            esc(via), esc(jpath.name)))
    path.write_text(html, encoding="utf-8")
    return str(path), str(jpath), case_id


def _online():
    for host in (("earthquake.usgs.gov", 443), ("1.1.1.1", 53)):
        try:
            s = socket.create_connection(host, timeout=1.2)
            s.close()
            return True
        except OSError:
            continue
    return False


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _chunk_text(text, cap=1800):
    """Spezza un testo in blocchi <= cap caratteri, tagliando su spazi/punti
    (l'endpoint di traduzione ha un limite pratico sulla query GET)."""
    text = text or ""
    if len(text) <= cap:
        return [text] if text else []
    out, s = [], text
    while len(s) > cap:
        cut = s.rfind(". ", 0, cap)
        if cut < cap // 2:
            cut = s.rfind(" ", 0, cap)
        if cut <= 0:
            cut = cap
        out.append(s[:cut + 1])
        s = s[cut + 1:]
    if s:
        out.append(s)
    return out


def _gtx_translate_one(text, tl="it"):
    """Traduce un testo con l'endpoint KEYLESS di Google, instradato dal proxy
    (Tor se disponibile, come i feed): non parte dal tuo IP piu' del resto.
    Best-effort: se fallisce, ritorna l'originale (mai peggio di com'era)."""
    if not text or not text.strip():
        return text
    out = []
    for ch in _chunk_text(text, 1800):
        url = ("https://translate.googleapis.com/translate_a/single"
               "?client=gtx&sl=auto&tl=" + quote(tl) + "&dt=t&q=" + quote(ch))
        try:
            data = _fetch(url)
            seg = "".join(s[0] for s in (data[0] or []) if s and s[0])
            out.append(seg or ch)
        except Exception:
            out.append(ch)
    return "".join(out)


def _translate(texts, tl="it"):
    """Traduce una lista di stringhe (titolo + paragrafi) in parallelo."""
    from concurrent.futures import ThreadPoolExecutor
    texts = [t if isinstance(t, str) else "" for t in (texts or [])][:150]
    if not texts:
        return []
    with ThreadPoolExecutor(max_workers=6) as ex:
        return list(ex.map(lambda t: _gtx_translate_one(t, tl), texts))


class Handler(BaseHTTPRequestHandler):
    server_version = "HORUS/1.0"

    def log_message(self, *a):
        pass  # niente rumore su stdout

    def handle_one_request(self):
        # Il client che chiude a meta' (cambia pagina, annulla un'immagine) fa
        # scoppiare BrokenPipe/ConnectionReset: e' normale, non sporchiamo il log.
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    # -- utilita' risposta --
    def _json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, rel):
        # Sicurezza: risolvi dentro WEB, niente path traversal.
        p = (WEB / rel).resolve()
        if not str(p).startswith(str(WEB)) or not p.is_file():
            self.send_error(404)
            return
        ctype = {
            ".html": "text/html; charset=utf-8", ".css": "text/css",
            ".js": "application/javascript", ".svg": "image/svg+xml",
            ".png": "image/png", ".json": "application/json",
        }.get(p.suffix, "application/octet-stream")
        data = p.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        # Niente cache "stantia": il browser rivalida sempre (evita di mostrare
        # una versione vecchia della UI dopo un aggiornamento).
        self.send_header("Cache-Control", "no-cache, must-revalidate")
        self.end_headers()
        self.wfile.write(data)

    # -- GET --
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/" or path == "":
            return self._file("index.html")
        if path == "/api/status":
            return self._json({"online": _online(), "tor": _tor_up()})
        if path == "/api/settings":
            return self._json(_settings_status())
        if path == "/api/phone/status":
            return self._json({"up": _port_up("127.0.0.1", PHONE_PORT),
                               "port": PHONE_PORT})
        if path == "/api/tle":
            try:
                return self._json({"sats": _tle()})
            except Exception as e:
                return self._json({"sats": [], "error": str(e)}, 502)
        if path == "/api/tools":
            out = []
            for tid, e in RECON.items():
                out.append({"id": tid, "nome": e["nome"], "kind": e["kind"],
                            "installed": _bin_of(e) is not None})
            return self._json(out)
        if path == "/api/news":
            q = parse_qs(urlparse(self.path).query)
            query = (q.get("q", ["world"])[0] or "world")
            df = (q.get("df", [""])[0] or "")
            if df not in ("d", "w", "m"):
                df = ""
            lang = (q.get("lang", ["it"])[0] or "it")
            if lang not in ("it", "en", "fr", "de", "es", "world"):
                lang = "it"
            try:
                return self._json(_news(query, df, lang))
            except Exception as e:
                return self._json({"error": "news non raggiungibili: %s" % e}, 502)
        if path == "/api/news-sources":
            return self._json({"sources": _news_sources_status()})
        if path == "/api/enrich":
            q = parse_qs(urlparse(self.path).query)
            kind = (q.get("type", [""])[0] or "").strip().lower()
            value = (q.get("value", [""])[0] or "").strip()
            try:
                return self._json(_enrich(kind, value))
            except Exception as e:
                return self._json({"error": "arricchimento fallito: %s" % e}, 502)
        if path == "/api/screenshot":
            png = _capture_screen()
            if not png:
                return self._json(
                    {"error": "scrot non disponibile o cattura fallita"}, 502)
            b64 = base64.b64encode(png).decode("ascii")
            return self._json({"png": "data:image/png;base64," + b64})
        if path == "/api/reports":
            return self._json({"reports": _list_reports()})
        if path == "/api/report/file":
            q = parse_qs(urlparse(self.path).query)
            name = q.get("name", [""])[0]
            dl = q.get("dl", ["0"])[0] == "1"
            return _serve_report_file(self, name, download=dl)
        if path == "/api/resolve":
            q = parse_qs(urlparse(self.path).query)
            u = q.get("url", [""])[0]
            if not u.startswith(("http://", "https://")):
                return self._json({"error": "url non valida"}, 400)
            try:
                return self._json(_resolve_article(u))
            except Exception as e:
                return self._json({"url": u, "embeddable": False, "error": str(e)})
        if path == "/api/read":
            q = parse_qs(urlparse(self.path).query)
            u = q.get("url", [""])[0]
            if not u.startswith(("http://", "https://")):
                return self._json({"error": "url non valida"}, 400)
            try:
                return self._json(_extract_article(u))
            except Exception as e:
                return self._json({"url": u, "paragraphs": [], "error": str(e)})
        if path == "/api/live":
            # Risolve la diretta YouTube in corso di un canale (ISS ecc.)
            q = parse_qs(urlparse(self.path).query)
            ch = q.get("ch", [""])[0]
            if not re.match(r"^[A-Za-z0-9_-]{10,40}$", ch):
                return self._json({"error": "canale non valido"}, 400)
            try:
                vid = _live_video_id(
                    "https://www.youtube.com/channel/" + ch + "/live")
                return self._json({"videoId": vid})
            except Exception as e:
                return self._json({"videoId": "", "error": str(e)})
        if path == "/api/area":
            q = parse_qs(urlparse(self.path).query)
            try:
                vals = [float(q[k][0]) for k in ("lamin", "lomin", "lamax", "lomax")]
            except (KeyError, ValueError):
                return self._json({"error": "parametri area mancanti"}, 400)
            return self._json(_area(*vals))
        if path.startswith("/api/feed/"):
            return self._feed(path[len("/api/feed/"):])
        if path == "/api/recorder":
            return self._json(recorder.status())
        if path == "/api/track/entities":
            return self._json({"entities": recorder.entities()})
        if path == "/api/track/range":
            q = parse_qs(urlparse(self.path).query)
            layer = q.get("layer", [""])[0]
            key = q.get("key", [""])[0]
            if not layer or not key:
                return self._json({"error": "parametri mancanti"}, 400)
            try:
                ft = int(q.get("from", ["0"])[0] or 0)
                to = q.get("to", [""])[0]
                tt = int(to) if to else None
            except ValueError:
                return self._json({"error": "intervallo non valido"}, 400)
            return self._json({"samples": recorder.range_(layer, key, ft, tt)})
        if path == "/api/track/export":
            return self._json(recorder.export_all())
        # statico
        return self._file(path.lstrip("/"))

    def _feed(self, fid):
        fd = FEEDS.get(fid)
        if not fd:
            return self._json({"error": "feed sconosciuto"}, 404)
        # Navi (AIS): UN solo layer. Con chiave aisstream -> AIS globale
        # (WebSocket); senza (o se aisstream e' giu') -> Digitraffic keyless
        # (solo Baltico/Nord EU). Cosi' l'utente vede sempre qualcosa.
        if fd["kind"] == "ships":
            key = _aisstream_key()
            if key:
                # Flusso CONTINUO: il thread AIS resta connesso e accumula. Qui
                # spostiamo il riquadro sottoscritto sulla vista corrente (zone
                # dense come Hormuz/Malacca si popolano) e restituiamo lo snapshot
                # istantaneo dello store. Il client accumula in IndexedDB.
                bbox = None
                q = parse_qs(urlparse(self.path).query)
                try:
                    bbox = tuple(float(q[k][0])
                                 for k in ("lamin", "lomin", "lamax", "lomax"))
                except (KeyError, ValueError):
                    bbox = None
                _AIS.ensure(key)
                # bbox None = sottoscrizione MONDIALE (default). Col riquadro la
                # vista globale mostrerebbe solo una frazione; il mondo intero
                # da' il massimo e lo store accumula nel tempo.
                _AIS.set_bbox(bbox)
                return self._json(_AIS.snapshot())
            # Senza chiave: AIS keyless Digitraffic (solo Nord Europa).
            try:
                data = _fetch(fd["url"], headers=dict(fd.get("headers") or {}))
            except Exception as e:
                return self._json({"error": "sorgente navi non raggiungibile: %s" % e}, 502)
            return self._json(_ships_geojson(data))

        # Telecamere: reti ufficiali del traffico (keyless), aggregate e cache.
        if fd["kind"] == "cameras":
            try:
                return self._json(_cameras_official())
            except Exception as e:
                return self._json({"error": "telecamere non raggiungibili: %s" % e}, 502)

        url = fd["url"]
        headers = dict(fd.get("headers") or {})
        if fd["kind"] == "gvp":
            # "attivi" = ultima eruzione negli ultimi ~3 anni (include gli attuali).
            url = url.format(year=time.gmtime().tm_year - 3)
        try:
            data = _fetch(url, headers=headers)
        except Exception as e:
            return self._json({"error": "sorgente non raggiungibile: %s" % e}, 502)
        if fd["kind"] == "eonet":
            data = _eonet_to_geojson(data)
        elif fd["kind"] == "gvp":
            data = _gvp_to_geojson(data)
        return self._json(data)

    # -- POST --
    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path not in ("/api/recon", "/api/recon/install", "/api/phone/start",
                        "/api/geoint", "/api/report", "/api/settings", "/api/exif",
                        "/api/socmint", "/api/email", "/api/recorder",
                        "/api/recorder/follow", "/api/track/import",
                        "/api/translate", "/api/report/delete"):
            return self.send_error(404)
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except (ValueError, json.JSONDecodeError):
            return self._json({"error": "richiesta non valida"}, 400)
        if path == "/api/settings":
            return self._json(_save_settings(body))
        if path == "/api/recorder":
            # Attiva/disattiva il recorder di background e ne regola i parametri.
            enabled = body.get("enabled")
            recorder.set_config(enabled=enabled,
                                hours=body.get("hours"),
                                interval=body.get("interval"))
            if enabled is True:
                recorder.start_detached()   # processo staccato: sopravvive alla finestra
            elif enabled is False:
                recorder.stop()             # il daemon esce al giro successivo
            return self._json(recorder.status())
        if path == "/api/recorder/follow":
            layer = (body.get("layer") or "").strip()
            key = str(body.get("key") or "").strip()
            if layer not in ("ships", "flights") or not key:
                return self._json({"error": "entita' non seguibile"}, 400)
            if body.get("op") == "del":
                recorder.follow_del(layer, key)
            else:
                recorder.follow_add(layer, key, (body.get("name") or "").strip())
            return self._json(recorder.status())
        if path == "/api/track/import":
            n = recorder.import_merge(body.get("samples") or [],
                                      recorder.load_cfg().get("hours"))
            return self._json({"imported": n})
        if path == "/api/translate":
            q = body.get("q") or []
            if not isinstance(q, list) or not q:
                return self._json({"error": "niente da tradurre"}, 400)
            tl = (body.get("tl") or "it").strip()[:5] or "it"
            try:
                return self._json({"t": _translate(q, tl)})
            except Exception as e:
                return self._json({"error": "traduzione non riuscita: %s" % e}, 502)
        if path == "/api/socmint":
            u = (body.get("username", "") or "").strip()
            if not u:
                return self._json({"error": "inserisci uno username"}, 400)
            return self._json(_socmint(u))
        if path == "/api/email":
            em = (body.get("email", "") or "").strip()
            if not em:
                return self._json({"error": "inserisci un'email"}, 400)
            return self._json(_email_intel(em))
        if path == "/api/exif":
            url = (body.get("url", "") or "").strip()
            if url:                       # foto presa da un link (anche social)
                if not url.startswith(("http://", "https://")):
                    return self._json({"error": "url non valida"}, 400)
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": UA})
                    with _opener().open(req, timeout=TIMEOUT) as r:
                        ct = (r.headers.get("Content-Type", "") or "").lower()
                        raw = r.read(40 * 1024 * 1024 + 1)
                except Exception as e:
                    return self._json({"error": "scaricamento: %s" % e}, 400)
                if not ct.startswith("image/"):
                    return self._json({"error": "l'URL non punta a un'immagine "
                        "diretta: apri il post, poi copia l'indirizzo dell'immagine "
                        "(tasto destro sulla foto)"}, 400)
                name = url.split("?", 1)[0].rstrip("/").split("/")[-1][:120] or "foto"
                out = _exif_extract(raw, name)
                out["url"] = url
                return self._json(out)
            b64 = body.get("data", "")
            if not b64:
                return self._json({"error": "nessuna immagine"}, 400)
            try:
                raw = base64.b64decode(b64.split(",", 1)[-1])
            except ValueError:
                return self._json({"error": "immagine non valida"}, 400)
            if len(raw) > 40 * 1024 * 1024:
                return self._json({"error": "immagine troppo grande (max 40MB)"}, 400)
            return self._json(_exif_extract(raw, (body.get("name", "") or "foto")[:120]))
        if path == "/api/phone/start":
            return self._phone_start()
        if path == "/api/geoint":
            target = (body.get("target", "") or "").strip()
            if not _valido("host", target):
                return self._json({"error": "inserisci un IP o un dominio valido"}, 400)
            return self._json(_geoint(target))
        if path == "/api/report":
            entries = body.get("entries") or []
            if not entries:
                return self._json({"error": "niente da salvare"}, 400)
            try:
                html_p, json_p, case_id = _save_report(body)
                return self._json({"path": html_p, "json": json_p, "case_id": case_id})
            except OSError as e:
                return self._json({"error": "salvataggio: %s" % e}, 500)
        if path == "/api/report/delete":
            name = (body.get("name") or "").strip()
            if not name:
                return self._json({"error": "nome mancante"}, 400)
            removed = _delete_report(name)
            return self._json({"ok": removed > 0, "removed": removed})
        if path == "/api/recon/install":
            return self._install(body.get("tool", ""))
        return self._recon(body.get("tool", ""), (body.get("target", "") or "").strip())

    def _phone_start(self):
        if _port_up("127.0.0.1", PHONE_PORT):
            return self._json({"up": True, "already": True})
        argv = _phone_start_argv()
        if not argv:
            return self._json({"error": "PhoneInfoga non disponibile "
                               "(installalo dal profilo OSINT)"}, 400)
        try:
            # Detached: PhoneInfoga resta a servire in background; non aspettiamo.
            subprocess.Popen(argv, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError as e:
            return self._json({"error": "avvio PhoneInfoga: %s" % e}, 500)
        return self._json({"up": False, "starting": True})

    def _install(self, tool):
        entry = RECON.get(tool)
        if not entry:
            return self._json({"error": "strumento non in whitelist"}, 400)
        if _bin_of(entry):
            return self._json({"ok": True, "already": True,
                               "output": "gia' installato."})
        argv = _install_argv(tool)
        if not argv:
            return self._json({"error": "installazione non disponibile "
                               "(manca nxs-tool)"}, 400)
        try:
            r = subprocess.run(argv, capture_output=True, text=True,
                               timeout=INSTALL_TIMEOUT)
            out = (r.stdout + r.stderr).strip()
        except subprocess.TimeoutExpired:
            return self._json({"error": "installazione: tempo scaduto"}, 504)
        except OSError as e:
            return self._json({"error": "installazione: %s" % e}, 500)
        ok = _bin_of(entry) is not None
        if len(out) > OUT_MAX:
            out = out[:OUT_MAX] + "\n... (output troncato)"
        return self._json({"ok": ok,
                           "output": "$ %s\n\n%s" % (" ".join(argv), out or "(fatto)"),
                           "error": None if ok else "installazione non riuscita"})

    def _recon(self, tool, target):
        entry = RECON.get(tool)
        if not entry:
            return self._json({"error": "strumento non in whitelist"}, 400)
        if not _valido(entry["kind"], target):
            return self._json({"error": "obiettivo non valido per il tipo '%s'"
                               % entry["kind"]}, 400)
        b = _bin_of(entry)
        if not b:
            return self._json({"error": "strumento non installato (installa dal profilo OSINT)"}, 400)
        argv = entry["args"](b, target)
        try:
            r = subprocess.run(argv, capture_output=True, text=True,
                               timeout=RECON_TIMEOUT)
            out = (r.stdout + r.stderr).strip() or "(nessun output)"
        except subprocess.TimeoutExpired:
            out = "Tempo scaduto (%ds)." % RECON_TIMEOUT
        except OSError as e:
            out = "Errore di esecuzione: %s" % e
        if len(out) > OUT_MAX:
            out = out[:OUT_MAX] + "\n... (output troncato)"
        return self._json({"output": "$ %s\n\n%s" % (" ".join(argv), out)})


def make_server():
    """Crea il server su 127.0.0.1. Ritorna (httpd, porta).

    Porta effimera di default; NXS_HORUS_PORT la fissa (0 = effimera). Legata
    SOLO a loopback: non e' raggiungibile dalla rete."""
    try:
        port = int(os.environ.get("NXS_HORUS_PORT", "0"))
    except ValueError:
        port = 0
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    # Pre-carica i TLE in background: quando l'utente accende i satelliti sono
    # gia' pronti (niente attesa al primo click). Best-effort.
    threading.Thread(target=lambda: _tle(), daemon=True).start()
    return httpd, httpd.server_address[1]


def serve_in_thread():
    httpd, port = make_server()
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, port
