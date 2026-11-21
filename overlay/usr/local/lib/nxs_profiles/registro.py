# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""Registro degli incarichi - ogni strumento lanciato lascia una traccia.

Pensato per il lavoro sul campo (pentest/OSINT/forense): a fine incarico si
deve poter dire COSA e' stato lanciato, QUANDO, con quale ESITO e quali FILE
ha prodotto, con impronte che ne provano l'integrita'.

  - Una riga JSON per evento in ~/NexusSec-loot/registro/registro-incarichi.jsonl
    (NexusSec-loot sta nella persistenza: il registro sopravvive ai riavvii).
  - Orari in UTC (esplicito) + ora locale, utente, host, versione, profilo,
    modalita' di rete (anonima via Tor o no), comando, codice d'uscita, durata.
  - Impronte SHA-256 dei file NUOVI o MODIFICATI in NexusSec-loot durante il
    lancio (catena di custodia dei risultati).
  - CATENA: ogni riga contiene l'impronta della riga precedente ("prec") e la
    propria ("hash"). Modificare o cancellare una riga passata rompe la catena
    e `verifica()` lo segnala (stessa idea della catena di custodia di nxs-case).

Nessuna dipendenza esterna, nessuna GUI: lo usano nxs-tool, HORUS, nxs-registro
e la vista "Registro e log" del Centro di Controllo. NON deve mai far fallire
il lancio di uno strumento: ogni errore qui viene ignorato.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import socket
from pathlib import Path

LOOT = Path(os.path.expanduser("~")) / "NexusSec-loot"
DIR = LOOT / "registro"
FILE = DIR / "registro-incarichi.jsonl"
MAX_FILE_HASH = 512 * 1024 * 1024      # oltre: impronta saltata (troppo lento)
MAX_FILES = 300                        # file elencati per singolo lancio
_GENESI = "0" * 64


def _utc():
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _locale():
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _versione():
    for p in ("/etc/nexussec-release", "/etc/alpine-release"):
        try:
            return open(p).read().strip()
        except OSError:
            continue
    return ""


def _profilo():
    try:
        return json.load(open("/etc/sec_os/state.json")).get("profile", "")
    except (OSError, ValueError):
        try:
            return (Path.home() / ".config/nxs/profile").read_text().strip()
        except OSError:
            return ""


def _rete():
    return "anonima (Tor)" if os.path.exists("/run/nxs-anon.on") else "normale"


def istantanea_loot():
    """{percorso_relativo: (mtime, size)} dei file in NexusSec-loot (escluso il
    registro stesso). Serve a capire cosa ha prodotto un lancio."""
    out = {}
    if not LOOT.is_dir():
        return out
    for radice, dirs, files in os.walk(LOOT):
        if Path(radice) == DIR or DIR in Path(radice).parents:
            continue
        for n in files:
            p = Path(radice) / n
            try:
                st = p.stat()
            except OSError:
                continue
            out[str(p.relative_to(LOOT))] = (st.st_mtime, st.st_size)
    return out


def _file_prodotti(prima, dopo):
    nuovi = [k for k, v in dopo.items() if prima.get(k) != v]
    res = []
    for rel in sorted(nuovi)[:MAX_FILES]:
        p = LOOT / rel
        mt, sz = dopo[rel]
        voce = {"file": rel, "byte": sz}
        if sz <= MAX_FILE_HASH:
            try:
                voce["sha256"] = sha256_file(p)
            except OSError:
                voce["sha256"] = "illeggibile"
        else:
            voce["sha256"] = "non calcolata (oltre 512 MB)"
        res.append(voce)
    if len(nuovi) > MAX_FILES:
        res.append({"file": "... altri %d file" % (len(nuovi) - MAX_FILES)})
    return res


def _ultimo_hash():
    try:
        with open(FILE, "rb") as f:
            f.seek(0, 2)
            pos = f.tell()
            buf = b""
            while pos > 0 and buf.count(b"\n") < 2:
                step = min(4096, pos)
                pos -= step
                f.seek(pos)
                buf = f.read(step) + buf
        righe = [r for r in buf.splitlines() if r.strip()]
        return json.loads(righe[-1]).get("hash", _GENESI) if righe else _GENESI
    except (OSError, ValueError, IndexError):
        return _GENESI


def _calcola_hash(voce):
    v = {k: voce[k] for k in voce if k != "hash"}
    return hashlib.sha256(json.dumps(v, sort_keys=True, ensure_ascii=False)
                          .encode()).hexdigest()


