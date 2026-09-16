# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""Fase 2 - esecuzione CONFERMATA dei comandi proposti dall'agente.

Regole ferme (distro di sicurezza):
- L'agente non esegue nulla da solo. L'utente vede il comando ESATTO e conferma.
- L'esecuzione e' OFF di default (config.allow_exec); si abilita dal pannello IA.
- Ogni comando gira nella sandbox `nxs-ai-sandbox` (bubblewrap: root in sola
  lettura, home isolata, rete solo se serve). Timeout rigido.
- Blocklist di comandi distruttivi + rispetto del profilo (Forensics: nessuna
  scrittura su disco). Tutto registrato nell'audit.
"""
from __future__ import annotations

import re
import subprocess
import sys

from . import config

# --- comandi/pattern SEMPRE bloccati (rete di sicurezza oltre alla conferma) ---
_DANGER = [re.compile(p, re.I) for p in [
    r"\brm\s+-\w*[rf]", r"\bmkfs\b", r"\bwipefs\b", r"\bshred\b",
    r"\bdd\b", r"\bof\s*=\s*/dev/", r">\s*/dev/(sd|nvme|mmc|vd|mapper)",
    r"\bfdisk\b", r"\bsfdisk\b", r"\bparted\b", r"\bsgdisk\b",
    r"\bcryptsetup\b.*\b(luksFormat|erase|luksKillSlot)",
    r"\bchmod\s+-R\s+0*777\s+/", r"\bchown\s+-R\b.*\s+/\s*$",
    r":\s*\(\s*\)\s*\{", r"\bmkfs\.", r"\bblkdiscard\b",
    r"\b(halt|poweroff|reboot|init\s+0|shutdown)\b",
    r"\bmv\b.*\s+/(bin|sbin|etc|usr|boot|lib)\b",
    r"/dev/(sd|nvme|mmc|vd)[a-z0-9]*",   # riferimenti a dischi reali
    r"\bnxs-panic\b",
]]

# tool che richiedono rete: la sandbox va aperta con --net (mostrato all'utente)
_NET = {
    "nmap", "masscan", "naabu", "rustscan", "httpx", "curl", "wget", "dig",
    "host", "nslookup", "whois", "ping", "fping", "hping3", "nc", "ncat",
    "netcat", "socat", "ssh", "scp", "ftp", "telnet", "nikto", "ffuf",
    "gobuster", "feroxbuster", "dirb", "sqlmap", "wpscan", "amass", "subfinder",
    "theharvester", "gau", "waybackurls", "uncover", "tlsx", "katana",
    "dnsx", "dnsrecon", "fierce", "arp-scan", "netdiscover", "smbclient",
    "enum4linux", "crackmapexec", "nxc", "tor", "proxychains", "torsocks",
    "git", "pip", "pip3", "apk", "wpscan", "nuclei", "interactsh-client",
}


def extract_commands(reply: str) -> list[str]:
    """Estrae i comandi dai blocchi ``` della risposta (una riga = un comando;
    scarta commenti, prompt e righe vuote)."""
    cmds: list[str] = []
    for block in re.findall(r"```[a-zA-Z0-9]*\n(.*?)```", reply, re.S):
        for line in block.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            s = re.sub(r"^\$\s+", "", s)        # togli prompt "$ "
            s = re.sub(r"^(nexus@\S+[:~][^\$#]*[\$#]\s+)", "", s)
            if s:
                cmds.append(s)
    # dedup mantenendo l'ordine
    seen, out = set(), []
    for c in cmds:
        if c not in seen:
            seen.add(c); out.append(c)
    return out


def _active_profile() -> str:
    try:
        sys.path.insert(0, "/usr/local/lib")
        from nxs_profiles import model
        return model.current_profile()
    except Exception:                          # noqa: BLE001
        return "base"


def classify(cmd: str) -> tuple[str, bool, str]:
    """Ritorna (livello, needs_net, motivo).
    livello: 'blocked' | 'ok'. needs_net True se serve la rete."""
    for rx in _DANGER:
        if rx.search(cmd):
            return ("blocked", False,
                    "comando potenzialmente distruttivo o su disco/sistema reale")
    # in Forensics niente scrittura verso dispositivi/mount (oltre alla blocklist)
    if _active_profile() == "forensics" and re.search(r"\b(mount\b(?!.*\bro\b)|umount|mkfs|dd)\b", cmd):
        return ("blocked", False,
                "profilo Forensics attivo: niente operazioni di scrittura sui dischi")
    first = re.split(r"[\s|;&]+", cmd.strip())
    tools = {re.sub(r"^.*/", "", t) for t in first if t}
    needs_net = bool(tools & _NET) or "http://" in cmd or "https://" in cmd
    return ("ok", needs_net, "")


def run_confirmed(cmd: str, needs_net: bool, log=print, timeout: int = 300) -> tuple[int, str]:
    """Esegue il comando (gia' confermato) nella sandbox bubblewrap. Ritorna
    (codice_uscita, output). Mostra l'output via `log`; registra nell'audit."""
    sandbox = ["nxs-ai-sandbox"]
    if needs_net:
        sandbox.append("--net")
    sandbox += ["--", "sh", "-lc", cmd]
    log(f"[IA] eseguo in sandbox ({'con' if needs_net else 'senza'} rete): {cmd}")
    try:
        p = subprocess.run(sandbox, capture_output=True, text=True, timeout=timeout)
        out = (p.stdout or "") + (p.stderr or "")
        rc = p.returncode
    except subprocess.TimeoutExpired:
        out, rc = f"(timeout dopo {timeout}s)", 124
    except FileNotFoundError:
        out, rc = "nxs-ai-sandbox non disponibile.", 127
    _audit(cmd, out)
    if out.strip():
        log(out.rstrip())
    log(f"[IA] (uscita: {rc})")
    return rc, out


def _audit(cmd: str, output: str) -> None:
    import datetime as _dt
    try:
        config.CONF_DIR.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().isoformat(timespec="seconds")
        with open(config.AUDIT, "a") as f:
            f.write(f"[{ts}] EXEC: {cmd}\n")
            f.write(f"[{ts}] EXIT/OUT: {output[:400]}\n")
    except Exception:                          # noqa: BLE001
        pass
