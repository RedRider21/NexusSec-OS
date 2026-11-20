# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""Layer aggiuntivi di HORUS (2026-11): tutte fonti GRATUITE e SENZA CHIAVE,
verificate una per una (licenza + endpoint vivo).

    gdacs      GDACS (Commissione UE JRC + ONU): allerte disastri mondiali
    outages    IODA (Georgia Tech): blackout/censure di Internet per Paese
    ransomware ransomware.live: vittime recenti rivendicate (uso personale libero)
    tor        Tor Metrics / Onionoo (CC0): relay Tor per Paese
    aurora     NOAA SWPC (pubblico dominio): probabilita' di aurora + indice Kp
    radiation  Safecast (CC0): sensori di radioattivita' in tempo reale
    fireballs  NASA JPL CNEOS (pubblico dominio): bolidi/meteore in atmosfera
    launches   TheSpaceDevs Launch Library 2 (gratis, 15 richieste/ora)
    airports   OurAirports (pubblico dominio): aeroporti grandi e medi
    events     NASA EONET (pubblico dominio): tempeste, alluvioni, frane, ...
    nws        NOAA NWS (pubblico dominio): allerte meteo gravi negli USA

Scartate di proposito: PeeringDB (il regolamento vieta la "mappatura"),
gpsjam (nessuna licenza dichiarata), World Port Index (servizio in 503),
OpenAQ/WAQI/ACLED/UCDP/ReliefWeb (ora richiedono chiave o registrazione).

Formato UNIFORME restituito al browser: GeoJSON le cui `properties` hanno
    t     titolo del fumetto
    rows  [[etichetta, valore], ...]   (testo semplice: il client fa l'escape)
    links [[etichetta, url], ...]
    c     colore (opz., altrimenti quello del layer)
    r     raggio del pallino (opz.)
cosi' un unico disegnatore lato client serve tutti i layer.

Il modulo NON importa server.py (niente import circolari): riceve `fetch`
(la _fetch del server, che passa da Tor se attivo) e la cartella di config.
"""
import csv
import hashlib
import io
import json
import math
import threading
import time
import urllib.request

_CACHE = {}               # fid -> (ts, dati)
_LOCK = threading.Lock()
_BUSY = set()             # fid in download (Safecast impiega ~100s)

# Durata della cache lato server (secondi), per non martellare le fonti.
TTL = {
    "gdacs": 900, "outages": 600, "ransomware": 1800, "tor": 3600,
    "aurora": 1800, "radiation": 3600, "fireballs": 21600,
    "launches": 3600, "airports": 7 * 86400, "events": 1800, "nws": 600,
    "kev": 3 * 3600,
}

# Colori di gravita' condivisi.
RED, ORANGE, GREEN, GREY = "#ff3b5c", "#ff9f1c", "#2ec27e", "#8aa0ad"


def _f(x, nd=1):
    try:
        return round(float(x), nd)
    except (TypeError, ValueError):
        return None


def _pt(lon, lat, props):
    return {"type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": props}


def _fc(feats, **meta):
    d = {"type": "FeatureCollection", "features": feats}
    d.update(meta)
    return d


def _jitter(key, lon, lat, spread=1.2):
    """Sposta in modo DETERMINISTICO (hash della chiave) i punti che cadono nello
    stesso centro-Paese, cosi' non si sovrappongono tutti in un pixel."""
    h = hashlib.md5(key.encode("utf-8", "replace")).digest()
    a = h[0] / 255 * 2 * math.pi
    d = (h[1] / 255) * spread
    return lon + d * math.cos(a), lat + d * math.sin(a)


def _raw(url, timeout=40):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# Centri dei Paesi (ISO 3166-1 alpha-2 -> lon, lat, nome IT) da Wikidata (CC0).
# Servono a IODA, ransomware.live e Tor, che danno solo il codice Paese.
# Cache su FILE 30 giorni: i confini non cambiano.
# ---------------------------------------------------------------------------
_CENTROIDS = {}
_CENTR_Q = ('PREFIX wdt: <http://www.wikidata.org/prop/direct/> '
            'PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> '
            'SELECT ?iso ?coord ?label WHERE { ?c wdt:P297 ?iso ; wdt:P625 ?coord . '
            'OPTIONAL { ?c rdfs:label ?label FILTER(lang(?label)="it") } }')


def centroids(fetch, conf_dir):
    if _CENTROIDS:
        return _CENTROIDS
    path = conf_dir / "horus-centroids.json"
    try:
        d = json.loads(path.read_text())
        if time.time() - d.get("ts", 0) < 30 * 86400 and d.get("c"):
            _CENTROIDS.update(d["c"])
            return _CENTROIDS
    except (OSError, ValueError):
        pass
    import urllib.parse
    url = "https://qlever.dev/api/wikidata?query=" + urllib.parse.quote(_CENTR_Q)
    data = fetch(url, headers={"Accept": "application/sparql-results+json"}, timeout=60)
    out = {}
    for b in data.get("results", {}).get("bindings", []):
        iso = b["iso"]["value"].upper()
        w = b["coord"]["value"]            # POINT(lon lat)
        try:
            lon, lat = (float(x) for x in w[w.index("(") + 1:w.index(")")].split())
        except ValueError:
            continue
        if iso not in out:                  # primo valore (alcuni Paesi ne hanno 2)
            out[iso] = [lon, lat, (b.get("label") or {}).get("value") or iso]
    if out:
        _CENTROIDS.update(out)
        try:
            conf_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"ts": time.time(), "c": out}))
        except OSError:
            pass
    return _CENTROIDS


