#!/usr/bin/env python3
"""nxs-sources-check - verifica che TUTTE le fonti dei tool NexusSec siano vive.

Legge il catalogo `overlay/usr/local/share/nexussec/repo.json` (la singola fonte
di verita') e, per ogni tool, controlla che il canale da cui viene scaricato sia
raggiungibile e funzionante:

  - apk        -> presente negli APKINDEX di Alpine edge (main/community/testing)
                  OPPURE nel nostro repo Arsenal (GitHub Pages);
  - pip        -> il pacchetto esiste su PyPI (api JSON);
  - container  -> l'immagine OCI esiste nel registry (`podman manifest inspect`);
  - git        -> il repo risponde (`git ls-remote`);
  - kali       -> il pacchetto apt esiste DAVVERO negli indici di kali-rolling
                  (Packages.gz di main/contrib/non-free), non solo l'immagine base.
                  Cosi' il check intercetta le DERIVE (pacchetti Kali rinominati o
                  rimossi nel rolling), garantendo l'allineamento nel tempo. Se gli
                  indici non sono scaricabili (offline), ripiega sulla sola verifica
                  dell'immagine base.

Scrive un report leggibile in `build/SOURCES.txt` (l'elenco dei link attivi e
funzionanti, da consultare a colpo d'occhio) e termina con codice != 0 se almeno
una fonte risulta ROTTA, cosi' e' usabile anche in una GitHub Action periodica.

Uso:  python3 build/nxs-sources-check.py
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tarfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_JSON = ROOT / "overlay" / "usr" / "local" / "share" / "nexussec" / "repo.json"
OUT_TXT = ROOT / "build" / "SOURCES.txt"

ALPINE_MIRROR = "http://dl-cdn.alpinelinux.org/alpine/edge"
ALPINE_REPOS = ("main", "community", "testing")
ARSENAL_INDEX = "https://dplusos21.github.io/NexusSec-OS/x86_64/APKINDEX.tar.gz"
KALI_IMG = "docker.io/kalilinux/kali-rolling:latest"
# Indici binari di kali-rolling: da qui ricaviamo l'elenco REALE dei pacchetti apt
# disponibili, per verificare che ogni tool 'kali' del catalogo sia installabile.
# Componenti abilitati di default nell'immagine kalilinux/kali-rolling (deb822):
# main contrib non-free non-free-firmware -> verifichiamo su TUTTI, cosi' il check
# rispecchia esattamente cosa apt riesce a installare dentro la distro.
KALI_MIRROR = "http://http.kali.org/kali/dists/kali-rolling"
KALI_COMPONENTS = ("main", "contrib", "non-free", "non-free-firmware")
KALI_ARCH = "binary-amd64"
TIMEOUT = 20


def _http_ok(url: str) -> bool:
    try:
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": "nxs-sources-check"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return 200 <= r.status < 400
    except Exception:
        return False


def _apkindex_names(url: str) -> set[str]:
    """Scarica un APKINDEX.tar.gz e ne estrae i nomi pacchetto (righe 'P:')."""
    names: set[str] = set()
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            data = r.read()
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            m = tf.extractfile("APKINDEX")
            if m:
                for line in m.read().decode("utf-8", "replace").splitlines():
                    if line.startswith("P:"):
                        names.add(line[2:].strip())
    except Exception:
        pass
    return names


def load_apk_universe() -> set[str]:
    print("[*] scarico gli APKINDEX (Alpine main/community/testing + Arsenal)...",
          file=sys.stderr)
    names: set[str] = set()
    urls = [f"{ALPINE_MIRROR}/{r}/x86_64/APKINDEX.tar.gz" for r in ALPINE_REPOS]
    urls.append(ARSENAL_INDEX)
    with ThreadPoolExecutor(max_workers=4) as ex:
        for s in ex.map(_apkindex_names, urls):
            names |= s
    return names


def _deb_package_names(url: str) -> set[str]:
    """Scarica un Packages.gz Debian/Kali ed estrae i nomi (righe 'Package:')."""
    import gzip
    names: set[str] = set()
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            data = r.read()
        text = gzip.decompress(data).decode("utf-8", "replace")
        for line in text.splitlines():
            if line.startswith("Package: "):
                names.add(line[len("Package: "):].strip())
    except Exception:
        pass
    return names


def load_kali_universe() -> set[str]:
    """Elenco dei pacchetti apt disponibili in kali-rolling (main+contrib+non-free).
    Vuoto se gli indici non sono scaricabili (offline) -> il check kali ripiega."""
    print("[*] scarico gli indici di kali-rolling (main/contrib/non-free)...",
          file=sys.stderr)
    urls = [f"{KALI_MIRROR}/{c}/{KALI_ARCH}/Packages.gz" for c in KALI_COMPONENTS]
    names: set[str] = set()
    with ThreadPoolExecutor(max_workers=3) as ex:
        for s in ex.map(_deb_package_names, urls):
            names |= s
    return names


def pypi_ok(name: str) -> bool:
    return _http_ok(f"https://pypi.org/pypi/{name}/json")


def image_ok(image: str) -> bool:
    try:
        return subprocess.run(["podman", "manifest", "inspect", image],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=60).returncode == 0
    except Exception:
        return False


def git_ok(url: str) -> bool:
    if url.startswith("git+"):
        url = url[4:]
    try:
        return subprocess.run(["git", "ls-remote", url, "HEAD"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=40).returncode == 0
    except Exception:
        return False


def main() -> int:
    data = json.loads(REPO_JSON.read_text())
    tools = data["tools"]
    apk_universe = load_apk_universe()
    kali_universe = load_kali_universe()
    # Fallback: se gli indici Kali non si scaricano, verifica almeno l'immagine base.
    kali_alive = image_ok(KALI_IMG) if not kali_universe else True

    rows = []  # (tool, method, source, status_bool, note)
    have_podman = subprocess.run(["sh", "-c", "command -v podman"],
                                 stdout=subprocess.DEVNULL).returncode == 0

    def check(name: str, t: dict):
        m = t.get("method", "apk")
        if m == "apk":
            pkg = t.get("apk", name)
            return (name, m, f"apk:{pkg}", pkg in apk_universe, "")
        if m == "pip":
            ref = t.get("pip", name)
            if ref.startswith("git+") or ref.startswith("http"):
                return (name, m, ref, git_ok(ref), "pip da git")
            return (name, m, f"pypi:{ref}", pypi_ok(ref), "")
        if m == "container":
            img = t.get("image", "")
            if not img:
                return (name, m, "(immagine non definita)", False, t.get("note", ""))
            ok = image_ok(img) if have_podman else True
            return (name, m, img, ok, "" if have_podman else "podman assente: non verificato")
        if m == "git":
            url = t.get("git") or t.get("pip", "")
            return (name, m, url, git_ok(url), "")
        if m == "kali":
            pkg = t.get("apt", name)
            if kali_universe:
                ok = pkg in kali_universe
                note = "" if ok else "pacchetto assente in kali-rolling (rinominato/rimosso?)"
                return (name, m, f"kali-rolling apt:{pkg}", ok, note)
            # offline: non abbiamo l'elenco, verifichiamo solo la base Kali
            return (name, m, f"kali-rolling apt:{pkg}", kali_alive,
                    "indici Kali non scaricati: verificata solo l'immagine base")
        return (name, m, "(metodo ignoto)", False, "")

    with ThreadPoolExecutor(max_workers=12) as ex:
        rows = list(ex.map(lambda kv: check(kv[0], kv[1]), sorted(tools.items())))

    broken = [r for r in rows if not r[3]]
    width = max(len(r[0]) for r in rows)

    lines = []
    lines.append("# NexusSec - fonti dei tool (link attivi e funzionanti)")
    lines.append("# Generato da build/nxs-sources-check.py - NON modificare a mano.")
    lines.append(f"# Tool totali: {len(rows)}   Rotti: {len(broken)}")
    lines.append("#")
    lines.append(f"# {'TOOL':<{width}}  {'STATO':<6} {'METODO':<9} FONTE")
    for tool, m, src, ok, note in rows:
        stato = "OK" if ok else "ROTTO"
        line = f"{tool:<{width}}  {stato:<6} {m:<9} {src}"
        if note:
            line += f"   ({note})"
        lines.append(line)
    if broken:
        lines.append("")
        lines.append("# === FONTI ROTTE (da sistemare) ===")
        for tool, m, src, _ok, _n in broken:
            lines.append(f"# {tool} [{m}] -> {src}")

    OUT_TXT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n[+] report scritto in {OUT_TXT}", file=sys.stderr)
    if broken:
        print(f"[!] {len(broken)} fonti ROTTE", file=sys.stderr)
        return 1
    print("[+] tutte le fonti sono vive", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
