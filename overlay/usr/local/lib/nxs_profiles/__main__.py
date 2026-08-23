"""`python -m nxs_profiles` apre il selettore grafico del profilo."""
import sys

from .selector import run

if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