# ---------------------------------------------------------------------------
# Un costruttore per layer. Ciascuno restituisce una FeatureCollection uniforme.
# ---------------------------------------------------------------------------
_GDACS_T = {"EQ": "Terremoto", "TC": "Ciclone tropicale", "FL": "Alluvione",
            "VO": "Eruzione vulcanica", "DR": "Siccità", "WF": "Incendio boschivo",
            "TS": "Tsunami"}
# verde GDACS piu' chiaro: non si confonde col verde della radioattivita'
_GDACS_C = {"Red": RED, "Orange": ORANGE, "Green": "#c5e478"}
_GDACS_L = {"Red": "ROSSA (grave)", "Orange": "ARANCIONE (media)", "Green": "verde (lieve)"}


def _gdacs(fetch, _cd):
    d0 = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 30 * 86400))
    d1 = time.strftime("%Y-%m-%d", time.gmtime())
    # L'API restituisce pagine da 100 eventi (pageNumber): ne leggiamo fino a 6.
    allf = []
    for pg in range(1, 7):
        try:
            data = fetch("https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
                         "?eventlist=EQ,TC,FL,VO,DR,WF&alertlevel=Green;Orange;Red"
                         "&fromdate=%s&todate=%s&pageNumber=%d" % (d0, d1, pg), timeout=40)
        except Exception:          # noqa: BLE001 - pagina oltre la fine / errore
            if pg == 1:
                raise
            break
        page = data.get("features", [])
        allf.extend(page)
        if len(page) < 100:
            break
    feats, seen = [], set()
    for f in allf:
        eid = (f.get("properties") or {}).get("eventid")
        if eid in seen:
            continue
        seen.add(eid)
        g = f.get("geometry") or {}
        if g.get("type") != "Point":
            continue
        p = f.get("properties", {})
        lvl = p.get("alertlevel") or ""
        sev = (p.get("severitydata") or {})
        rows = [["Tipo", _GDACS_T.get(p.get("eventtype"), p.get("eventtype"))],
                ["Allerta", _GDACS_L.get(lvl, lvl)],
                ["Paese", p.get("country") or ""],
                ["Intensità", sev.get("severitytext") or ""],
                ["Inizio", (p.get("fromdate") or "")[:16].replace("T", " ")],
                ["Fine", (p.get("todate") or "")[:16].replace("T", " ")],
                ["Fonte", "GDACS (UE JRC / ONU)"]]
        rep = (p.get("url") or {}).get("report") or ""
        feats.append(_pt(g["coordinates"][0], g["coordinates"][1], {
            "t": p.get("name") or p.get("description") or "Evento",
            "rows": rows, "links": [["Rapporto GDACS", rep]],
            "c": _GDACS_C.get(lvl, GREY),
            "r": {"Red": 9, "Orange": 7}.get(lvl, 5)}))
    return _fc(feats)


