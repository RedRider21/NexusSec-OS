"""Caso forense - logica pura, senza GTK.

PERCHE' ESISTE: gli strumenti forensi veri (The Sleuth Kit, libewf) sono
eccellenti motori ma non tengono traccia di NULLA. In un accertamento serio il
problema non e' estrarre i dati: e' poter dimostrare, mesi dopo, COSA e' stato
fatto, QUANDO, con quale strumento e su quale reperto, e che il reperto non e'
cambiato. E' esattamente il valore che Autopsy aggiunge sopra TSK.

Qui quel registro e' automatico: ogni operazione scrive da sola nella catena di
custodia, con orario UTC, versione dello strumento e hash. Non c'e' un modo di
"dimenticarsi" di annotare, perche' non lo fa l'operatore.

Struttura di un caso:

    <base>/casi/<slug>/
        caso.json                  metadati (nome, operatore, riferimento, date)
        catena-di-custodia.log     registro append-only di OGNI azione
        immagini/                  acquisizioni E01 + log di ewfacquire
        analisi/                   partizioni, elenco file, timeline
        reperti/                   file estratti
        relazione.html             la relazione finale

Usa solo strumenti presenti sul media: ewfacquire/ewfverify (libewf), mmls/fls/
mactime (sleuthkit), sha256sum. Nessuna dipendenza Python esterna.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone

BASE_DEFAULT = os.path.expanduser("~/NexusSec-loot/casi")
_SLUG = re.compile(r"[^A-Za-z0-9._-]+")


def ora_utc():
    """Orario UTC in ISO 8601. In perizia l'ora locale e' ambigua (fuso, ora
    legale): il registro usa sempre UTC, esplicito."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slug(nome):
    s = _SLUG.sub("-", (nome or "").strip()).strip("-")
    return s or ("caso-%s" % time.strftime("%Y%m%d-%H%M%S"))


def have(prog):
    return shutil.which(prog) is not None


def versione(prog):
    """Versione dello strumento, da mettere agli atti: una timeline prodotta da
    TSK 4.12 e una da TSK 4.15 non sono lo stesso reperto."""
    for flag in ("-V", "--version", "-v"):
        try:
            r = subprocess.run([prog, flag], capture_output=True, text=True, timeout=8)
            testo = (r.stdout or r.stderr).strip().splitlines()
            if testo:
                return testo[0][:120]
        except (OSError, subprocess.SubprocessError):
            continue
    return "sconosciuta"


def _priv(args):
    if os.geteuid() != 0:
        if shutil.which("doas"):
            return ["doas"] + args
        if shutil.which("sudo"):
            return ["sudo"] + args
    return args


def sha256(percorso, blocco=1 << 20):
    """SHA-256 di un file. Calcolato a blocchi: le immagini sono enormi."""
    import hashlib
    h = hashlib.sha256()
    try:
        with open(percorso, "rb") as f:
            while True:
                b = f.read(blocco)
                if not b:
                    break
                h.update(b)
    except OSError:
        return None
    return h.hexdigest()


