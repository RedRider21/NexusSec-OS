"""Relazione HTML del caso - generata automaticamente.

Perche' HTML e non PDF: si apre con nxs-browser (gia' nella distro), si stampa
in PDF dal browser quando serve consegnarla, e non aggiunge dipendenze. Il file
e' autonomo (CSS incorporato): si puo' copiare su una chiavetta e resta leggibile
ovunque, anche fra anni.

La relazione NON e' un riassunto discorsivo: e' il verbale. Riporta i metadati
del caso, la catena di custodia integrale, gli hash di acquisizione e di
verifica, e i risultati dell'analisi. Chi la legge deve poter rifare i passi.
"""
from __future__ import annotations

import html
import os

from nxs_case import model

_CSS = """
:root{--bg:#050a14;--pan:#0a1a26;--ink:#c8f5ff;--mut:#5a8a9a;--acc:#00e5ff;
      --line:#1a3a52;--alr:#ff5a8a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
     font:15px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:26px;margin:0 0 4px;letter-spacing:.02em}
h2{font-size:15px;text-transform:uppercase;letter-spacing:.12em;color:var(--acc);
   margin:34px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--line)}
.sub{color:var(--mut);margin:0 0 24px}
table{width:100%;border-collapse:collapse;font-size:14px;margin:10px 0}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);
      vertical-align:top}
th{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--mut)}
td.k{color:var(--acc);white-space:nowrap;font-family:ui-monospace,monospace}
pre{background:var(--pan);border:1px solid var(--line);border-radius:6px;
    padding:12px;overflow-x:auto;font-size:12.5px;max-height:460px}
.nota{background:var(--pan);border-left:3px solid var(--acc);padding:10px 14px;
      border-radius:0 6px 6px 0;margin:14px 0;color:var(--mut)}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;
      word-break:break-all}
footer{margin-top:40px;padding-top:14px;border-top:1px solid var(--line);
       color:var(--mut);font-size:12.5px}
@media print{body{background:#fff;color:#000}
  .wrap{max-width:none}pre{max-height:none;background:#f6f6f6;color:#000}
  h2{color:#000}td.k{color:#000}.nota{background:#f6f6f6;color:#000}}
"""


def _e(x):
    return html.escape(str(x if x is not None else "-"))


def _tabella(righe):
    out = ["<table><tbody>"]
    for k, v in righe:
        out.append("<tr><td class='k'>%s</td><td>%s</td></tr>" % (_e(k), _e(v)))
    out.append("</tbody></table>")
    return "".join(out)


def _file_txt(percorso, max_righe=300):
    """Incorpora un file di analisi, troncandolo: una timeline puo' avere
    milioni di righe e il file completo resta comunque nella cartella."""
    if not percorso or not os.path.isfile(percorso):
        return None
    righe = []
    try:
        with open(percorso, encoding="utf-8", errors="replace") as f:
            for i, r in enumerate(f):
                if i >= max_righe:
                    righe.append("\n[...] troncato: il file completo e' in %s"
                                 % os.path.basename(percorso))
                    break
                righe.append(r.rstrip("\n"))
    except OSError:
        return None
    return "\n".join(righe)


