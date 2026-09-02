"""Montaggio dischi - l'UNICO punto in cui NexusSec tocca un disco.

REGOLA FORENSIC (decisione utente): i dischi si VEDONO ma non si toccano se non
con un comando esplicito. Qui questo si traduce in tre scelte non negoziabili:

  1. NIENTE automount. Non esiste nessuna funzione che monti da sola: ogni
     montaggio nasce da un clic dell'utente. E' anche il motivo per cui la
     distro NON installa gvfs (27 MiB che servono proprio ad automontare).
  2. "ro" e' il DEFAULT. mount_ro() e' la via normale; mount_rw() esiste ma va
     chiamata di proposito e la GUI ci mette davanti un avviso.
  3. Opzioni difensive sempre attive: noatime (non aggiorna i tempi di accesso,
     che altererebbero il reperto), nosuid e nodev (un disco altrui non deve
     poter portare binari setuid o nodi di device).

Per la protezione VERA c'e' write_protect(): agisce a livello di BLOCCO
(blockdev --setro), quindi sotto al filesystem. Con quella attiva nemmeno un
montaggio rw sbagliato riesce a scrivere: e' il write-blocker software.

Elevazione: nexus e' in wheel con 'permit nopass :wheel' (doas), come il resto
della distro (nxs-wifi, nxs-users...).
"""
import os
import re
import shutil
import subprocess

# Radice dei punti di montaggio creati da noi. Sotto /media (non /mnt) per non
# pestare i piedi a chi monta a mano.
RADICE = "/media/nxs"

_OPZIONI_BASE = "noatime,nosuid,nodev"
_SICURO = re.compile(r"^[A-Za-z0-9._-]+$")


def _priv(args, input_text=None, timeout=60):
    """Esegue un comando da root via doas. Ritorna (ok, output)."""
    if os.geteuid() != 0:
        if shutil.which("doas"):
            args = ["doas"] + args
        elif shutil.which("sudo"):
            args = ["sudo"] + args
    try:
        r = subprocess.run(args, capture_output=True, text=True,
                           input=input_text, timeout=timeout)
        return (r.returncode == 0, (r.stdout + r.stderr).strip())
    except (OSError, subprocess.SubprocessError) as e:
        return (False, str(e))


def _nome_punto(node):
    """Nome della cartella di mount: etichetta se pulita, altrimenti il device.

    L'etichetta arriva dal disco ALTRUI: va trattata come non fidata, quindi
    accettiamo solo caratteri innocui (niente '/', niente '..').
    """
    cand = (node.label or "").strip()
    if not cand or not _SICURO.match(cand):
        cand = node.name
    return cand


def punto_di_mount(node):
    return os.path.join(RADICE, _nome_punto(node))


def mount_ro(node):
    """Monta in SOLA LETTURA. E' la via normale. Ritorna (ok, messaggio)."""
    return _monta(node, scrittura=False)


def mount_rw(node):
    """Monta in lettura-SCRITTURA. Va chiamata solo dopo conferma esplicita."""
    return _monta(node, scrittura=True)


def _monta(node, scrittura):
    if node.mounted:
        return (True, "gia' montato in %s" % node.mountpoint)
    if node.is_swap:
        return (False, "e' una partizione di swap: non si monta")
    if not node.fstype:
        return (False, "nessun filesystem riconosciuto su %s" % node.path)

    punto = punto_di_mount(node)
    # Collisione: due partizioni con la STESSA etichetta (es. due NTFS "Windows")
    # mapperebbero sulla stessa cartella e la seconda si monterebbe SOPRA la
    # prima, nascondendola. Se il punto e' gia' un mountpoint attivo, ripiego
    # sul nome del device (sempre univoco).
    if os.path.ismount(punto):
        punto = os.path.join(RADICE, node.name)
    ok, msg = _priv(["mkdir", "-p", punto])
    if not ok:
        return (False, "non riesco a creare %s: %s" % (punto, msg))

    opz = ("rw," if scrittura else "ro,") + _OPZIONI_BASE
    ok, msg = _priv(["mount", "-o", opz, node.path, punto])
    if ok:
        return (True, punto)

    # ntfs: se il kernel non ha ntfs3, ci pensa ntfs-3g (FUSE). Riproviamo
    # esplicitamente cosi' l'errore che mostriamo e' quello vero.
    if node.fstype in ("ntfs", "ntfs3") and shutil.which("ntfs-3g"):
        ok2, msg2 = _priv(["ntfs-3g", "-o", opz, node.path, punto])
        if ok2:
            return (True, punto)
        msg = msg2 or msg
    _priv(["rmdir", punto])
    return (False, msg or "montaggio fallito")


def smonta(node):
    """Smonta. Rimuove anche la cartella se l'avevamo creata noi."""
    if not node.mounted:
        return (True, "non era montato")
    ok, msg = _priv(["umount", node.mountpoint])
    if not ok:
        return (False, msg or "smontaggio fallito")
    if node.mountpoint.startswith(RADICE + "/"):
        _priv(["rmdir", node.mountpoint])
    return (True, "smontato")


def write_protect(path, attiva):
    """Protezione in scrittura a livello di BLOCCO (il write-blocker software).

    Agisce sotto al filesystem: con questa attiva nessun montaggio, nemmeno
    rw, riesce a scrivere sul dispositivo. E' la protezione che conta davvero
    quando si esamina un reperto.

    Passa da nxs-writeblock e NON da "blockdev --setro" diretto: quel comando
    tiene il registro dei device che ha bloccato lui (/run/nxs/wb-locked), cosi'
    un "nxs-writeblock off" sblocca solo quelli e non quelli bloccati a mano.
    Scavalcandolo si creerebbero due meccanismi che non si vedono a vicenda.
    Il fallback su blockdev resta per il caso in cui nxs-writeblock manchi.
    """
    if shutil.which("nxs-writeblock"):
        ok, msg = _priv(["nxs-writeblock", "lock" if attiva else "unlock", path])
        if ok:
            return (True, "protetto" if attiva else "protezione rimossa")
        return (False, msg or "nxs-writeblock ha rifiutato l operazione")
    flag = "--setro" if attiva else "--setrw"
    ok, msg = _priv(["blockdev", flag, path])
    return (ok, msg or ("protetto" if attiva else "protezione rimossa"))


def luks_apri(path, nome, passphrase):
    """Apre un volume LUKS. In SOLA LETTURA (--readonly), coerente col resto.

    La passphrase passa da STDIN, mai negli argomenti: in argv sarebbe visibile
    a chiunque con un 'ps' (stessa regola di nxs-users e del PSK WiFi).
    """
    if not _SICURO.match(nome or ""):
        return (False, "nome del volume non valido")
    return _priv(["cryptsetup", "open", "--readonly", "--key-file=-", path, nome],
                 input_text=passphrase)


def luks_chiudi(nome):
    if not _SICURO.match(nome or ""):
        return (False, "nome del volume non valido")
    return _priv(["cryptsetup", "close", nome])