def _outages(fetch, cd):
    now = int(time.time())
    data = fetch("https://api.ioda.inetintel.cc.gatech.edu/v2/outages/summary"
                 "?from=%d&until=%d&entityType=country" % (now - 86400, now), timeout=40)
    cen = centroids(fetch, cd)
    feats = []
    for e in data.get("data", []):
        ent = e.get("entity") or {}
        code = (ent.get("code") or "").upper()
        if code not in cen:
            continue
        lon, lat, nome = cen[code]
        sc = (e.get("scores") or {})
        ov = sc.get("overall") or 0
        # punteggio IODA: scala enorme -> raggio logaritmico (6..18)
        r = max(6, min(18, 4 + 1.6 * math.log10(ov + 1)))
        segn = ", ".join(sorted(k.split(".")[0] for k in sc if k != "overall"))
        feats.append(_pt(lon, lat, {
            "t": "Interruzione Internet - " + nome,
            "rows": [["Eventi (24h)", e.get("event_cnt")],
                     ["Segnali anomali", segn.replace("ping-slash24", "raggiungibilità (ping)")
                      .replace("bgp", "rotte BGP").replace("gtr", "traffico Google")
                      .replace("merit-nt", "telescopio di rete")],
                     ["Punteggio", "%.0f" % ov],
                     ["Fonte", "IODA - Georgia Tech"]],
            "links": [["Dashboard IODA",
                       "https://ioda.inetintel.cc.gatech.edu/country/" + code]],
            "c": RED if ov > 1e5 else ORANGE, "r": round(r, 1)}))
    return _fc(feats)


def _ransomware(fetch, cd):
    data = fetch("https://api.ransomware.live/v2/recentvictims", timeout=40)
    cen = centroids(fetch, cd)
    feats = []
    for v in data if isinstance(data, list) else []:
        code = (v.get("country") or "").upper()
        if code not in cen:
            continue
        lon, lat, nome = cen[code]
        lon, lat = _jitter((v.get("victim") or "") + (v.get("group") or ""), lon, lat, 2.0)
        when = (v.get("attackdate") or v.get("discovered") or "")[:16].replace("T", " ")
        feats.append(_pt(lon, lat, {
            "t": v.get("victim") or "Vittima",
            "rows": [["Gruppo", v.get("group")], ["Paese", nome],
                     ["Settore", v.get("activity")], ["Dominio", v.get("domain")],
                     ["Rivendicato", when],
                     ["Posizione", "centro del Paese (indicativa)"],
                     ["Fonte", "ransomware.live (libero per uso personale)"]],
            "links": [["Scheda ransomware.live", v.get("url") or ""]],
            "r": 5}))
    return _fc(feats)


def _tor(fetch, cd):
    data = fetch("https://onionoo.torproject.org/details?type=relay&running=true"
                 "&fields=country,flags,observed_bandwidth", timeout=60)
    cen = centroids(fetch, cd)
    agg = {}
    for r in data.get("relays", []):
        code = (r.get("country") or "").upper()
        a = agg.setdefault(code, [0, 0, 0, 0])
        fl = r.get("flags") or []
        a[0] += 1
        a[1] += "Exit" in fl
        a[2] += "Guard" in fl
        a[3] += r.get("observed_bandwidth") or 0
    feats = []
    for code, (n, ex, gu, bw) in agg.items():
        if code not in cen:
            continue
        lon, lat, nome = cen[code]
        feats.append(_pt(lon, lat, {
            "t": "Tor - " + nome,
            "rows": [["Relay attivi", n], ["Di uscita (exit)", ex],
                     ["Di guardia (guard)", gu],
                     ["Banda osservata", "%.1f Gbit/s" % (bw * 8 / 1e9)],
                     ["Fonte", "Tor Metrics / Onionoo (CC0)"]],
            "links": [["Tor Metrics", "https://metrics.torproject.org/rs.html#search/country:"
                       + code.lower()]],
            "c": "#b77cff", "r": round(max(4, min(22, 3 + 3 * math.log10(n + 1) * 1.6)), 1)}))
    return _fc(feats, total=sum(v[0] for v in agg.values()))


