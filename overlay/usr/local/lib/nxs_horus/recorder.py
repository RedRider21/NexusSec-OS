"""HORUS - recorder di storico in BACKGROUND (processo staccato + SQLite).

Modalita' ALTERNATIVA allo storico client-side (IndexedDB) usato quando HORUS e'
aperto. Qui un processo STACCATO (start_new_session) sopravvive alla chiusura
della finestra e campiona su FILE SQLite le entita' seguite + l'ISS, finche' non
lo si disattiva. NON riparte al boot (scelta esplicita: opt-in, footprint sotto
controllo).

Perche' SQLite e non JSON: lo store cresce nel tempo (giorni di registrazione);
SQLite scrive/legge a record con indici e query per intervallo, senza mai
caricare tutto in RAM. Un JSON grande andrebbe invece serializzato/deserializ-
zato tutto in memoria a ogni accesso (rischio di errori/lentezza). Il JSON resta
solo per il BACKUP/RESTORE portabile (stesso formato dello storico client, cosi'
i backup sono intercambiabili tra le due modalita').

Avvio come modulo:  python3 -m nxs_horus.recorder
Il server lo lancia/ferma via /api/recorder; il daemon rilegge la config a ogni
giro, cosi' cambi di ore/entita' non richiedono un riavvio.
"""
from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

# --- Percorsi (dati, non segreti: NON in ~/.config/nxs con le chiavi) ---------
DATA_DIR = Path(os.environ.get("NXS_HORUS_DATA")
                or (Path.home() / ".local" / "share" / "nxs_horus"))
DB_PATH = DATA_DIR / "tracks.db"
CFG_PATH = DATA_DIR / "recorder.json"
PID_PATH = DATA_DIR / "recorder.pid"
LOG_PATH = DATA_DIR / "recorder.log"

DEFAULT_HOURS = 72          # finestra di ritenzione (0 = illimitato per numero)
DEFAULT_INTERVAL = 60       # secondi tra un campione e l'altro
MAX_POINTS = 4000           # tetto punti per entita' (come il client)


# --- Store SQLite -----------------------------------------------------------
def _conn():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH), timeout=5)
    # WAL: il server (lettore) e il recorder (scrittore) sono processi distinti;
    # con WAL leggono/scrivono in parallelo senza bloccarsi.
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=4000")
    c.execute("CREATE TABLE IF NOT EXISTS tracks("
              "id INTEGER PRIMARY KEY AUTOINCREMENT,"
              "layer TEXT, key TEXT, lat REAL, lon REAL, t INTEGER, name TEXT)")
    c.execute("CREATE INDEX IF NOT EXISTS ix_ent ON tracks(layer,key,t)")
    return c


def insert(layer, key, lat, lon, t, name, hours=DEFAULT_HOURS):
    """Aggiunge un campione (salta il doppione se ha lo stesso t dell'ultimo)."""
    if lat is None or lon is None:
        return False
    key = str(key)
    t = int(t)
    c = _conn()
    try:
        row = c.execute("SELECT t FROM tracks WHERE layer=? AND key=? "
                        "ORDER BY t DESC LIMIT 1", (layer, key)).fetchone()
        if row and row[0] == t:
            return False
        c.execute("INSERT INTO tracks(layer,key,lat,lon,t,name) VALUES(?,?,?,?,?,?)",
                  (layer, key, float(lat), float(lon), t, name or ""))
        c.commit()
        _prune(c, layer, key, hours)
        c.commit()
        return True
    finally:
        c.close()


def _prune(c, layer, key, hours):
    if hours and hours > 0:
        min_t = int((time.time() - hours * 3600) * 1000)
        c.execute("DELETE FROM tracks WHERE layer=? AND key=? AND t<?",
                  (layer, key, min_t))
    # tetto per numero: tieni gli ultimi MAX_POINTS
    n = c.execute("SELECT COUNT(*) FROM tracks WHERE layer=? AND key=?",
                  (layer, key)).fetchone()[0]
    if n > MAX_POINTS:
        c.execute("DELETE FROM tracks WHERE id IN (SELECT id FROM tracks "
                  "WHERE layer=? AND key=? ORDER BY t ASC LIMIT ?)",
                  (layer, key, n - MAX_POINTS))


