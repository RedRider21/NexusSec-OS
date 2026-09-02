"""Gestione ed esecuzione dei tool NexusSec (base Alpine Linux).

Cinque metodi, scelti per tool in repo.json (campo 'method'):

- 'apk'       : pacchetto nativo Alpine. install = `apk add`; run dal PATH.
- 'pip'       : tool Python. install = `pipx install`; run dal PATH.
- 'container' : immagine OCI eseguita con **Podman** (daemonless, rootless).
                Adatto a tool pesanti o non in apk (Metasploit, ZAP, WPScan).
                install = `podman pull`; run = `podman run --rm -it ...`.
- 'git'       : clone del repo upstream + venv dedicato (quando il tool non e'
                un pacchetto PyPI installabile, es. metagoofil = solo script).
                install = git clone + python -m venv + pip install; run = launcher
                in ~/.local/bin che invoca lo script nel venv.
- 'kali'      : tool eseguito in un AMBIENTE Kali rolling CONDIVISO E PERSISTENTE.
                CANALE DURATURO per qualsiasi tool dell'arsenale Kali (~600+) non
                disponibile come apk/pip su Alpine (musl). La base kali-rolling si
                scarica UNA SOLA VOLTA; ogni tool si aggiunge con `apt install` a
                un'unica immagine che ACCUMULA (localhost/nxs-kali) e viene
                ricommittata -> lo strumento resta disponibile (persistente su
                disco). run = `podman run` in quell'ambiente condiviso.

ISOLAMENTO (regola base: il core del SO non si tocca):

- 'container'        -> gia' isolato per natura (namespace del container).
- 'apk' / 'pip'      -> sandbox **bubblewrap ATTIVA DI DEFAULT**: filesystem
                        di sistema in sola lettura (vedi _bwrap). Disattivabile
                        solo con NXS_ISOLATE=0 (debug).
- tool 'privileged'  -> ECCEZIONE: i tool che richiedono raw socket / monitor
                        mode / sniffing (nmap-SYN, masscan, aircrack, bettercap,
                        ettercap, responder, wifite) girano con privilegi e
                        senza bwrap (lo romperebbe), oppure container --privileged.
                        Il core resta protetto dalla natura live/RAM read-only.

Il codice resta semplice: e' un direttore d'orchestra sopra apk, pip e podman.
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path

from . import model

LOOT = Path(os.path.expanduser("~")) / "NexusSec-loot"   # output condiviso coi container
GIT_BASE = Path(os.path.expanduser("~")) / ".local" / "share" / "nexussec" / "git"
LOCAL_BIN = Path(os.path.expanduser("~")) / ".local" / "bin"
KALI_IMG = "docker.io/kalilinux/kali-rolling:latest"     # base Debian/Kali (scaricata UNA volta)

# Ambiente Kali CONDIVISO E PERSISTENTE: un'unica immagine che ACCUMULA i tool.
# Invece di un'immagine derivata per ogni tool (spreco: N copie della base ~450MB),
# manteniamo localhost/nxs-kali:latest e ci facciamo `apt install` dentro, poi la
# ricommittiamo. Cosi la base si scarica una sola volta e QUALSIASI tool/metapacchetto
# dell'arsenale Kali (~600+) e a un apt di distanza. Persiste su disco (installazione
# o persistenza live); l'elenco dei pacchetti gia dentro sta in un file di stato.
KALI_ENV = "localhost/nxs-kali:latest"
KALI_STATE = model.CONF_DIR / "kali_installed.txt"       # un pacchetto apt per riga


def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def priv(cmd: list[str]) -> list[str]:
    """Anteprone doas/sudo se serve (no-op se gia' root o assenti)."""
    if os.geteuid() == 0:
        return cmd
    if have("doas"):
        return ["doas"] + cmd
    if have("sudo"):
        return ["sudo"] + cmd
    return cmd


# ---------------------------------------------------------------- helper repo
def _method(tool: str) -> str:
    return (model.tool_data(tool).get("method") or "apk")


def _apk_name(tool: str) -> str | None:
    data = model.tool_data(tool)
    return data.get("apk", tool) if "apk" in data or _method(tool) == "apk" else None


def _image(tool: str) -> str:
    """Immagine container del tool. Se repo.json indica un 'digest'
    (sha256:...), l'immagine viene PINNATA per digest (integrita' della
    supply-chain: si esegue esattamente quel contenuto). Senza digest si usa
    il tag (comportamento rolling, adatto ai tool Kali sempre aggiornati)."""
    data = model.tool_data(tool)
    img = data.get("image", "")
    digest = data.get("digest", "")
    if img and digest and "@" not in img:
        base = img.split(":", 1)[0] if ":" in img.rsplit("/", 1)[-1] else img
        return "%s@%s" % (base, digest)
    return img


def _bin(tool: str) -> str:
    """Nome del comando eseguibile (puo' differire dal nome del tool/pacchetto:
    es. netexec -> nxc, enum4linux -> enum4linux-ng)."""
    return model.tool_data(tool).get("bin", tool)


# ---------------------------------------------------------------- stato
def _image_exists(img: str) -> bool:
    return bool(img) and have("podman") and subprocess.run(
        ["podman", "image", "exists", img],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def _kali_pkg(tool: str) -> str:
    """Pacchetto apt Kali del tool (campo 'apt', default = nome tool)."""
    return model.tool_data(tool).get("apt", tool)


def _kali_installed_pkgs() -> set[str]:
    """Pacchetti gia presenti nell'ambiente Kali condiviso (file di stato)."""
    try:
        return {ln.strip() for ln in KALI_STATE.read_text().splitlines() if ln.strip()}
    except OSError:
        return set()


def _kali_mark(pkg: str, present: bool) -> None:
    pkgs = _kali_installed_pkgs()
    pkgs.add(pkg) if present else pkgs.discard(pkg)
    try:
        KALI_STATE.parent.mkdir(parents=True, exist_ok=True)
        KALI_STATE.write_text("\n".join(sorted(pkgs)) + ("\n" if pkgs else ""))
    except OSError:
        pass


def is_installed(tool: str) -> bool:
    m = _method(tool)
    if m == "container":
        return _image_exists(_image(tool))
    if m == "kali":
        # installato = l'ambiente condiviso esiste E contiene gia il pacchetto.
        return _image_exists(KALI_ENV) and _kali_pkg(tool) in _kali_installed_pkgs()
    if m == "git":
        return have(_bin(tool)) or (LOCAL_BIN / _bin(tool)).exists()
    # apk / pip: il comando vive nel PATH una volta installato
    if have(_bin(tool)) or have(tool):
        return True
    if m == "apk":
        pkg = _apk_name(tool)
        if pkg and have("apk"):
            return subprocess.run(["apk", "info", "-e", pkg],
                                  stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL).returncode == 0
    return False


# ---------------------------------------------------------------- git (clone+venv)
def _git_url(tool: str) -> str:
    """URL del repo: campo 'git' o 'pip' tipo 'git+https://...'."""
    url = model.tool_data(tool).get("git") or model.tool_data(tool).get("pip", "")
    return url[4:] if url.startswith("git+") else url


# Compilatori e -dev installati TEMPORANEAMENTE quando un pacchetto Python deve
# compilare estensioni C (musl, nessun wheel pronto). NON sono preinstallati nella
# live (terrebbero ~centinaia di MB): si aggiungono al volo e si rimuovono dopo,
# cosi' "il compilatore c'e' quando serve" senza gonfiare l'ISO. Servono rete+apk.
BUILD_DEPS = ["python3-dev", "gcc", "g++", "musl-dev", "libffi-dev",
              "openssl-dev", "make", "linux-headers", "curl-dev",
              "libxml2-dev", "libxslt-dev"]


def _retry_with_build_deps(attempt, log=print) -> bool:
    """Esegue attempt() (-> bool). Se fallisce, installa i compilatori temporanei
    (.nxs-pipbuild), riprova e poi li rimuove (nessun bloat permanente)."""
    if attempt():
        return True
    if not have("apk"):
        return False
    log("[*] riprovo con compilatori temporanei (.nxs-pipbuild)...")
    subprocess.run(priv(["apk", "add", "--no-cache", "--virtual",
                         ".nxs-pipbuild"] + BUILD_DEPS))
    try:
        return attempt()
    finally:
        subprocess.run(priv(["apk", "del", ".nxs-pipbuild"]))


def _pip_user(args: list[str], log=print) -> bool:
    """pip --user robusto. Su Alpine (PEP 668) serve --break-system-packages;
    sui pip piu' vecchi quel flag non esiste -> riprova senza. Se la build di
    un'estensione C fallisce, riprova coi compilatori temporanei."""
    pip = "pip3" if have("pip3") else ("pip" if have("pip") else None)
    if not pip:
        log("[!] pip non disponibile (apk add py3-pip).")
        return False

    def _try():
        rc = subprocess.run([pip, "install", "--user",
                             "--break-system-packages"] + args).returncode
        if rc != 0:
            rc = subprocess.run([pip, "install", "--user"] + args).returncode
        return rc == 0

    return _retry_with_build_deps(_try, log)


def _install_git(tool: str, log=print) -> bool:
    url = _git_url(tool)
    if not url:
        log(f"[!] {tool}: manca l'URL git in repo.json.")
        return False
    if not have("git"):
        log("[!] git non disponibile (apk add git).")
        return False
    dest = GIT_BASE / tool
    GIT_BASE.mkdir(parents=True, exist_ok=True)
    if (dest / ".git").exists():
        log(f"[*] git -C {dest} pull --ff-only")
        subprocess.run(["git", "-C", str(dest), "pull", "--ff-only"])
    else:
        log(f"[*] git clone --depth 1 {url}")
        if subprocess.run(["git", "clone", "--depth", "1", url, str(dest)]).returncode != 0:
            return False

    binname = _bin(tool)
    # Caso A: il repo E' un pacchetto installabile -> pipx (gestisce il venv da
    # solo, gia' affidabile su Alpine; mette il bin in ~/.local/bin).
    if ((dest / "pyproject.toml").exists() or (dest / "setup.py").exists()) and have("pipx"):
        log(f"[*] pipx install {dest}")
        if subprocess.run(["pipx", "install", str(dest)]).returncode == 0:
            return True
        log("[*] pipx fallito: ripiego su pip --user + launcher.")

    # Caso B: solo script (es. metagoofil) o pipx assente. NB: su Alpine NON si
    # usa `python3 -m venv` (ensurepip assente): installo i requirements in user
    # site e creo un launcher che esegue lo script col python di sistema.
    if (dest / "requirements.txt").exists():
        log("[*] pip --user -r requirements.txt")
        _pip_user(["-r", str(dest / "requirements.txt")], log)
    entry = model.tool_data(tool).get("entry")
    if not entry:
        log(f"[!] {tool}: definisci 'entry' in repo.json (script da eseguire).")
        return False
    LOCAL_BIN.mkdir(parents=True, exist_ok=True)
    launcher = LOCAL_BIN / binname
    launcher.write_text(
        f'#!/bin/sh\n# launcher NexusSec (metodo git) per {tool}\n'
        f'exec python3 "{dest}/{entry}" "$@"\n')
    launcher.chmod(0o755)
    log(f"[+] {tool} pronto: {launcher}")
    return True


# ---------------------------------------------------------------- kali (container Debian)
def install_kali_pkg(pkg: str, log=print) -> bool:
    """Installa UN pacchetto apt nell'ambiente Kali condiviso e lo persiste.

    Base = l'ambiente condiviso se esiste (cosi accumula), altrimenti kali-rolling
    (scaricata la prima volta). Dopo l'install, ricommitta l'immagine su KALI_ENV:
    il pacchetto resta disponibile per sempre (finche lo storage e persistente).
    Ritorna True se il pacchetto e ora presente nell'ambiente.
    """
    if not have("podman"):
        log("[!] podman non disponibile (apk add podman).")
        return False
    env_ready = _image_exists(KALI_ENV)
    base = KALI_ENV if env_ready else KALI_IMG
    if not env_ready:
        log(f"[*] primo uso Kali: podman pull {KALI_IMG} (una sola volta)...")
        if subprocess.run(["podman", "pull", KALI_IMG]).returncode != 0:
            log("[!] impossibile scaricare la base Kali (rete? spazio su disco?).")
            return False
    # Se costruiamo dalla base grezza servono gli indici apt (update); se invece
    # ripartiamo dall'ambiente gia commitato, gli indici sono gia dentro -> salto.
    cname = "nxs-kali-build"
    log(f"[*] apt install {pkg} nell'ambiente Kali condiviso...")
    # Fino a 3 tentativi: assorbe gli intoppi di rete (mirror lento/indice
    # parziale) che davano errori apt confusi. L'apt-get update ha a sua volta un
    # retry interno. Dai tentativi >1 forziamo l'update anche se l'ambiente era
    # gia' pronto (indici del commit potrebbero essere vecchi in kali-rolling).
    rc = 1
    for attempt in range(1, 4):
        do_upd = (not env_ready) or attempt > 1
        upd = ("for i in 1 2 3; do apt-get update && break || sleep 3; done; "
               if do_upd else "")
        subprocess.run(["podman", "rm", "-f", cname],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        rc = subprocess.run(["podman", "run", "--name", cname, base, "sh", "-c",
                             f"{upd}DEBIAN_FRONTEND=noninteractive "
                             f"apt-get install -y --no-install-recommends {pkg}"]).returncode
        if rc == 0:
            break
        log(f"[!] apt install {pkg}: tentativo {attempt}/3 non riuscito "
            f"(rete?), riprovo...")
        time.sleep(3)
    if rc != 0:
        subprocess.run(["podman", "rm", "-f", cname],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log(f"[!] apt install {pkg} fallito dopo 3 tentativi.")
        return False
    ok = subprocess.run(["podman", "commit", cname, KALI_ENV]).returncode == 0
    subprocess.run(["podman", "rm", "-f", cname],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if ok:
        _kali_mark(pkg, True)
        log(f"[+] {pkg} pronto nell'ambiente Kali ({KALI_ENV}).")
    return ok


def _install_kali(tool: str, log=print) -> bool:
    return install_kali_pkg(_kali_pkg(tool), log)


def launch_kali_pkg(pkg: str, binname: str = "", args_string: str = "",
                    net_host: bool = True, log=print) -> bool:
    """Installa-se-serve ed ESEGUE un QUALSIASI pacchetto dell'arsenale Kali
    (~600+), anche NON elencato in repo.json: e la porta d'accesso "come Kali,
    tutti gli strumenti dentro". binname default = nome pacchetto (per i tool il
    cui comando differisce dal pacchetto, aggiungili a repo.json con 'bin')."""
    if not (_image_exists(KALI_ENV) and pkg in _kali_installed_pkgs()):
        if not install_kali_pkg(pkg, log):
            return False
    LOOT.mkdir(parents=True, exist_ok=True)
    cmd = _podman_flags(True) + _x11_flags()
    if net_host:
        cmd += ["--net", "host"]
    cmd.append(KALI_ENV)
    cmd += [binname or pkg] + (shlex.split(args_string) if args_string else [])
    log(f"[*] Kali: {' '.join(cmd)}")
    try:
        subprocess.run(cmd)
        return True
    except (FileNotFoundError, OSError) as e:
        log(f"[!] avvio fallito: {e}")
        return False


def kali_env_pkgs() -> list[str]:
    """Elenco dei tool Kali gia installati nell'ambiente condiviso."""
    return sorted(_kali_installed_pkgs())


def local_images() -> set[str]:
    """Insieme delle immagini container presenti in locale (per lo stato 'fast'
    del menu). Ritorna sia 'repo:tag' sia il solo 'repo', cosi' il pannello puo'
    riconoscere un tool 'container' come installato con un'UNICA chiamata a
    podman (invece di 'podman image exists' per ogni tool)."""
    if not have("podman"):
        return set()
    try:
        r = subprocess.run(["podman", "images", "--format", "{{.Repository}}:{{.Tag}}"],
                           capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return set()
    out = set()
    for ln in r.stdout.split():
        ln = ln.strip()
        if ln and ln != "<none>:<none>":
            out.add(ln)
            out.add(ln.rsplit(":", 1)[0])   # anche senza tag
    return out


def _make_cli_shim(tool: str, log=print) -> None:
    """Crea ~/.local/bin/<bin> per i tool CONTAINERIZZATI (kali/container), il
    cui binario NON sta nel PATH host: cosi' dopo l'installazione il tool si
    lancia anche da un TERMINALE qualsiasi (es. `amap ...`), non solo dal menu.
    Lo shim inoltra a `nxs-tool launch` (installa-se-serve + esegue nel
    container). apk/pip/git non ne hanno bisogno (binario gia' nel PATH).
    NB: ~/.local/bin e' gia' nel PATH della live (vedi home/nexus/.profile)."""
    binname = model.tool_data(tool).get("bin") or tool
    if not binname or not all(c.isalnum() or c in "._+-" for c in binname):
        return                                   # nome non sicuro: niente shim
    try:
        bindir = Path(os.path.expanduser("~")) / ".local" / "bin"
        bindir.mkdir(parents=True, exist_ok=True)
        shim = bindir / binname
        shim.write_text(
            "#!/bin/sh\n"
            f"# NexusSec: shim CLI del tool containerizzato '{tool}' (lo esegue\n"
            "# nel container). Generato automaticamente all'installazione.\n"
            f'exec nxs-tool launch {tool} "$@"\n')
        shim.chmod(0o755)
        log(f"[+] '{binname}' ora disponibile anche da terminale (~/.local/bin).")
    except OSError as e:
        log(f"[!] shim CLI non creato per {tool}: {e}")


# ---------------------------------------------------------------- installazione
def install(tool: str, log=print) -> bool:
    m = _method(tool)
    if m == "git":
        return _install_git(tool, log)
    if m == "kali":
        ok = _install_kali(tool, log)
        if ok:
            _make_cli_shim(tool, log)
        return ok
    if m == "container":
        img = _image(tool)
        if not img:
            note = model.tool_data(tool).get("note", "immagine non definita in repo.json")
            log(f"[!] {tool}: {note}")
            return False
        if not have("podman"):
            log("[!] podman non disponibile (apk add podman).")
            return False
        log(f"[*] podman pull {img}")
        ok = subprocess.run(["podman", "pull", img]).returncode == 0
        if ok:
            _make_cli_shim(tool, log)
        return ok

    if m == "pip":
        ref = model.tool_data(tool).get("pip", tool)
        if have("pipx"):
            # Alcuni tool pip compilano estensioni C (musl, niente wheel): se la
            # prima pipx install fallisce, _retry_with_build_deps riprova coi
            # compilatori temporanei e poi li rimuove (live snella).
            log(f"[*] pipx install {ref}")
            return _retry_with_build_deps(
                lambda: subprocess.run(["pipx", "install", ref]).returncode == 0,
                log)
        if have("pip3") or have("pip"):
            log(f"[*] pip install --user {ref}")
            return _pip_user([ref], log)
        log("[!] ne' pipx ne' pip disponibili (apk add pipx).")
        return False

    pkg = _apk_name(tool)
    if not pkg:
        log(f"[!] {tool}: nessun pacchetto apk associato.")
        return False
    if not have("apk"):
        log("[!] apk non disponibile: non e' un sistema Alpine?")
        return False
    # apk_extra: pacchetti companion necessari al pieno funzionamento (es. nmap
    # -> nmap-scripts per gli script NSE / rilevamento debolezze).
    pkgs = [pkg] + list(model.tool_data(tool).get("apk_extra", []))
    log(f"[*] apk add --no-cache {' '.join(pkgs)}")
    return subprocess.run(priv(["apk", "add", "--no-cache"] + pkgs)).returncode == 0


def uninstall(tool: str, log=print) -> bool:
    m = _method(tool)
    if m == "git":
        # se installato via pipx (pacchetto), prova a rimuoverlo da pipx
        if have("pipx"):
            for nm in {_bin(tool), tool}:
                subprocess.run(["pipx", "uninstall", nm],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        binp = LOCAL_BIN / _bin(tool)
        if binp.exists():
            binp.unlink()
        dest = GIT_BASE / tool
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        log(f"[*] {tool}: rimosso clone e launcher.")
        return True
    if m == "kali":
        # NON cancellare l'ambiente condiviso (ci vivono gli altri tool Kali):
        # rimuovo solo QUESTO pacchetto e ricommitto, poi aggiorno lo stato.
        pkg = _kali_pkg(tool)
        if not (have("podman") and _image_exists(KALI_ENV)):
            _kali_mark(pkg, False)
            log(f"[*] {tool}: ambiente Kali assente, niente da rimuovere.")
            return True
        cname = "nxs-kali-build"
        subprocess.run(["podman", "rm", "-f", cname],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log(f"[*] apt-get purge {pkg} dall'ambiente Kali condiviso...")
        rc = subprocess.run(["podman", "run", "--name", cname, KALI_ENV, "sh", "-c",
                             f"DEBIAN_FRONTEND=noninteractive apt-get purge -y {pkg} "
                             f"&& apt-get autoremove -y"]).returncode
        if rc == 0:
            subprocess.run(["podman", "commit", cname, KALI_ENV],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["podman", "rm", "-f", cname],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _kali_mark(pkg, False)
        return rc == 0
    if m == "container":
        img = _image(tool)
        if img and have("podman"):
            log(f"[*] podman rmi {img}")
            return subprocess.run(["podman", "rmi", img]).returncode == 0
        log(f"[!] {tool}: niente immagine da rimuovere.")
        return False
    if m == "pip":
        ref = model.tool_data(tool).get("pip", tool)
        if have("pipx"):
            log(f"[*] pipx uninstall {ref}")
            return subprocess.run(["pipx", "uninstall", ref]).returncode == 0
        log(f"[!] {tool}: rimozione pip manuale (pip uninstall {ref}).")
        return False
    pkg = _apk_name(tool)
    if pkg and have("apk"):
        log(f"[*] apk del {pkg}")
        return subprocess.run(priv(["apk", "del", pkg])).returncode == 0
    log(f"[!] {tool}: niente da rimuovere.")
    return False


# ---------------------------------------------------------------- esecuzione
def _bwrap(cmd: list[str]) -> list[str]:
    """Sandbox bwrap ATTIVA DI DEFAULT per i tool apk/pip non privilegiati.

    Tutela il core del sistema: l'intero filesystem e' montato in SOLA LETTURA
    (il tool non puo' modificare /usr, /etc, binari, config). Scrivibili solo:
    /tmp (tmpfs effimero), ~/NexusSec-loot (output), ~/.config e ~/.cache (stato
    del tool). La rete e' CONDIVISA (i tool di rete funzionano) e il socket X e'
    riesposto (tool GUI). Disattivabile con NXS_ISOLATE=0 (debug).
    """
    if os.environ.get("NXS_ISOLATE") == "0" or not have("bwrap"):
        return cmd
    home = os.path.expanduser("~")
    for d in (LOOT, Path(home) / ".config", Path(home) / ".cache"):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    return [
        "bwrap",
        "--ro-bind", "/", "/",                       # core in sola lettura
        "--dev", "/dev", "--proc", "/proc",
        "--tmpfs", "/tmp",
        "--ro-bind-try", "/tmp/.X11-unix", "/tmp/.X11-unix",
        "--bind-try", str(LOOT), str(LOOT),          # output condiviso
        "--bind-try", f"{home}/.config", f"{home}/.config",
        "--bind-try", f"{home}/.cache", f"{home}/.cache",
        "--chdir", str(LOOT),
        "--unshare-pid", "--die-with-parent",
    ] + cmd


def _x11_flags() -> list[str]:
    """Passthrough X11: fa girare anche i tool GRAFICI dell'arsenale Kali dentro
    il container (montando il socket X e passando DISPLAY). Innocuo per i CLI."""
    disp = os.environ.get("DISPLAY")
    if disp and Path("/tmp/.X11-unix").exists():
        return ["-e", f"DISPLAY={disp}", "-v", "/tmp/.X11-unix:/tmp/.X11-unix"]
    return []


def _podman_flags(interactive: bool) -> list[str]:
    # -it solo in modo interattivo: per i wizard (output catturato) niente tty.
    return ["podman", "run", "--rm"] + (["-it"] if interactive else []) \
        + ["-v", f"{LOOT}:/loot"]


def _podman_run(tool: str, args: list[str], interactive: bool = True) -> list[str]:
    data = model.tool_data(tool)
    img = _image(tool)
    LOOT.mkdir(parents=True, exist_ok=True)
    cmd = _podman_flags(interactive)
    if data.get("privileged"):           # tool che richiedono accesso completo
        cmd += ["--privileged"]
    if data.get("net") == "host":
        cmd += ["--net", "host"]
    # Pubblicazione porte: mappa "ports":["127.0.0.1:5000:5000",...] su -p.
    # AUTOPROTEZIONE: i server web dei tool OSINT (es. PhoneInfoga) vanno esposti
    # SOLO su loopback, mai su 0.0.0.0 (che con --net host sarebbe raggiungibile
    # dalla LAN quando il firewall e' spento durante un pentest).
    for _p in (data.get("ports") or []):
        cmd += ["-p", _p]
    if data.get("entrypoint"):           # override (es. theHarvester: l'EP e' il server REST)
        cmd += ["--entrypoint", data["entrypoint"]]
    cmd.append(img)
    run_in = data.get("run")
    if run_in:
        cmd += shlex.split(run_in)
    return cmd + args


def _kali_run(tool: str, args: list[str], interactive: bool = True) -> list[str]:
    data = model.tool_data(tool)
    LOOT.mkdir(parents=True, exist_ok=True)
    cmd = _podman_flags(interactive) + _x11_flags()
    if data.get("privileged"):
        cmd += ["--privileged"]
    if data.get("net") == "host":
        cmd += ["--net", "host"]
    cmd.append(KALI_ENV)                  # ambiente Kali condiviso (accumula i tool)
    return cmd + [_bin(tool)] + args


def build_cmd(tool: str, args: list[str], interactive: bool = True,
              log=print) -> list[str] | None:
    """Costruisce (senza eseguire) la riga di comando per lanciare un tool.
    Condivisa da run() e dai wizard. interactive=False per output catturato."""
    m = _method(tool)
    if m in ("container", "kali"):
        if not have("podman"):
            log("[!] podman non disponibile (apk add podman).")
            return None
        return _kali_run(tool, args, interactive) if m == "kali" \
            else _podman_run(tool, args, interactive)
    exe = shutil.which(_bin(tool)) or shutil.which(tool) or shutil.which(_apk_name(tool) or "")
    if not exe:
        log(f"[!] {tool}: non installato. Usa 'nxs-tool install {tool}'.")
        return None
    if model.tool_data(tool).get("privileged"):
        # raw socket / monitor mode / sniffing: serve accesso reale -> con
        # privilegi e SENZA bwrap (lo romperebbe). Il core resta protetto dalla
        # natura live/RAM in sola lettura.
        return priv([exe] + args)
    return _bwrap([exe] + args)


def run(tool: str, args_string: str = "", log=print, foreground: bool = False) -> bool:
    args = shlex.split(args_string) if args_string else []
    cmd = build_cmd(tool, args, interactive=True, log=log)
    if not cmd:
        return False
    if cmd[0] == "podman":
        log(f"[*] container: {' '.join(cmd)}")
    elif cmd[0] == "bwrap":
        log("[*] sandbox bwrap attiva: filesystem di sistema in sola lettura.")
    elif cmd[0] in ("doas", "sudo"):
        log("[*] tool privilegiato: eseguo con privilegi (no sandbox FS).")
    try:
        (subprocess.run if foreground else subprocess.Popen)(cmd)
        return True
    except (FileNotFoundError, OSError) as e:
        log(f"[!] avvio fallito: {e}")
        return False


def launch(tool: str, args_string: str = "", log=print) -> bool:
    """Installa-se-serve e poi esegue. Pensato per girare in un terminale
    (voce di menu del pannello)."""
    if not is_installed(tool):
        log(f"[*] {tool} non presente: lo ottengo ({_method(tool)})...")
        if not install(tool, log):
            return False
    return run(tool, args_string, log, foreground=True)
