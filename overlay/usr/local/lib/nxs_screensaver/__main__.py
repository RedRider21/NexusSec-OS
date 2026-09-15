# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""Avvio del salvaschermo NexusSec: nxs-screensaver [nebula|matrix|starfield]."""
import sys

from nxs_screensaver.app import main

if __name__ == "__main__":
    main(sys.argv[1:])
