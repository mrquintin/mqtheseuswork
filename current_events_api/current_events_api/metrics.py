"""Minimal Prometheus text renderer for the Currents service."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from threading import Lock


def _label_key(labels: Mapping[str, str] | None) -> tuple[tuple[str, str], ...]:
    if not labels:
        return ()
    return tuple(sorted((str(k), str(v)) for k, v in labels.items()))


def _format_labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    parts = []
    for key, value in labels:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        parts.append(f'{key}="{escaped}"')
    return "{" + ",".join(parts) + "}"


class Metrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: dict[str, dict[tuple[tuple[str, str], ...], float]] = defaultdict(dict)
        self._gauges: dict[str, dict[tuple[tuple[str, str], ...], float]] = defaultdict(dict)

    def inc(self, name: str, labels: Mapping[str, str] | None = None, value: float = 1.0) -> None:
        key = _label_key(labels)
        with self._lock:
            self._counters[name][key] = self._counters[name].get(key, 0.0) + value

    def set_gauge(self, name: str, value: float, labels: Mapping[str, str] | None = None) -> None:
        key = _label_key(labels)
        with self._lock:
            self._gauges[name][key] = value

    def render(self) -> str:
        lines: list[str] = []
        with self._lock:
            counters = {name: dict(rows) for name, rows in self._counters.items()}
            gauges = {name: dict(rows) for name, rows in self._gauges.items()}
        for name in sorted(counters):
            lines.append(f"# TYPE {name} counter")
            for labels, value in sorted(counters[name].items()):
                lines.append(f"{name}{_format_labels(labels)} {value:g}")
        for name in sorted(gauges):
            lines.append(f"# TYPE {name} gauge")
            for labels, value in sorted(gauges[name].items()):
                lines.append(f"{name}{_format_labels(labels)} {value:g}")
        return "\n".join(lines) + "\n"
