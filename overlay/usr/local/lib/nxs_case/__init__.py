# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""nxs_case - gestione di un caso forense per NexusSec OS.

model.py (logica pura, niente GTK) · report.py (relazione HTML) · view.py (GUI).
Stessa struttura di nxs_disks, per gli stessi motivi: la logica si riusa e si
collauda senza interfaccia grafica.
"""
__all__ = ["model", "report", "view"]
