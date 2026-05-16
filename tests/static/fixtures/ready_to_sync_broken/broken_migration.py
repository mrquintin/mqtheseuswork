#!/usr/bin/env python3
"""Stand-in for scripts/check_migration_linearity.py.

The test plants this script in lieu of the real linearity check and points
the gate at it via the READY_TO_SYNC_CMD_1 override. It exits 1 with a
deterministic message so the gate's step-1 log can be asserted against.
"""
import sys

if __name__ == "__main__":
    print("FIXTURE: planted broken Prisma migration chain", file=sys.stderr)
    print("  20260101000000_first parent missing", file=sys.stderr)
    sys.exit(1)
