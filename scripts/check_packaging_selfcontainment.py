#!/usr/bin/env python3
"""CI check: verify that a packaged adapter imports without noosphere.

Launches a subprocess whose PYTHONPATH excludes any ``noosphere.*`` packages,
imports ``adapter.py`` from the package directory, and asserts no ImportError.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import textwrap
from pathlib import Path


def check_selfcontainment(package_dir: str) -> bool:
    """Return True if adapter.py in *package_dir* can be imported without noosphere."""
    package_path = Path(package_dir).resolve()
    adapter_path = package_path / "adapter.py"
    impl_path = package_path / "implementation"

    if not adapter_path.exists():
        print(f"FAIL: {adapter_path} does not exist")
        return False

    test_script = textwrap.dedent(f"""\
        import sys
        # Remove any noosphere paths from sys.path
        sys.path = [p for p in sys.path if "noosphere" not in p]
        # Add only the package dir and implementation dir
        sys.path.insert(0, {str(package_path)!r})
        sys.path.insert(0, {str(impl_path)!r})

        # Verify noosphere is not importable
        try:
            import noosphere
            print("FAIL: noosphere is importable — package is not self-contained")
            sys.exit(1)
        except ImportError:
            pass  # Good — noosphere should not be available

        # Now try to import the adapter
        import importlib.util
        spec = importlib.util.spec_from_file_location("adapter", {str(adapter_path)!r})
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # Verify the run function exists
        assert hasattr(mod, "run"), "adapter.py must export a run() function"
        print("OK: adapter.py is self-contained")
    """)

    result = subprocess.run(
        [sys.executable, "-c", test_script],
        capture_output=True,
        text=True,
        env={"PATH": "", "HOME": "", "PYTHONPATH": ""},
        timeout=30,
    )

    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)

    return result.returncode == 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check that a packaged method adapter is self-contained."
    )
    parser.add_argument("package_dir", help="Path to the packaged method directory")
    args = parser.parse_args()

    if not check_selfcontainment(args.package_dir):
        sys.exit(1)


if __name__ == "__main__":
    main()