def _aurora(fetch, _cd):
    data = fetch("https://services.swpc.noaa.gov/json/ovation_aurora_latest.json", timeout=40)
    kp = ""
    try:
        k = fetch("https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
                  timeout=20)
        last = k[-1]
        kp = last.get("Kp") if isinstance(last, dict) else last[1]
    except Exception:          # noqa: BLE001 - il Kp e' un di piu'
        pass
    feats = []
    for lon, lat, p in data.get("coordinates", []):
        # griglia 1x1 grado: 1 punto ogni 2 gradi con probabilita' >=5%. Il
        # client li disegna come ALONE sfumato (o = opacita' ~ probabilita'),
        # cosi' si vede una fascia e non una fila di puntini.
        if p < 5 or lon % 2 or lat % 2:
            continue
        lo = lon - 360 if lon > 180 else lon
        feats.append(_pt(lo, lat, {
            "t": "Aurora %d%%" % p,
            "rows": [["Probabilità", "%d%%" % p], ["Indice Kp attuale", kp],
                     ["Previsione per", (data.get("Forecast Time") or "").replace("T", " ")],
                     ["Fonte", "NOAA SWPC (OVATION)"]],
            "links": [["Previsione NOAA", "https://www.swpc.noaa.gov/products/aurora-30-minute-forecast"]],
            "c": "#39ff88" if p < 50 else "#ff4fd8", "r": 9,
            "o": round(min(0.75, 0.08 + p / 120), 2)}))
    return _fc(feats, kp=kp)


# Safecast: fattori CPM -> microSievert/ora per i tubi Geiger piu' diffusi.
_SC_TUBE = {"lnd_7318u": 334, "lnd_7318c": 334, "lnd_7128ec": 108, "lnd_712u": 108,
            "lnd_78017w": 334}


def _radiation(fetch, _cd):
    # Endpoint LENTO (~100s, 1.4MB): timeout lungo, gira in background (vedi get).
    data = json.loads(_raw("https://tt.safecast.org/devices", timeout=180))
    lim = time.time() - 30 * 86400
    feats = []
    for d in data:
        lat, lon = d.get("loc_lat"), d.get("loc_lon")
        if lat is None or lon is None:
            continue
        w = d.get("when_captured") or ""
        try:
            ts = time.mktime(time.strptime(w[:19], "%Y-%m-%dT%H:%M:%S"))
        except ValueError:
            continue
        if ts < lim:
            continue
        cpm, usv = None, None
        for k, fac in _SC_TUBE.items():
            if d.get(k) is not None:
                cpm = d[k]
                usv = cpm / fac
                break
        if cpm is None:
            continue
        col = GREEN if usv < 0.3 else (ORANGE if usv < 1 else RED)
        # NB privacy: NON esponiamo device_contact_name (nome del volontario).
        feats.append(_pt(lon, lat, {
            "t": "Radioattività %.2f µSv/h" % usv,
            "rows": [["Dose stimata", "%.3f µSv/h" % usv], ["Conteggi", "%.0f CPM" % cpm],
                     ["Luogo", d.get("loc_name") or ""], ["Paese", d.get("loc_country") or ""],
                     ["Rilevato", w[:16].replace("T", " ")],
                     ["Fonte", "Safecast (CC0)"]],
            "links": [["Mappa Safecast", "https://map.safecast.org/"]],
            "c": col, "r": 5}))
    return _fc(feats)


def _fireballs(fetch, _cd):
    data = fetch("https://ssd-api.jpl.nasa.gov/fireball.api?limit=300&req-loc=true", timeout=40)
    idx = {k: i for i, k in enumerate(data.get("fields", []))}
    feats = []
    for row in data.get("data", []):
        try:
            lat = float(row[idx["lat"]]) * (-1 if row[idx["lat-dir"]] == "S" else 1)
            lon = float(row[idx["lon"]]) * (-1 if row[idx["lon-dir"]] == "W" else 1)
        except (TypeError, ValueError, KeyError):
            continue
        e = _f(row[idx["impact-e"]], 2)
        feats.append(_pt(lon, lat, {
            "t": "Bolide " + (row[idx["date"]] or ""),
            "rows": [["Data (UTC)", row[idx["date"]]],
                     ["Energia d'impatto", "%s kt" % e if e is not None else ""],
                     ["Quota", (row[idx["alt"]] or "") and row[idx["alt"]] + " km"],
                     ["Velocità", (row[idx["vel"]] or "") and row[idx["vel"]] + " km/s"],
                     ["Fonte", "NASA JPL CNEOS"]],
            "links": [["Dati NASA", "https://cneos.jpl.nasa.gov/fireballs/"]],
            "r": round(min(10, 2 + 1.5 * math.log10((e or 0.01) * 100 + 1)), 1)}))
    return _fc(feats)


