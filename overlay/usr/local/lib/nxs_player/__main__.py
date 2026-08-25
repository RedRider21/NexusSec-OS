"""Avvio del Lettore audio NexusSec: nxs-player [file1 file2 ...]."""
import sys

from nxs_player.app import main

if __name__ == "__main__":
    main(sys.argv[1:])
