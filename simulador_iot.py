"""Backward-compatible entry point; implementation lives in ``simulation``."""

from simulation.cli import main

if __name__ == '__main__':
    raise SystemExit(main())