def _launches(fetch, _cd):
    data = fetch("https://ll.thespacedevs.com/2.2.0/launch/upcoming/?limit=40&mode=normal",
                 timeout=40)
    feats = []
    for r in data.get("results", []):
        pad = r.get("pad") or {}
        try:
            lat, lon = float(pad.get("latitude")), float(pad.get("longitude"))
        except (TypeError, ValueError):
            continue
        lon, lat = _jitter(r.get("id") or r.get("name") or "", lon, lat, 0.15)
        st = (r.get("status") or {}).get("name") or ""
        mis = r.get("mission") or {}
        feats.append(_pt(lon, lat, {
            "t": r.get("name") or "Lancio",
            "rows": [["Quando (UTC)", (r.get("net") or "")[:16].replace("T", " ")],
                     ["Stato", st],
                     ["Operatore", (r.get("launch_service_provider") or {}).get("name")],
                     ["Razzo", ((r.get("rocket") or {}).get("configuration") or {}).get("full_name")],
                     ["Missione", mis.get("name")], ["Orbita", (mis.get("orbit") or {}).get("name")],
                     ["Rampa", pad.get("name")],
                     ["Base", (pad.get("location") or {}).get("name")],
                     ["Fonte", "TheSpaceDevs Launch Library 2"]],
            "links": [["Diretta / info", ((r.get("vidURLs") or [{}])[0] or {}).get("url", "")
                       if r.get("vidURLs") else ""]],
            "c": "#ffd166" if "Go" in st else "#e9c46a", "r": 7}))
    return _fc(feats)


def _airports(_fetch, cd):
    """OurAirports (pubblico dominio): CSV di ~12MB -> teniamo solo aeroporti
    grandi e medi con servizio di linea (~3500). Cache su FILE 7 giorni."""
    path = cd / "horus-airports.json"
    try:
        d = json.loads(path.read_text())
        if time.time() - d.get("ts", 0) < 7 * 86400:
            return d["fc"]
    except (OSError, ValueError, KeyError):
        pass
    txt = _raw("https://davidmegginson.github.io/ourairports-data/airports.csv", timeout=90)
    feats = []
    for a in csv.DictReader(io.StringIO(txt)):
        ty = a.get("type")
        if ty not in ("large_airport", "medium_airport"):
            continue
        if ty == "medium_airport" and a.get("scheduled_service") != "yes":
            continue
        try:
            lat, lon = float(a["latitude_deg"]), float(a["longitude_deg"])
        except (TypeError, ValueError):
            continue
        big = ty == "large_airport"
        feats.append(_pt(round(lon, 4), round(lat, 4), {
            "t": a.get("name") or "Aeroporto",
            "rows": [["Codici", " / ".join(x for x in (a.get("iata_code"), a.get("icao_code")
                                                       or a.get("ident")) if x)],
                     ["Città", a.get("municipality")], ["Paese", a.get("iso_country")],
                     ["Tipo", "grande" if big else "medio"],
                     ["Quota", (a.get("elevation_ft") or "") and "%s ft" % a["elevation_ft"]],
                     ["Fonte", "OurAirports (pubblico dominio)"]],
            "links": [["Sito", a.get("home_link") or ""], ["Wikipedia", a.get("wikipedia_link") or ""]],
            "r": 5 if big else 3, "c": "#9ad1ff" if big else "#5fa8d3"}))
    fc = _fc(feats)
    try:
        cd.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"ts": time.time(), "fc": fc}))
    except OSError:
        pass
    return fc


_EONET_CATS = {"severeStorms": ("Tempesta / ciclone", "#4cc9f0"),
               "floods": ("Alluvione", "#4361ee"),
               "landslides": ("Frana", "#bc6c25"),
               "dustHaze": ("Polvere / foschia", "#d4a373"),
               "snow": ("Neve estrema", "#e0fbfc"),
               "seaLakeIce": ("Ghiaccio marino/lacustre", "#a8dadc"),
               "tempExtremes": ("Temperature estreme", "#f72585"),
               "drought": ("Siccità", "#e9c46a"),
               "manmade": ("Evento di origine umana", "#ff6b6b")}


