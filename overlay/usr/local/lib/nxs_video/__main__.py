"""Avvio del Visualizzatore video NexusSec: nxs-video [file1 file2 ...]."""
import sys

from nxs_video.app import main

if __name__ == "__main__":
    main(sys.argv[1:])
