"""nxs_disks - gestione dischi di NexusSec OS.

Diviso in tre pezzi per poter essere riusato in Vesper senza portarsi dietro
GTK: model.py (logica pura), mount.py (montaggio), view.py (GUI GTK3).
"""
__all__ = ["model", "mount", "view"]