def _events(fetch, _cd):
    data = fetch("https://eonet.gsfc.nasa.gov/api/v3/events?status=open&limit=500&category="
                 + ",".join(_EONET_CATS), timeout=60)
    feats = []
    for ev in data.get("events", []):
        geos = ev.get("geometry") or []
        if not geos:
            continue
        g = geos[-1]                       # ultima posizione nota
        co = g.get("coordinates")
        if g.get("type") == "Polygon":
            ring = co[0]
            co = [sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)]
        if not co or len(co) < 2:
            continue
        cat = ((ev.get("categories") or [{}])[0]).get("id", "")
        nome, col = _EONET_CATS.get(cat, ("Evento", GREY))
        mag = ""
        if g.get("magnitudeValue") is not None:
            mag = "%s %s" % (g["magnitudeValue"], g.get("magnitudeUnit") or "")
        src = (ev.get("sources") or [{}])[0]
        feats.append(_pt(co[0], co[1], {
            "t": ev.get("title") or nome,
            "rows": [["Tipo", nome], ["Intensità", mag],
                     ["Ultimo aggiornamento", (g.get("date") or "")[:16].replace("T", " ")],
                     ["Posizioni registrate", len(geos)],
                     ["Fonte", "NASA EONET (%s)" % (src.get("id") or "")]],
            "links": [["Fonte originale", src.get("url") or ""]],
            "c": col, "r": 7}))
    return _fc(feats)


_NWS_C = {"Extreme": RED, "Severe": ORANGE}


def _nws(fetch, _cd):
    data = fetch("https://api.weather.gov/alerts/active?status=actual&severity=Extreme,Severe",
                 headers={"Accept": "application/geo+json"}, timeout=40)
    feats = []
    for f in data.get("features", []):
        g = f.get("geometry")
        if not g:
            continue                       # allerte per zona senza poligono: saltate
        p = f.get("properties", {})
        feats.append({"type": "Feature", "geometry": g, "properties": {
            "t": p.get("event") or "Allerta",
            "rows": [["Gravità", {"Extreme": "ESTREMA", "Severe": "grave"}.get(p.get("severity"), p.get("severity"))],
                     ["Zona", (p.get("areaDesc") or "")[:200]],
                     ["Inizio", (p.get("onset") or p.get("effective") or "")[:16].replace("T", " ")],
                     ["Fine", (p.get("ends") or p.get("expires") or "")[:16].replace("T", " ")],
                     ["Titolo", p.get("headline")],
                     ["Fonte", "NOAA National Weather Service"]],
            "links": [["Testo completo", p.get("@id") or ""]],
            "c": _NWS_C.get(p.get("severity"), ORANGE)}})
    return _fc(feats)


def _kev(fetch, _cd):
    """CISA KEV (pubblico dominio USA): vulnerabilita' SFRUTTATE davvero negli
    attacchi. Non e' un dato da mappa: lo mostra un elenco nella scheda Feed."""
    data = fetch("https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
                 timeout=60)
    vs = sorted(data.get("vulnerabilities", []), key=lambda v: v.get("dateAdded", ""),
                reverse=True)[:40]
    return {"count": data.get("count"), "released": data.get("dateReleased", "")[:10],
            "items": [{"cve": v.get("cveID"), "vendor": v.get("vendorProject"),
                       "product": v.get("product"), "name": v.get("vulnerabilityName"),
                       "added": v.get("dateAdded"), "due": v.get("dueDate"),
                       "ransomware": v.get("knownRansomwareCampaignUse") == "Known",
                       "action": v.get("requiredAction"), "cwes": v.get("cwes") or [],
                       "desc": v.get("shortDescription")} for v in vs]}


_CVE = {}                 # id -> (ts, dati)  (NVD: max 5 richieste / 30s senza chiave)
_CVE_RE = __import__("re").compile(r"^CVE-\d{4}-\d{4,7}$")