class Caso:
    def __init__(self, cartella):
        self.dir = os.path.abspath(cartella)
        self.meta = {}
        self._carica()

    # --- creazione / apertura -------------------------------------------
    @classmethod
    def crea(cls, base, nome, operatore, riferimento="", note=""):
        d = os.path.join(base, slug(nome))
        if os.path.exists(d):
            d = "%s-%s" % (d, time.strftime("%H%M%S"))
        for sub in ("", "immagini", "analisi", "reperti"):
            os.makedirs(os.path.join(d, sub), exist_ok=True)
        c = cls(d)
        c.meta = {
            "nome": nome,
            "operatore": operatore,
            "riferimento": riferimento,
            "note": note,
            "aperto": ora_utc(),
            "chiuso": None,
            "sistema": "NexusSec OS",
        }
        c._salva()
        c.registra("APERTURA CASO",
                   "nome=%s operatore=%s riferimento=%s" % (nome, operatore, riferimento or "-"))
        return c

    @classmethod
    def elenco(cls, base=BASE_DEFAULT):
        fuori = []
        if not os.path.isdir(base):
            return fuori
        for n in sorted(os.listdir(base)):
            d = os.path.join(base, n)
            if os.path.isfile(os.path.join(d, "caso.json")):
                try:
                    fuori.append(cls(d))
                except Exception:            # noqa: BLE001
                    pass
        return fuori

    def _carica(self):
        p = os.path.join(self.dir, "caso.json")
        if os.path.isfile(p):
            try:
                self.meta = json.load(open(p, encoding="utf-8"))
            except (OSError, ValueError):
                self.meta = {}

    def _salva(self):
        with open(os.path.join(self.dir, "caso.json"), "w", encoding="utf-8") as f:
            json.dump(self.meta, f, indent=2, ensure_ascii=False)

    # --- catena di custodia ---------------------------------------------
    @property
    def registro(self):
        return os.path.join(self.dir, "catena-di-custodia.log")

    def registra(self, azione, dettagli=""):
        """Aggiunge una riga al registro. APPEND-ONLY: non esiste una funzione
        per cancellare o modificare righe, di proposito."""
        riga = "%s\t%s\t%s\n" % (ora_utc(), azione, dettagli.replace("\n", " | "))
        with open(self.registro, "a", encoding="utf-8") as f:
            f.write(riga)
        return riga

    def righe_registro(self):
        try:
            with open(self.registro, encoding="utf-8") as f:
                return [r.rstrip("\n").split("\t", 2) for r in f if r.strip()]
        except OSError:
            return []

    def nota(self, testo):
        self.registra("NOTA", testo)

    # --- acquisizione ----------------------------------------------------
    def acquisisci(self, device, descrizione="", progresso=None):
        """Acquisisce un dispositivo in formato E01 con ewfacquire.

        E01 e non un .img grezzo perche' incorpora NELL'IMMAGINE i metadati del
        caso e gli hash, e si verifica con ewfverify. Un .img con l'hash in un
        file a fianco e' molto piu' fragile da difendere.

        Il device viene prima messo in sola lettura a livello di blocco: la
        protezione deve valere DURANTE la copia, non solo prima.
        """
        if not have("ewfacquire"):
            return (False, "ewfacquire non disponibile (pacchetto libewf)")
        nome = os.path.basename(device).replace("/", "_")
        target = os.path.join(self.dir, "immagini", nome)
        log = target + ".log"

        # write-block a livello di blocco, per tutta la durata dell acquisizione
        bloccato = False
        if have("nxs-writeblock"):
            r = subprocess.run(_priv(["nxs-writeblock", "lock", device]),
                               capture_output=True, text=True)
            bloccato = (r.returncode == 0)
        self.registra("WRITE-BLOCK", "%s -> %s" % (device, "attivo" if bloccato else "NON attivabile"))

        self.registra("ACQUISIZIONE INIZIO",
                      "device=%s formato=E01 strumento=%s" % (device, versione("ewfacquire")))
        cmd = _priv([
            "ewfacquire", "-u",                 # non interattivo
            "-t", target,
            "-f", "encase6",
            "-c", "deflate:best",
            "-d", "sha256",                     # oltre a MD5, che e il default
            "-C", self.meta.get("riferimento") or self.meta.get("nome", "caso"),
            "-D", descrizione or ("Acquisizione di %s" % device),
            "-e", self.meta.get("operatore", "-"),
            "-E", nome,
            "-N", self.meta.get("note", "") or "-",
            "-l", log,
            device,
        ])
        ok, uscita = _esegui(cmd, progresso)
        if not ok:
            self.registra("ACQUISIZIONE FALLITA", uscita[-400:])
            return (False, uscita[-400:] or "ewfacquire fallito")

        immagine = target + ".E01"
        if not os.path.exists(immagine):
            trovate = [f for f in os.listdir(os.path.join(self.dir, "immagini"))
                       if f.startswith(nome) and f.endswith(".E01")]
            immagine = os.path.join(self.dir, "immagini", trovate[0]) if trovate else ""
        hashes = _hash_da_log(log)
        self.registra("ACQUISIZIONE COMPLETATA",
                      "immagine=%s md5=%s sha256=%s"
                      % (os.path.basename(immagine), hashes.get("MD5", "-"), hashes.get("SHA256", "-")))
        return (True, immagine)

    def verifica(self, immagine, progresso=None):
        """Riverifica l'immagine con ewfverify: ricalcola gli hash e li confronta
        con quelli scritti dentro l'immagine al momento dell'acquisizione."""
        if not have("ewfverify"):
            return (False, "ewfverify non disponibile")
        self.registra("VERIFICA INIZIO", os.path.basename(immagine))
        ok, uscita = _esegui(["ewfverify", "-d", "sha256", immagine], progresso)
        esito = "INTEGRA" if ok else "NON CORRISPONDENTE"
        self.registra("VERIFICA ESITO", "%s -> %s" % (os.path.basename(immagine), esito))
        return (ok, uscita[-600:])

    # --- analisi ----------------------------------------------------------
    def analizza(self, immagine, progresso=None):
        """Partizioni (mmls), elenco file compresi i cancellati (fls) e TIMELINE
        (mactime). La timeline e' l'artefatto centrale di un accertamento: dice
        in che ordine sono successe le cose."""
        if not have("mmls"):
            return (False, "sleuthkit non disponibile")
        ana = os.path.join(self.dir, "analisi")
        os.makedirs(ana, exist_ok=True)
        base = os.path.basename(immagine).split(".")[0]

        def _scrivi(nome, argv):
            p = os.path.join(ana, nome)
            try:
                r = subprocess.run(argv, capture_output=True, text=True, timeout=1800)
                with open(p, "w", encoding="utf-8", errors="replace") as f:
                    f.write(r.stdout or "")
                    if r.returncode != 0 and r.stderr:
                        f.write("\n--- stderr ---\n" + r.stderr)
                return p, r.returncode == 0
            except (OSError, subprocess.SubprocessError) as e:
                return p, False

        self.registra("ANALISI INIZIO",
                      "immagine=%s strumento=%s" % (os.path.basename(immagine), versione("mmls")))
        if progresso:
            progresso("Tabella delle partizioni (mmls)...")
        _scrivi("%s-partizioni.txt" % base, ["mmls", immagine])

        if progresso:
            progresso("Elenco file, cancellati compresi (fls)...")
        corpo = os.path.join(ana, "%s-corpo.body" % base)
        try:
            r = subprocess.run(["fls", "-r", "-m", "/", immagine],
                               capture_output=True, text=True, timeout=3600)
            with open(corpo, "w", encoding="utf-8", errors="replace") as f:
                f.write(r.stdout or "")
        except (OSError, subprocess.SubprocessError):
            pass

        tl = os.path.join(ana, "%s-timeline.txt" % base)
        if os.path.getsize(corpo) if os.path.exists(corpo) else 0:
            if progresso:
                progresso("Costruzione della timeline (mactime)...")
            try:
                r = subprocess.run(["mactime", "-b", corpo, "-d"],
                                   capture_output=True, text=True, timeout=3600)
                with open(tl, "w", encoding="utf-8", errors="replace") as f:
                    f.write(r.stdout or "")
            except (OSError, subprocess.SubprocessError):
                pass

        n = 0
        try:
            with open(tl, encoding="utf-8", errors="replace") as f:
                n = sum(1 for _ in f)
        except OSError:
            pass
        self.registra("ANALISI COMPLETATA", "timeline=%d righe" % n)
        return (True, "timeline: %d righe" % n)

    def chiudi(self):
        self.meta["chiuso"] = ora_utc()
        self._salva()
        self.registra("CHIUSURA CASO", "")


def _esegui(cmd, progresso=None):
    """Esegue un comando lungo inoltrando l'avanzamento alla GUI."""
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, bufsize=1)
    except (OSError, subprocess.SubprocessError) as e:
        return (False, str(e))
    righe = []
    for riga in p.stdout:
        riga = riga.rstrip()
        righe.append(riga)
        if progresso and riga:
            progresso(riga)
    p.wait()
    return (p.returncode == 0, "\n".join(righe[-40:]))


def _hash_da_log(log):
    """Estrae MD5/SHA256 dal log di ewfacquire."""
    out = {}
    try:
        with open(log, encoding="utf-8", errors="replace") as f:
            for r in f:
                m = re.match(r"\s*(MD5|SHA1|SHA256) hash calculated over data:\s*(\S+)", r)
                if m:
                    out[m.group(1)] = m.group(2)
    except OSError:
        pass
    return out
