#!/usr/bin/env python3
"""Stand-in for scripts/check_no_import_cycles.py.

Exits 1 with a deterministic message identifying a fake cycle. The gate
test invokes this via READY_TO_SYNC_CMD_2 to assert step-2 failures
surface correctly.
"""
import sys

if __name__ == "__main__":
    print("FIXTURE: import cycle detected", file=sys.stderr)
    print("  noosphere.a -> noosphere.b -> noosphere.a", file=sys.stderr)
    sys.exit(1)