def cve(cid, fetch):
    """Scheda di una CVE dall'API pubblica NVD 2.0 (NIST, pubblico dominio,
    senza chiave): descrizione, punteggio CVSS piu' recente, debolezze (CWE),
    riferimenti. Cache 1 giorno."""
    cid = (cid or "").strip().upper()
    if not _CVE_RE.match(cid):
        raise ValueError("identificativo CVE non valido")
    hit = _CVE.get(cid)
    if hit and time.time() - hit[0] < 86400:
        return hit[1]
    d = fetch("https://services.nvd.nist.gov/rest/json/cves/2.0?cveId=" + cid, timeout=40)
    vs = d.get("vulnerabilities") or []
    if not vs:
        raise ValueError("CVE non trovata in NVD")
    c = vs[0].get("cve", {})
    desc = next((x.get("value") for x in c.get("descriptions", []) if x.get("lang") == "en"), "")
    score = None
    m = c.get("metrics") or {}
    for k in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        for e in m.get(k) or []:
            cd = e.get("cvssData") or {}
            if cd.get("baseScore") is not None:
                score = {"version": cd.get("version") or k[10:], "score": cd.get("baseScore"),
                         "severity": cd.get("baseSeverity") or e.get("baseSeverity") or "",
                         "vector": cd.get("vectorString") or ""}
                break
        if score:
            break
    cwes = sorted({dd.get("value") for w in c.get("weaknesses", [])
                   for dd in w.get("description", []) if dd.get("value", "").startswith("CWE")})
    refs = [{"url": r.get("url"), "tags": r.get("tags") or []}
            for r in (c.get("references") or [])[:25]]
    out = {"id": cid, "published": (c.get("published") or "")[:10],
           "modified": (c.get("lastModified") or "")[:10], "status": c.get("vulnStatus"),
           "desc": desc, "cvss": score, "cwes": cwes, "refs": refs}
    _CVE[cid] = (time.time(), out)
    return out


BUILDERS = {"gdacs": _gdacs, "outages": _outages, "ransomware": _ransomware,
            "tor": _tor, "aurora": _aurora, "radiation": _radiation,
            "fireballs": _fireballs, "launches": _launches, "airports": _airports,
            "events": _events, "nws": _nws, "kev": _kev}

# Layer lenti: si scaricano in BACKGROUND; finche' non sono pronti si risponde
# con l'ultima copia (o "in preparazione") invece di tenere appesa la pagina.
SLOW = {"radiation", "airports"}


def _file_cache(cd, fid):
    try:
        d = json.loads((cd / ("horus-%s.json" % fid)).read_text())
        return d.get("ts", 0), d.get("data") or d.get("fc")
    except (OSError, ValueError):
        return 0, None


def _store(cd, fid, data):
    _CACHE[fid] = (time.time(), data)
    if fid in SLOW and fid != "airports":     # airports ha la sua cache file
        try:
            cd.mkdir(parents=True, exist_ok=True)
            (cd / ("horus-%s.json" % fid)).write_text(
                json.dumps({"ts": time.time(), "data": data}))
        except OSError:
            pass


def _build(fid, fetch, cd):
    try:
        data = BUILDERS[fid](fetch, cd)
        _store(cd, fid, data)
        return data
    finally:
        with _LOCK:
            _BUSY.discard(fid)


def get(fid, fetch, conf_dir):
    """Dati del layer `fid` (cache TTL). Solleva eccezione se la fonte non
    risponde e non c'e' nessuna copia precedente."""
    now = time.time()
    hit = _CACHE.get(fid)
    if not hit and fid in SLOW:
        ts, d = _file_cache(conf_dir, fid)
        if d is not None:
            hit = _CACHE[fid] = (ts, d)
    if hit and now - hit[0] < TTL.get(fid, 900):
        return hit[1]
    if fid in SLOW:
        with _LOCK:
            start = fid not in _BUSY
            _BUSY.add(fid)
        if start:
            threading.Thread(target=_build, args=(fid, fetch, conf_dir), daemon=True).start()
        if hit:
            return hit[1]                    # copia vecchia mentre si aggiorna
        return _fc([], pending=True)
    with _LOCK:
        _BUSY.add(fid)
    try:
        return _build(fid, fetch, conf_dir)
    except Exception:
        if hit:
            return hit[1]                    # fonte giu': ultima copia buona
        raise
