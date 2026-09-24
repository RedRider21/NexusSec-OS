# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS (portato da Vesper).
"""Avvio del visualizzatore: nxs-viewer [file o cartella]."""
import sys

from nxs_viewer.app import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
