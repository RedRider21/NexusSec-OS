# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di NexusSec OS.
import os
import sys

from nxs_horus.app import main

if __name__ == "__main__":
    rc = main()
    # Uscita ESPLICITA: thread di servizio (stream AIS, download in background,
    # pool delle news) altrimenti tengono vivo il processo dopo la chiusura
    # dell'ultima finestra (verificato 2026-11-20).
    sys.stdout.flush(); sys.stderr.flush()
    os._exit(rc or 0)
