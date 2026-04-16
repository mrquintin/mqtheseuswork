"""PyInstaller runtime hook: runs before any noosphere code when frozen."""

import os
import sys  # noqa: F401  (kept so hook has stdlib access for future env checks)

# Signal to application code that it is running from a PyInstaller bundle.
os.environ.setdefault("NOOSPHERE_FROZEN", "1")
