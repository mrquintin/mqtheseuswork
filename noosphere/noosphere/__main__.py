"""
Entry point for Noosphere CLI.

Allows running the Noosphere system as a module:
    python -m noosphere <command> [options]
"""

import multiprocessing
import sys

if getattr(sys, "frozen", False):
    multiprocessing.freeze_support()

from noosphere.typer_cli import main

if __name__ == "__main__":
    main()
