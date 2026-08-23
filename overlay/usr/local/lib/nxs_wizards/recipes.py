"""Caricamento e gestione delle ricette dei wizard.

Due sorgenti, fuse in un unico elenco:
  - STANDARD  : /usr/local/share/nexussec/wizards.json (parte della distro,
                sola lettura; accanto a profiles.json/repo.json).
  - PERSONALI : ~/.config/nxs/wizards/<id>.json (uno per file, creati
                dall'utente col costruttore; scrivibili e persistenti nella home).

I wizard personali possono aggiungersi agli standard e, se hanno lo stesso id,
sovrascriverli. Ogni ricetta caricata riceve i campi calcolati `id` e `custom`.

Schema di una ricetta (v2, retro-compatibile con la v1 senza modes/options):
  name, icon, description, profile(opz.)
  fields:  [{key,label,placeholder,required,type}]         input testuali/file
  modes:   [{id,label,desc,default,vars:{...}}]            intensita' (scelta 1)
  options: [{id,label,desc,default}]                       spunte indipendenti
  steps:   [{tool,desc,args,modes:[...],needs:[...]}]       catena di tool
           - `modes` (opz.): lo step gira solo con una di quelle intensita';
           - `needs` (opz.): lo step gira solo se TUTTE quelle opzioni sono attive;
           - senza gate lo step gira sempre. Negli args: {campo}, {var-di-modalita'},
             {outdir} (cartella step), {loot} (cartella run).

Niente GTK qui: importabile headless (CLI/runner).
"""
from __future__ import annotations

import json

from nxs_profiles import model  # per riusare PREFIX e CONF_DIR

WIZARDS_JSON = model.PREFIX / "wizards.json"
USER_DIR = model.CONF_DIR / "wizards"


# --------------------------------------------------------------- caricamento
def _load_standard() -> dict:
    try:
        return dict(json.loads(WIZARDS_JSON.read_text()).get("wizards", {}))
    except (OSError, ValueError):
        return {}


def _load_user() -> dict:
    """Legge ~/.config/nxs/wizards/*.json (un wizard per file, id = nome file)."""
    out: dict = {}
    try:
        files = sorted(USER_DIR.glob("*.json"))
    except OSError:
        return out
    for fp in files:
        try:
            obj = json.loads(fp.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(obj, dict) and obj.get("steps") is not None:
            out[fp.stem] = obj
    return out


def _merged() -> dict:
    """{id: ricetta} standard + personali (i personali vincono su pari id)."""
    std = _load_standard()
    usr = _load_user()
    merged: dict = {}
    for wid, w in std.items():
        w = dict(w)
        w["id"] = wid
        w["custom"] = False
        merged[wid] = w
    for wid, w in usr.items():
        w = dict(w)
        w["id"] = wid
        w["custom"] = True
        merged[wid] = w
    return merged


# ------------------------------------------------------------------- query
def all_wizards() -> dict:
    """{id: ricetta} di tutti i wizard (standard + personali)."""
    return _merged()


def get(wid: str) -> dict | None:
    return _merged().get(wid)


def for_profile(profile: str) -> list[tuple[str, dict]]:
    """Wizard pertinenti a un profilo (piu' quelli senza profilo = generici)."""
    out = []
    for wid, w in _merged().items():
        p = w.get("profile")
        if p is None or p == profile:
            out.append((wid, w))
    return out


def is_custom(wid: str) -> bool:
    w = get(wid)
    return bool(w and w.get("custom"))


# ------------------------------------------------------- modalita' / opzioni
def default_mode(wiz: dict) -> str | None:
    """Id della modalita' preselezionata (la prima con default=true, altrimenti
    la prima in elenco). None se il wizard non ha modalita'."""
    modes = wiz.get("modes") or []
    if not modes:
        return None
    for m in modes:
        if m.get("default"):
            return m.get("id")
    return modes[0].get("id")


def mode_vars(wiz: dict, mode_id: str | None) -> dict:
    """Variabili di sostituzione della modalita' scelta (per gli args)."""
    for m in wiz.get("modes") or []:
        if m.get("id") == mode_id:
            return dict(m.get("vars") or {})
    return {}


def default_options(wiz: dict) -> list[str]:
    """Id delle opzioni spuntate di default."""
    return [o["id"] for o in (wiz.get("options") or []) if o.get("default")]


def stealth_default(wiz: dict) -> bool:
    """Se l'interruttore Stealth parte ON per questo wizard."""
    return bool(wiz.get("stealth_default"))


def stealth_applicable(wiz: dict) -> bool:
    """True se lo stealth ha senso: almeno uno step e' instradabile via Tor
    (anon='tor', il default). Falso per wizard tutti locali (es. forensics),
    dove l'interruttore Stealth non va mostrato."""
    for s in wiz.get("steps", []):
        if (s.get("stealth") or {}).get("anon", "tor") == "tor":
            return True
    return False


def step_active(step: dict, mode_id: str | None, options: set[str],
                stealth: bool | None = None) -> bool:
    """True se lo step va eseguito con questa combinazione. Se `stealth` e'
    specificato, considera anche i gate stealth dello step: `only` ('on'/'off')
    e `skip` (saltato quando stealth e' ON)."""
    smodes = step.get("modes")
    if smodes and mode_id not in smodes:
        return False
    needs = step.get("needs")
    if needs and not set(needs).issubset(options):
        return False
    if stealth is not None:
        st = step.get("stealth") or {}
        only = st.get("only")
        if only == "on" and not stealth:
            return False
        if only == "off" and stealth:
            return False
        if stealth and st.get("skip"):
            return False
    return True


def count_active_steps(wiz: dict, mode_id: str | None, options,
                       stealth: bool | None = None) -> int:
    opts = set(options or [])
    return sum(1 for s in wiz.get("steps", [])
               if step_active(s, mode_id, opts, stealth))


# ------------------------------------------------- salvataggio personalizzati
def save_custom(wid: str, wiz: dict) -> bool:
    """Salva/aggiorna un wizard personale in ~/.config/nxs/wizards/<wid>.json.
    `wid` deve essere uno slug semplice (validato dal chiamante)."""
    try:
        USER_DIR.mkdir(parents=True, exist_ok=True)
        data = {k: v for k, v in wiz.items() if k not in ("id", "custom")}
        (USER_DIR / f"{wid}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2))
        return True
    except OSError:
        return False


def delete_custom(wid: str) -> bool:
    """Elimina un wizard personale. Ritorna False se non e' personale/non esiste."""
    fp = USER_DIR / f"{wid}.json"
    try:
        if fp.exists():
            fp.unlink()
            return True
    except OSError:
        pass
    return False
