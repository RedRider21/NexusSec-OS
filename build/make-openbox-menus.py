#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""Genera il menu del tasto destro di Openbox nelle 5 lingue.

Sorgente: overlay/home/nexus/.config/openbox/menu.xml (italiano, la lingua
sorgente di NexusSec). Output: overlay/usr/local/share/nexussec/openbox-menu/
menu.<lang>.xml per it/en/fr/es/de. nxs-lang copia quello della lingua scelta
in ~/.config/openbox/menu.xml, ma SOLO se il menu dell'utente e' ancora uno di
questi file di serie (le modifiche fatte a mano o con l'editor del menu del
Centro di Controllo non vengono mai sovrascritte).

Si cambia il menu? Si modifica il menu.xml italiano, si aggiungono qui le
traduzioni delle voci nuove e si rilancia:  python3 build/make-openbox-menus.py
Una voce senza traduzione fa fallire lo script (niente menu mezzi italiani).
"""
import os
import re
import sys
from xml.sax.saxutils import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "overlay/home/nexus/.config/openbox/menu.xml")
OUT = os.path.join(ROOT, "overlay/usr/local/share/nexussec/openbox-menu")
LANGS = ("en", "fr", "es", "de")

# etichetta italiana -> (en, fr, es, de)
TR = {
    "Strumenti": ("Tools", "Outils", "Herramientas", "Werkzeuge"),
    "Editor di testo": ("Text editor", "Éditeur de texte", "Editor de texto", "Texteditor"),
    "Registratore vocale": ("Voice recorder", "Enregistreur vocal", "Grabadora de voz", "Sprachaufnahme"),
    "Pulisci metadati (MAT2)": ("Clean metadata (MAT2)", "Nettoyer les métadonnées (MAT2)",
                                "Limpiar metadatos (MAT2)", "Metadaten bereinigen (MAT2)"),
    "Appunti (cronologia)": ("Clipboard (history)", "Presse-papiers (historique)",
                             "Portapapeles (historial)", "Zwischenablage (Verlauf)"),
    "Filtro luce blu (on/off)": ("Blue light filter (on/off)", "Filtre lumière bleue (on/off)",
                                 "Filtro de luz azul (on/off)", "Blaulichtfilter (ein/aus)"),
    "Scorciatoie da tastiera": ("Keyboard shortcuts", "Raccourcis clavier",
                                "Atajos de teclado", "Tastenkürzel"),
    "Dischi": ("Disks", "Disques", "Discos", "Datenträger"),
    "Casi forensi": ("Forensic cases", "Affaires forensiques", "Casos forenses", "Forensische Fälle"),
    "Procedure guidate (Wizard)": ("Guided procedures (Wizard)", "Procédures guidées (Wizard)",
                                   "Procedimientos guiados (Wizard)", "Geführte Abläufe (Wizard)"),
    "Centro di Controllo": ("Control Center", "Centre de contrôle", "Centro de control", "Kontrollzentrum"),
    "Sicurezza": ("Security", "Sécurité", "Seguridad", "Sicherheit"),
    "Blocca schermo": ("Lock screen", "Verrouiller l'écran", "Bloquear pantalla", "Bildschirm sperren"),
    "Cattura schermata (intero)": ("Screenshot (full screen)", "Capture d'écran (entière)",
                                   "Captura de pantalla (completa)", "Bildschirmfoto (ganz)"),
    "Cattura schermata (area)": ("Screenshot (area)", "Capture d'écran (zone)",
                                 "Captura de pantalla (área)", "Bildschirmfoto (Bereich)"),
    "Anonimo (tutto via Tor): ATTIVA": ("Anonymous (all via Tor): ENABLE",
                                        "Anonyme (tout via Tor) : ACTIVER",
                                        "Anónimo (todo por Tor): ACTIVAR",
                                        "Anonym (alles über Tor): AKTIVIEREN"),
    "Anonimo (tutto via Tor): DISATTIVA": ("Anonymous (all via Tor): DISABLE",
                                           "Anonyme (tout via Tor) : DÉSACTIVER",
                                           "Anónimo (todo por Tor): DESACTIVAR",
                                           "Anonym (alles über Tor): DEAKTIVIEREN"),
    "Firewall: ATTIVA": ("Firewall: ENABLE", "Pare-feu : ACTIVER",
                         "Cortafuegos: ACTIVAR", "Firewall: AKTIVIEREN"),
    "Firewall: DISATTIVA": ("Firewall: DISABLE", "Pare-feu : DÉSACTIVER",
                            "Cortafuegos: DESACTIVAR", "Firewall: DEAKTIVIEREN"),
    "MAC casuale ora": ("Random MAC now", "MAC aléatoire maintenant",
                        "MAC aleatoria ahora", "Zufällige MAC jetzt"),
    "PANICO: cancella e spegni": ("PANIC: wipe and shut down", "PANIQUE : effacer et éteindre",
                                  "PÁNICO: borrar y apagar", "PANIK: löschen und herunterfahren"),
    "NexusSec": ("NexusSec", "NexusSec", "NexusSec", "NexusSec"),
    "Profilo operativo": ("Operational profile", "Profil opérationnel",
                          "Perfil operativo", "Betriebsprofil"),
    "Cambia sfondo": ("Change wallpaper", "Changer le fond d'écran", "Cambiar fondo",
                      "Hintergrund ändern"),
    "Terminale": ("Terminal", "Terminal", "Terminal", "Terminal"),
    "NexusSec Browser": ("NexusSec Browser", "NexusSec Browser", "NexusSec Browser",
                         "NexusSec Browser"),
    "File manager": ("File manager", "Gestionnaire de fichiers", "Gestor de archivos",
                     "Dateimanager"),
    "HORUS (OSINT globale)": ("HORUS (global OSINT)", "HORUS (OSINT mondial)",
                              "HORUS (OSINT global)", "HORUS (globales OSINT)"),
    "Riavvia Openbox": ("Restart Openbox", "Redémarrer Openbox", "Reiniciar Openbox",
                        "Openbox neu starten"),
    "Esci / Spegni…": ("Log out / Shut down…", "Déconnexion / Éteindre…",
                       "Salir / Apagar…", "Abmelden / Ausschalten…"),
}

LABEL = re.compile(r'label="([^"]*)"')


def main():
    src = open(SRC, encoding="utf-8").read()
    missing = sorted({m for m in LABEL.findall(src)} - set(TR))
    if missing:
        print("voci senza traduzione:", missing, file=sys.stderr)
        return 1
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "menu.it.xml"), "w", encoding="utf-8") as f:
        f.write(src)
    for i, lang in enumerate(LANGS):
        out = LABEL.sub(lambda m: 'label="%s"' % escape(TR[m.group(1)][i],
                                                         {'"': "&quot;"}), src)
        with open(os.path.join(OUT, "menu.%s.xml" % lang), "w", encoding="utf-8") as f:
            f.write(out)
    print("menu generati in", OUT, "(it + %s)" % ", ".join(LANGS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
