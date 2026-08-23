"""Esecutore delle procedure guidate.

run_wizard() e' il "regista": valida i campi, sceglie modalita'/opzioni/stealth,
prepara una cartella reperti sotto ~/NexusSec-loot/, e per ogni step attivo
installa-se-serve il tool (nxs_profiles.isolation) e lo esegue catturando
l'output riga per riga (lo inoltra a `emit` e lo salva in report.log).

Novita':
  - STEALTH (ON/OFF): dove possibile instrada il tool via Tor (torsocks/
    proxychains sul socket 9050), con esito ONESTO per step:
      anon="tor"       -> incapsulato in Tor  (badge "via Tor");
      anon="raw"       -> pacchetti raw/ICMP: NON anonimizzabile (badge);
      anon="container" -> gira in container: non instradabile da Tor host (badge);
      anon="local"     -> offline (forensics): stealth ininfluente;
      skip=true        -> lo step viene saltato quando stealth e' ON.
    Se stealth e' ON ma Tor non e' disponibile, gli step "tor" vengono SALTATI
    (non si esegue in chiaro per non esporre l'IP).
  - CATENA DATI: uno step puo' 'produces' una lista estratta dal suo output
    (extract: nmap_up/subdomains/urls/hosts/lines/regex:PATTERN); il risultato
    va in {loot}/<var>.txt ed e' esposto agli step successivi come {var}
    (percorso file) e {var}_n (quanti). Uno step che usa un {var} vuoto si salta.

Nessuna dipendenza GTK: usabile da CLI/headless.
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import socket
import subprocess
import time
from pathlib import Path

from nxs_profiles import isolation

from . import recipes

TOR_HOST, TOR_PORT = "127.0.0.1", 9050


# ---------------------------------------------------------------- stealth/Tor
def _tor_up() -> bool:
    try:
        with socket.create_connection((TOR_HOST, TOR_PORT), timeout=0.6):
            return True
    except OSError:
        return False


def _ensure_tor(out) -> bool:
    """Tor raggiungibile su 9050? Se no prova ad avviarne uno utente."""
    if _tor_up():
        return True
    torbin = shutil.which("tor")
    if not torbin:
        return False
    data = Path.home() / ".nxs-tor"
    data.mkdir(parents=True, exist_ok=True)
    out("[*] avvio Tor (SOCKS 9050)...")
    try:
        subprocess.Popen([torbin, "--SocksPort", str(TOR_PORT),
                          "--DataDirectory", str(data)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return False
    for _ in range(30):            # ~15s
        if _tor_up():
            return True
        time.sleep(0.5)
    return False


def _stealth_wrapper():
    """Prefisso che instrada un comando via Tor: torsocks o proxychains."""
    if shutil.which("torsocks"):
        return ["torsocks"]
    if shutil.which("proxychains"):
        return ["proxychains", "-q"]
    if shutil.which("proxychains4"):
        return ["proxychains4", "-q"]
    return None


def _step_anon(step: dict) -> tuple[str, str, bool]:
    """(anon, flags-stealth, skip) di uno step. Default anon='tor'."""
    s = step.get("stealth") or {}
    return s.get("anon", "tor"), s.get("flags", ""), bool(s.get("skip"))


# ------------------------------------------------------------- estrattori dati
def _extract(kind: str, text: str) -> list[str]:
    kind = kind or "lines"
    if kind.startswith("regex:"):
        pat = kind[6:]
        try:
            return [m.group(1) if m.groups() else m.group(0)
                    for m in re.finditer(pat, text)]
        except re.error:
            return []
    if kind == "nmap_up":
        ips = re.findall(
            r"Nmap scan report for (?:[^\n(]*\()?([0-9]{1,3}(?:\.[0-9]{1,3}){3})",
            text)
        ips += re.findall(r"Host:\s+([0-9.]+).*Status:\s+Up", text)
        return list(dict.fromkeys(ips))
    if kind == "subdomains":
        return list(dict.fromkeys(
            re.findall(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b", text, re.I)))
    if kind == "urls":
        return list(dict.fromkeys(re.findall(r"https?://[^\s'\"<>]+", text)))
    # "hosts"/"lines"/default: ogni riga non vuota
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _stream(cmd: list[str], out) -> tuple[int, str]:
    """Esegue cmd inoltrando stdout+stderr a `out` e accumulandolo. -> (rc, testo)."""
    buf: list[str] = []
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, bufsize=1)
    except (FileNotFoundError, OSError) as e:
        out(f"[!] avvio fallito: {e}")
        return 127, ""
    assert p.stdout is not None
    for line in p.stdout:
        line = line.rstrip("\n")
        out(line)
        buf.append(line)
    p.wait()
    return p.returncode, "\n".join(buf)


_BADGE = {"tor": "[STEALTH] via Tor",
          "raw": "[STEALTH] NON anonimizzabile (pacchetti raw)",
          "container": "[STEALTH] non anonimizzabile (gira in container)",
          "local": "[STEALTH] locale (nessun traffico di rete)"}


def run_wizard(wid: str, values: dict, emit, stop=None,
               mode=None, options=None, stealth=False) -> bool:
    """Esegue il wizard `wid`.

    emit(str), stop()->bool, mode=<id modalita'>, options=<lista id opzioni>,
    stealth=<bool> (anonimato via Tor dove possibile). Ritorna True se tutti gli
    step eseguiti sono andati a buon fine.
    """
    wiz = recipes.get(wid)
    if not wiz:
        emit(f"[!] procedura sconosciuta: {wid}")
        return False

    for f in wiz.get("fields", []):
        if f.get("required") and not (values.get(f["key"]) or "").strip():
            emit(f"[!] campo obbligatorio mancante: {f['label']}")
            return False

    mode_id = mode if mode is not None else recipes.default_mode(wiz)
    if wiz.get("modes") and mode_id not in {m.get("id") for m in wiz["modes"]}:
        mode_id = recipes.default_mode(wiz)
    active_opts = set(options if options is not None
                      else recipes.default_options(wiz))
    mvars = recipes.mode_vars(wiz, mode_id)

    steps = [s for s in wiz.get("steps", [])
             if recipes.step_active(s, mode_id, active_opts, stealth)]

    run_dir = isolation.LOOT / f"{wid}-{time.strftime('%Y%m%d-%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    logf = open(run_dir / "report.log", "w")

    def out(line: str = ""):
        emit(line)
        logf.write(line + "\n")
        logf.flush()

    out(f"=== {wiz.get('name', wid)} ===")
    if wiz.get("modes"):
        mlabel = next((m.get("label", mode_id) for m in wiz["modes"]
                       if m.get("id") == mode_id), mode_id)
        out(f"Modalita': {mlabel}")
    if wiz.get("options"):
        on = [o.get("label", o["id"]) for o in wiz["options"]
              if o["id"] in active_opts] or ["(nessuna)"]
        out(f"Opzioni attive: {', '.join(on)}")
    out(f"Stealth: {'ON (anonimato via Tor dove possibile)' if stealth else 'OFF'}")
    out(f"Step da eseguire: {len(steps)}")
    out(f"Reperti e log in: {run_dir}")

    # Predisposizione stealth: serve Tor su 9050 + un wrapper (torsocks/proxychains).
    wrapper = None
    tor_ok = False
    if stealth:
        needs_tor = any(_step_anon(s)[0] == "tor" for s in steps)
        if needs_tor:
            tor_ok = _ensure_tor(out)
            wrapper = _stealth_wrapper()
            if not tor_ok:
                out("[!] Tor non disponibile: gli step anonimizzabili verranno "
                    "SALTATI per non esporre il tuo IP reale.")
            elif wrapper is None:
                out("[!] torsocks/proxychains assenti: impossibile instradare "
                    "via Tor; gli step anonimizzabili verranno saltati.")

    produced: dict = {}
    ok_all = True
    try:
        for idx, st in enumerate(steps, 1):
            if stop and stop():
                out("")
                out("[!] interrotto dall'utente.")
                return False
            tool = st["tool"]
            desc = st.get("desc", tool)
            raw_args = st.get("args", "")

            subst = dict(values)
            subst.update(mvars)
            subst.update(produced)
            subst["outdir"] = str(run_dir / f"out{idx}")
            subst["loot"] = str(run_dir)

            # auto-skip: usa una lista prodotta ma vuota?
            skip_empty = None
            for ref in set(re.findall(r"{([a-zA-Z0-9_]+)}", raw_args)):
                if produced.get(f"{ref}_n") == "0":
                    skip_empty = ref
                    break

            anon, sflags, _sskip = _step_anon(st)  # only/skip gia' pre-filtrati
            out("")
            out(f"--- [{idx}/{len(steps)}] {desc}")

            if skip_empty:
                out(f"[=] salto: la lista '{skip_empty}' e' vuota.")
                continue

            args = raw_args
            prefix: list[str] = []
            if stealth:
                out(_BADGE.get(anon, ""))
                if anon == "tor":
                    if not (tor_ok and wrapper):
                        out("[=] salto: non instradabile via Tor.")
                        continue
                    prefix = list(wrapper)
                if sflags:
                    args = (args + " " + sflags).strip()

            try:
                fargs = args.format(**subst)
            except KeyError as e:
                out(f"[!] segnaposto {e} non disponibile, salto.")
                ok_all = False
                continue

            out(f"    {' '.join(prefix)} {tool} {fargs}".strip())
            if not isolation.is_installed(tool):
                out(f"[*] installo {tool} ({isolation._method(tool)})...")
                if not isolation.install(tool, out):
                    out(f"[!] installazione di {tool} fallita: salto questo step.")
                    ok_all = False
                    continue

            cmd = isolation.build_cmd(
                tool, shlex.split(fargs) if fargs else [],
                interactive=False, log=out)
            if not cmd:
                out(f"[!] {tool}: impossibile costruire il comando.")
                ok_all = False
                continue
            cmd = prefix + cmd

            rc, text = _stream(cmd, out)
            out(f"[=] {tool} terminato (codice {rc}).")
            if rc != 0:
                ok_all = False

            # catena dati: cattura l'output prodotto per gli step successivi
            prod = st.get("produces")
            if prod and prod.get("var"):
                var = prod["var"]
                src = prod.get("from", "stdout")
                if src == "stdout":
                    data_text = text
                else:
                    try:
                        data_text = Path(src.format(**subst)).read_text()
                    except OSError:
                        data_text = ""
                items = _extract(prod.get("extract", "lines"), data_text)
                pf = run_dir / f"{var}.txt"
                pf.write_text(("\n".join(items) + "\n") if items else "")
                produced[var] = str(pf)
                produced[f"{var}_n"] = str(len(items))
                out(f"[+] prodotto '{var}': {len(items)} elementi -> {pf}")

        out("")
        out("=== Procedura terminata. ===")
        out(f"Risultati salvati in {run_dir}")
    finally:
        logf.close()
    return ok_all
