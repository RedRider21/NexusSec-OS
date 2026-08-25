"""Avvio del salvaschermo NexusSec: nxs-screensaver [nebula|matrix|starfield]."""
import sys

from nxs_screensaver.app import main

if __name__ == "__main__":
    main(sys.argv[1:])
