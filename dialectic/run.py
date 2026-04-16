#!/usr/bin/env python3
"""Launch the Dialectic live-analysis dashboard (wrapper for ``python -m dialectic``)."""

import multiprocessing
import sys

if getattr(sys, "frozen", False):
    multiprocessing.freeze_support()

from dialectic.__main__ import main

if __name__ == "__main__":
    main()