def genera(caso):
    """Scrive relazione.html nella cartella del caso. Ritorna il percorso."""
    m = caso.meta
    p = []
    p.append("<!doctype html><html lang='it'><head><meta charset='utf-8'>")
    p.append("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    p.append("<title>Relazione — %s</title><style>%s</style></head><body><div class='wrap'>"
             % (_e(m.get("nome", "caso")), _CSS))

    p.append("<h1>Relazione tecnica — %s</h1>" % _e(m.get("nome", "-")))
    p.append("<p class='sub'>Generata il %s (UTC) da NexusSec OS</p>" % _e(model.ora_utc()))

    p.append("<h2>Dati del caso</h2>")
    p.append(_tabella([
        ("Denominazione", m.get("nome")),
        ("Operatore", m.get("operatore")),
        ("Riferimento", m.get("riferimento") or "-"),
        ("Apertura (UTC)", m.get("aperto")),
        ("Chiusura (UTC)", m.get("chiuso") or "caso ancora aperto"),
        ("Cartella", caso.dir),
    ]))
    if m.get("note"):
        p.append("<div class='nota'>%s</div>" % _e(m["note"]))

    # --- reperti acquisiti ------------------------------------------------
    imgdir = os.path.join(caso.dir, "immagini")
    immagini = sorted(f for f in os.listdir(imgdir)) if os.path.isdir(imgdir) else []
    e01 = [f for f in immagini if f.endswith(".E01")]
    p.append("<h2>Reperti acquisiti</h2>")
    if not e01:
        p.append("<p class='sub'>Nessuna acquisizione registrata.</p>")
    for f in e01:
        percorso = os.path.join(imgdir, f)
        dim = os.path.getsize(percorso) if os.path.exists(percorso) else 0
        h = model._hash_da_log(os.path.join(imgdir, f.rsplit(".", 1)[0] + ".log"))
        p.append("<h3 class='mono'>%s</h3>" % _e(f))
        p.append(_tabella([
            ("Dimensione", "%.2f MiB" % (dim / 1048576.0)),
            ("MD5", h.get("MD5", "-")),
            ("SHA-256", h.get("SHA256", "-")),
            ("Formato", "EWF/E01 (Expert Witness) — verificabile con ewfverify"),
        ]))

    # --- catena di custodia ----------------------------------------------
    p.append("<h2>Catena di custodia</h2>")
    p.append("<p class='sub'>Registro append-only: ogni riga e' stata scritta "
             "automaticamente dallo strumento al momento dell'operazione.</p>")
    righe = caso.righe_registro()
    if righe:
        p.append("<table><thead><tr><th>Quando (UTC)</th><th>Azione</th>"
                 "<th>Dettagli</th></tr></thead><tbody>")
        for r in righe:
            quando = r[0] if len(r) > 0 else "-"
            azione = r[1] if len(r) > 1 else "-"
            dett = r[2] if len(r) > 2 else ""
            p.append("<tr><td class='k'>%s</td><td>%s</td><td class='mono'>%s</td></tr>"
                     % (_e(quando), _e(azione), _e(dett)))
        p.append("</tbody></table>")
    else:
        p.append("<p class='sub'>Registro vuoto.</p>")

    # --- analisi -----------------------------------------------------------
    anadir = os.path.join(caso.dir, "analisi")
    p.append("<h2>Analisi</h2>")
    trovato = False
    if os.path.isdir(anadir):
        for nome, titolo in (("-partizioni.txt", "Tabella delle partizioni (mmls)"),
                             ("-timeline.txt", "Cronologia delle attivita (mactime)")):
            for f in sorted(os.listdir(anadir)):
                if f.endswith(nome):
                    txt = _file_txt(os.path.join(anadir, f),
                                    300 if "timeline" in nome else 80)
                    if txt:
                        trovato = True
                        p.append("<h3>%s</h3><pre>%s</pre>" % (_e(titolo), _e(txt)))
    if not trovato:
        p.append("<p class='sub'>Nessuna analisi eseguita.</p>")

    # --- strumenti ---------------------------------------------------------
    p.append("<h2>Strumenti impiegati</h2>")
    p.append("<p class='sub'>Le versioni sono agli atti: risultati prodotti con "
             "versioni diverse non sono automaticamente confrontabili.</p>")
    p.append(_tabella([(t, model.versione(t)) for t in
                       ("ewfacquire", "ewfverify", "mmls", "fls", "mactime")
                       if model.have(t)]))

    p.append("<footer>NexusSec OS — relazione generata automaticamente. "
             "I file integrali (immagini E01, timeline completa, registro) "
             "si trovano nella cartella del caso.</footer>")
    p.append("</div></body></html>")

    dest = os.path.join(caso.dir, "relazione.html")
    with open(dest, "w", encoding="utf-8") as f:
        f.write("".join(p))
    caso.registra("RELAZIONE GENERATA", os.path.basename(dest))
    return dest
