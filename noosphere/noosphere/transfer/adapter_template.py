"""Generate a self-contained adapter.py for a packaged method.

The adapter MUST import ONLY from the packaged implementation and PyPI
packages — never from ``noosphere.*``.
"""
from __future__ import annotations

ADAPTER_TEMPLATE = '''\
# Auto-generated adapter for packaged method: {method_name} v{method_version}.
# This file imports ONLY from the local implementation package and PyPI deps.
import json
import sys
from pathlib import Path

# The implementation directory is a sibling of this file.
_impl_dir = Path(__file__).resolve().parent / "implementation"
if str(_impl_dir) not in sys.path:
    sys.path.insert(0, str(_impl_dir))

from {entry_module} import {entry_fn}  # noqa: E402


def run(input_json: str) -> str:
    """Deserialize *input_json*, call the method, and return JSON output."""
    payload = json.loads(input_json)
    result = {entry_fn}(payload)
    if hasattr(result, "model_dump"):
        return json.dumps(result.model_dump(mode="json"))
    return json.dumps(result)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="{method_name} adapter")
    parser.add_argument("input_file", help="Path to a JSON input file")
    args = parser.parse_args()

    data = Path(args.input_file).read_text()
    print(run(data))
'''


def render_adapter(
    method_name: str,
    method_version: str,
    entry_module: str,
    entry_fn: str,
) -> str:
    """Return a fully rendered adapter.py string."""
    return ADAPTER_TEMPLATE.format(
        method_name=method_name,
        method_version=method_version,
        entry_module=entry_module,
        entry_fn=entry_fn,
    )
