"""Minimal Server-Sent Events frame formatter."""
from __future__ import annotations

import json
from typing import Any


def format_sse(event: str, data: Any) -> str:
    """Format a single SSE frame.

    ``data`` is JSON-encoded unless it's already a string. String payloads
    are emitted verbatim — callers that want JSON encoding for strings
    should wrap them in a dict or pre-serialize.
    """
    body = data if isinstance(data, str) else json.dumps(data, default=str)
    # An event can contain multiple data lines; we keep it simple and
    # escape newlines as multi-line `data:` frames.
    data_lines = body.split("\n")
    data_payload = "\n".join(f"data: {line}" for line in data_lines)
    return f"event: {event}\n{data_payload}\n\n"
