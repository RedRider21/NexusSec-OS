# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""Avvio dell'editor: python3 -m nxs_editor [file...] [+RIGA]."""
import sys
from nxs_editor.app import main

if __name__ == "__main__":
    main(sys.argv[1:])