def annota(evento, **dati):
    """Aggiunge una riga al registro (append-only, concatenata). Mai eccezioni."""
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        voce = {"utc": _utc(), "locale": _locale(), "evento": evento,
                "utente": os.environ.get("USER") or str(os.getuid()),
                "host": socket.gethostname(), "versione": _versione(),
                "profilo": _profilo(), "rete": _rete()}
        voce.update(dati)
        voce["prec"] = _ultimo_hash()
        voce["hash"] = _calcola_hash(voce)
        with open(FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(voce, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        try:
            os.chmod(FILE, 0o600)          # dati d'incarico: solo l'utente
        except OSError:
            pass
        return voce
    except Exception:                      # noqa: BLE001 - il registro non blocca mai
        return None


class Lancio:
    """Uso:  with registro.Lancio(tool, comando, metodo) as l: rc = esegui(); l.rc = rc"""

    def __init__(self, strumento, comando="", metodo="", origine="nxs-tool"):
        self.strumento, self.comando, self.metodo, self.origine = \
            strumento, comando, metodo, origine
        self.rc = None

    def __enter__(self):
        import time
        self._t0 = time.time()
        try:
            self._prima = istantanea_loot()
        except Exception:                  # noqa: BLE001
            self._prima = {}
        annota("avvio", strumento=self.strumento, comando=self.comando,
               metodo=self.metodo, origine=self.origine)
        return self

    def __exit__(self, tipo, valore, tb):
        import time
        try:
            prodotti = _file_prodotti(self._prima, istantanea_loot())
        except Exception:                  # noqa: BLE001
            prodotti = []
        esito = self.rc
        if tipo is not None:
            esito = "errore: %s" % (valore or tipo.__name__)
        annota("fine", strumento=self.strumento, comando=self.comando,
               metodo=self.metodo, origine=self.origine, esito=esito,
               durata_s=round(time.time() - self._t0, 1), file_prodotti=prodotti)
        return False                       # le eccezioni proseguono normalmente


def voci():
    """Tutte le righe del registro (le malformate come {'errore': ...})."""
    out = []
    try:
        with open(FILE, encoding="utf-8") as f:
            for n, riga in enumerate(f, 1):
                if not riga.strip():
                    continue
                try:
                    out.append(json.loads(riga))
                except ValueError:
                    out.append({"errore": "riga %d illeggibile" % n})
    except OSError:
        pass
    return out


def verifica():
    """(ok, messaggi). Controlla la catena: ogni riga deve avere l'impronta
    giusta e puntare alla precedente. Una riga modificata o tolta si vede."""
    prec, msg = _GENESI, []
    tutte = voci()
    for i, v in enumerate(tutte, 1):
        if "errore" in v:
            msg.append(v["errore"])
            continue
        if v.get("prec") != prec:
            msg.append("riga %d: catena interrotta (manca o e' cambiata una riga precedente)" % i)
        if _calcola_hash(v) != v.get("hash"):
            msg.append("riga %d: contenuto MODIFICATO dopo la registrazione" % i)
        prec = v.get("hash", "")
    return (not msg, msg or ["%d righe, catena integra" % len(tutte)])


def verifica_file():
    """Ricalcola le impronte dei file prodotti ancora presenti: (ok, messaggi)."""
    msg, ok = [], True
    for v in voci():
        for fp in v.get("file_prodotti") or []:
            h = fp.get("sha256", "")
            if len(h) != 64:
                continue
            p = LOOT / fp.get("file", "")
            if not p.exists():
                msg.append("assente: %s" % fp["file"])
                continue
            try:
                if sha256_file(p) != h:
                    ok = False
                    msg.append("CAMBIATO dopo il lancio (%s): %s" % (v.get("utc"), fp["file"]))
            except OSError:
                msg.append("illeggibile: %s" % fp["file"])
    return ok, msg or ["tutti i file registrati corrispondono alle impronte"]


def esporta_html(dest):
    """Rapporto HTML autonomo del registro (per allegarlo alla relazione)."""
    import html
    ok, vmsg = verifica()
    righe = []
    for v in voci():
        if v.get("evento") != "fine":
            continue
        fp = "<br>".join("%s <code>%s</code>" % (html.escape(x.get("file", "")),
                                                  html.escape(x.get("sha256", "")))
                         for x in v.get("file_prodotti") or [])
        righe.append("<tr><td>%s</td><td>%s</td><td><code>%s</code></td><td>%s</td>"
                     "<td>%s s</td><td>%s</td><td>%s</td></tr>" % tuple(html.escape(str(x)) if i < 6 else x
                     for i, x in enumerate((v.get("utc", ""), v.get("strumento", ""),
                                           v.get("comando", ""), v.get("esito", ""),
                                           v.get("durata_s", ""), v.get("rete", ""), fp))))
    doc = ("<!doctype html><meta charset=utf-8><title>Registro incarichi NexusSec</title>"
           "<style>body{font-family:sans-serif;margin:24px}table{border-collapse:collapse;width:100%%}"
           "td,th{border:1px solid #bbb;padding:4px 6px;font-size:12px;vertical-align:top}"
           "code{font-size:11px;word-break:break-all}</style>"
           "<h1>Registro incarichi NexusSec</h1><p>Generato: %s UTC &middot; host %s &middot; "
           "integrit&agrave; della catena: <b>%s</b> (%s)</p>"
           "<table><tr><th>Fine (UTC)</th><th>Strumento</th><th>Comando</th><th>Esito</th>"
           "<th>Durata</th><th>Rete</th><th>File prodotti (SHA-256)</th></tr>%s</table>"
           % (_utc(), html.escape(socket.gethostname()), "OK" if ok else "NON INTEGRA",
              html.escape("; ".join(vmsg)), "".join(righe)))
    Path(dest).write_text(doc, encoding="utf-8")
    return dest


def salva_log(cartella=None):
    """Copia i log NexusSec (in RAM, /tmp/nxs-*.log + boot) nel registro, cosi'
    con la persistenza non si perdono allo spegnimento. Ritorna la cartella."""
    import glob
    import shutil
    dest = Path(cartella) if cartella else DIR / "log" / _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    sorgenti = glob.glob("/tmp/nxs-*.log") + ["/var/log/nxs-boot.log",
                                              os.path.expanduser("~/.local/share/xorg/Xorg.0.log")]
    copiati = 0
    for s in sorgenti:
        if os.path.isfile(s) and os.path.getsize(s) > 0:
            dest.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(s, dest / os.path.basename(s))
                copiati += 1
            except OSError:
                pass
    if copiati:
        annota("log-salvati", cartella=str(dest), numero=copiati)
    return dest if copiati else None
