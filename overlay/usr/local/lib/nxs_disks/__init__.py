# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""nxs_disks - gestione dischi di NexusSec OS.

Diviso in tre pezzi per poter essere riusato in Vesper senza portarsi dietro
GTK: model.py (logica pura), mount.py (montaggio), view.py (GUI GTK3).
"""
__all__ = ["model", "mount", "view"]
