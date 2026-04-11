"""
Entry point for Noosphere CLI.

Allows running the Noosphere system as a module:
    python -m noosphere <command> [options]
"""

from noosphere.cli import cli

if __name__ == "__main__":
    cli()
