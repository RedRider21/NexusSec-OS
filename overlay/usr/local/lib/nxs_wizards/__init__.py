"""NexusSec - procedure guidate (wizard).

Piccole interfacce che chiedono pochi dati (un IP, un dominio, un URL, un file)
ed eseguono in autonomia una catena di tool del catalogo, installandoli al volo.

Moduli:
- recipes : carica/espone le ricette da wizards.json;
- runner  : esegue la sequenza di step (riusa nxs_profiles.isolation) e fa da
            "regista", emettendo l'output riga per riga via callback;
- gui     : finestra GTK3 (form + output dal vivo), coerente col pannello;
- cli     : backend di `nxs-wizard` (list / run / gui).

Niente GTK in recipes/runner/cli (importabili headless): solo gui usa GTK.
"""
