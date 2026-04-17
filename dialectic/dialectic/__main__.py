"""Allow running with ``python -m dialectic``."""

import argparse
import multiprocessing
import sys

from .config import DialecticConfig
from .dashboard import run_dashboard


def main() -> None:
    p = argparse.ArgumentParser(description="Dialectic live dashboard")
    p.add_argument(
        "--model",
        default=None,
        metavar="NAME",
        help="faster-whisper model: tiny, base, small, medium, large (optional .en)",
    )
    p.add_argument(
        "--device",
        default=None,
        choices=("cpu", "mps", "cuda", "auto"),
        help="Inference device (MPS maps to CPU for faster-whisper).",
    )
    p.add_argument(
        "--legacy",
        action="store_true",
        help="Use the original multi-panel dashboard (no qasync graph).",
    )
    args = p.parse_args()
    run_dashboard(
        DialecticConfig(),
        legacy=args.legacy,
        whisper_model=args.model,
        whisper_device=args.device,
    )


if __name__ == "__main__":
    # Must be inside the __main__ guard — see note in run.py.
    if getattr(sys, "frozen", False):
        multiprocessing.freeze_support()
    main()