def entities():
    """Elenco entita' con storico: {layer,key,name,count,first,last}."""
    c = _conn()
    try:
        rows = c.execute(
            "SELECT layer,key,COUNT(*),MIN(t),MAX(t),"
            "(SELECT name FROM tracks t2 WHERE t2.layer=t1.layer AND t2.key=t1.key "
            " AND name<>'' ORDER BY t DESC LIMIT 1) "
            "FROM tracks t1 GROUP BY layer,key").fetchall()
    finally:
        c.close()
    return [{"layer": r[0], "key": r[1], "count": r[2], "first": r[3],
             "last": r[4], "name": r[5] or r[1]} for r in rows]


def range_(layer, key, from_t=0, to_t=None):
    """Campioni di un'entita' tra from_t e to_t (ms), ordinati nel tempo."""
    if to_t is None:
        to_t = 8_640_000_000_000_000
    c = _conn()
    try:
        rows = c.execute(
            "SELECT layer,key,lat,lon,t,name FROM tracks "
            "WHERE layer=? AND key=? AND t BETWEEN ? AND ? ORDER BY t ASC",
            (layer, str(key), int(from_t or 0), int(to_t))).fetchall()
    finally:
        c.close()
    return [{"layer": r[0], "key": r[1], "lat": r[2], "lon": r[3],
             "t": r[4], "name": r[5]} for r in rows]


def export_all():
    """Backup completo (stesso formato del client: intercambiabile)."""
    c = _conn()
    try:
        rows = c.execute("SELECT layer,key,lat,lon,t,name FROM tracks "
                         "ORDER BY t ASC").fetchall()
    finally:
        c.close()
    return {"format": "horus-tracks", "version": 1, "exported": int(time.time() * 1000),
            "samples": [{"layer": r[0], "key": r[1], "lat": r[2], "lon": r[3],
                         "t": r[4], "name": r[5]} for r in rows]}


def import_merge(samples, hours=DEFAULT_HOURS):
    """Fonde una lista di campioni nello store. Ritorna quanti inseriti."""
    n = 0
    touched = set()
    for s in (samples or []):
        if s.get("lat") is None or s.get("lon") is None:
            continue
        if insert(s.get("layer"), s.get("key"), s["lat"], s["lon"],
                  s.get("t") or int(time.time() * 1000), s.get("name") or "", hours):
            n += 1
        touched.add((s.get("layer"), str(s.get("key"))))
    return n


def _count():
    c = _conn()
    try:
        return c.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
    finally:
        c.close()


# --- Config -----------------------------------------------------------------
def load_cfg():
    cfg = {"enabled": False, "hours": DEFAULT_HOURS, "interval": DEFAULT_INTERVAL,
           "follows": []}
    try:
        cfg.update(json.loads(CFG_PATH.read_text()))
    except (OSError, ValueError):
        pass
    return cfg


def save_cfg(cfg):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CFG_PATH.write_text(json.dumps(cfg))
    return cfg


def set_config(enabled=None, hours=None, interval=None):
    cfg = load_cfg()
    if enabled is not None:
        cfg["enabled"] = bool(enabled)
    if hours is not None:
        cfg["hours"] = max(0, int(hours))
    if interval is not None:
        cfg["interval"] = max(15, int(interval))
    return save_cfg(cfg)


def follow_add(layer, key, name=""):
    cfg = load_cfg()
    key = str(key)
    fl = [f for f in cfg["follows"] if not (f["layer"] == layer and str(f["key"]) == key)]
    fl.append({"layer": layer, "key": key, "name": name or key})
    cfg["follows"] = fl
    return save_cfg(cfg)


def follow_del(layer, key):
    cfg = load_cfg()
    key = str(key)
    cfg["follows"] = [f for f in cfg["follows"]
                      if not (f["layer"] == layer and str(f["key"]) == key)]
    return save_cfg(cfg)


# --- Ciclo di vita del processo ---------------------------------------------
def pid_running():
    """PID del daemon se vivo, altrimenti 0."""
    try:
        pid = int(PID_PATH.read_text().strip())
    except (OSError, ValueError):
        return 0
    try:
        os.kill(pid, 0)
        return pid
    except OSError:
        return 0


def start_detached():
    """Avvia il recorder staccato (sopravvive alla finestra). No-op se gia' su."""
    pid = pid_running()
    if pid:
        return pid
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    parent = str(Path(__file__).resolve().parent.parent)  # dir che contiene nxs_horus/
    env["PYTHONPATH"] = parent + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    log = open(str(LOG_PATH), "ab")
    p = subprocess.Popen([sys.executable, "-m", "nxs_horus.recorder"],
                         stdout=log, stderr=log, start_new_session=True, env=env)
    return p.pid


