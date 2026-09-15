# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
"""`python -m nxs_profiles` apre il selettore grafico del profilo."""
import sys

from .selector import run

if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