def stop():
    """Ferma il daemon (SIGTERM). Ritorna True se ne ha ucciso uno."""
    pid = pid_running()
    if not pid:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False
    return True


def status():
    cfg = load_cfg()
    return {"enabled": bool(cfg.get("enabled")), "running": pid_running() > 0,
            "pid": pid_running(), "hours": cfg.get("hours", DEFAULT_HOURS),
            "interval": cfg.get("interval", DEFAULT_INTERVAL),
            "follows": cfg.get("follows", []), "samples": _count(),
            "entities": len(entities())}


# --- Campionamento (riusa server.py) ----------------------------------------
def _sample_iss(hours, now_ms):
    from nxs_horus import server
    try:
        d = server._fetch(server.FEEDS["iss"]["url"])
    except Exception:
        return
    if d.get("latitude") is None:
        return
    t = int(d.get("timestamp") or 0) * 1000 or now_ms
    insert("iss", "iss", d.get("latitude"), d.get("longitude"), t, "ISS", hours)


def _sample_flights(keys, hours, now_ms):
    from nxs_horus import server
    try:
        d = server._fetch(server.FEEDS["flights"]["url"])
    except Exception:
        return
    byk = {}
    for s in (d.get("states") or []):
        if s and s[0] in keys:
            byk[s[0]] = s
    for k, name in keys.items():
        s = byk.get(k)
        if not s or s[6] is None or s[5] is None:
            continue
        t = int((s[4] or s[3] or 0)) * 1000 or now_ms
        nm = (s[1] or "").strip() or name or k
        insert("flights", k, s[6], s[5], t, nm, hours)


def _sample_ships(keys, hours, now_ms):
    from nxs_horus import server
    try:
        key = server._aisstream_key()
        if key:
            server._AIS.ensure(key)
            server._AIS.set_bbox(None)
            gj = server._AIS.snapshot()
        else:
            fd = server.FEEDS["ships"]
            raw = server._fetch(fd["url"], headers=dict(fd.get("headers") or {}))
            gj = server._ships_geojson(raw)
    except Exception:
        return
    for f in (gj.get("features") or []):
        p = f.get("properties") or {}
        mmsi = str(p.get("mmsi") or "")
        if mmsi not in keys:
            continue
        c = (f.get("geometry") or {}).get("coordinates") or []
        if len(c) >= 2:
            nm = (p.get("name") or "").strip() or keys[mmsi] or mmsi
            insert("ships", mmsi, c[1], c[0], now_ms, nm, hours)


def _cycle(cfg):
    now_ms = int(time.time() * 1000)
    hours = cfg.get("hours", DEFAULT_HOURS)
    _sample_iss(hours, now_ms)          # ISS sempre
    follows = cfg.get("follows", [])
    flights = {str(f["key"]): f.get("name", "") for f in follows if f["layer"] == "flights"}
    ships = {str(f["key"]): f.get("name", "") for f in follows if f["layer"] == "ships"}
    if flights:
        _sample_flights(flights, hours, now_ms)
    if ships:
        _sample_ships(ships, hours, now_ms)


def run():
    """Loop del daemon. Esce se la config passa a enabled=false."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()))
    stopping = {"v": False}
    signal.signal(signal.SIGTERM, lambda *_: stopping.__setitem__("v", True))
    try:
        while not stopping["v"]:
            cfg = load_cfg()
            if not cfg.get("enabled"):
                break
            try:
                _cycle(cfg)
            except Exception as e:
                sys.stderr.write("recorder: giro fallito: %s\n" % e)
            # dorme a piccoli passi per reagire in fretta a stop/disattivazione
            interval = max(15, int(cfg.get("interval", DEFAULT_INTERVAL)))
            slept = 0
            while slept < interval and not stopping["v"]:
                time.sleep(min(5, interval - slept))
                slept += 5
                if not load_cfg().get("enabled"):
                    stopping["v"] = True
    finally:
        try:
            if pid_running() == os.getpid() or PID_PATH.read_text().strip() == str(os.getpid()):
                PID_PATH.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    # Esegui nell'istanza-pacchetto (evita il doppio-modulo del -m ...).
    from nxs_horus import recorder as _r
    _r.run()
