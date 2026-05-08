"""A small, low-attention live panel showing each speaker's consistency dot.

Design constraints:

* The panel must not steal attention from the main transcript view —
  one row per active speaker, a single coloured dot, the speaker name,
  and a tooltip with the reason. No animation, no sound, no toasts.
* Qt is imported lazily so this module can be imported in test
  environments where PyQt6 is not installed (the panel object then
  exposes a no-op fallback that records updates for inspection).

Usage from the dashboard::

    from dialectic.ui.speaker_panel import SpeakerConsistencyPanel
    panel = SpeakerConsistencyPanel(speakers=["Founder", "Guest"])
    layout.addWidget(panel.widget())
    # On each new analyzer event:
    panel.update_verdict(verdict)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from ..speaker_consistency import ConsistencyLabel, ConsistencyVerdict


_LABEL_TEXT = {
    ConsistencyLabel.NO_BASELINE: "no baseline",
    ConsistencyLabel.CONSISTENT: "consistent",
    ConsistencyLabel.NOVEL: "novel",
    ConsistencyLabel.SHARP_DEPARTURE: "departure",
}


# ----------------------------------------------------------------------
# Headless fallback (used in tests / environments without PyQt6)
# ----------------------------------------------------------------------


@dataclass
class _SpeakerRowState:
    name: str
    label: ConsistencyLabel = ConsistencyLabel.NO_BASELINE
    reason: str = "No baseline profile loaded."
    color: str = "#888888"
    pattern: str = ""

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "label": self.label.value,
            "reason": self.reason,
            "color": self.color,
            "pattern": self.pattern,
        }


class _HeadlessPanel:
    """Drop-in for environments without PyQt6 — records state, draws nothing."""

    def __init__(self, speakers: Iterable[str]):
        self._rows: dict[str, _SpeakerRowState] = {
            s: _SpeakerRowState(name=s) for s in speakers
        }

    def widget(self):  # pragma: no cover — only meaningful when Qt loads
        return None

    def update_verdict(self, verdict: ConsistencyVerdict) -> None:
        row = self._rows.setdefault(verdict.speaker, _SpeakerRowState(name=verdict.speaker))
        row.label = verdict.label
        row.reason = verdict.reason
        row.color = verdict.dot_color
        row.pattern = verdict.classified_pattern

    def state(self) -> dict[str, dict]:
        return {k: v.as_dict() for k, v in self._rows.items()}

    def is_qt(self) -> bool:
        return False


# ----------------------------------------------------------------------
# Public factory
# ----------------------------------------------------------------------


class SpeakerConsistencyPanel:
    """Public wrapper that picks Qt or headless impl at construction time."""

    def __init__(self, speakers: Optional[Iterable[str]] = None):
        speakers = list(speakers or [])
        self._impl = _build_impl(speakers)

    def widget(self):
        return self._impl.widget()

    def update_verdict(self, verdict: ConsistencyVerdict) -> None:
        self._impl.update_verdict(verdict)

    def state(self) -> dict[str, dict]:
        if hasattr(self._impl, "state"):
            return self._impl.state()
        return {}

    def is_qt(self) -> bool:
        return getattr(self._impl, "is_qt", lambda: False)()


def _build_impl(speakers: list[str]):
    try:
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QColor, QPainter
        from PyQt6.QtWidgets import (
            QHBoxLayout,
            QLabel,
            QVBoxLayout,
            QWidget,
        )
    except Exception:
        return _HeadlessPanel(speakers)

    class _Dot(QLabel):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._color = QColor("#888888")
            self.setFixedSize(10, 10)

        def set_color(self, hex_str: str) -> None:
            self._color = QColor(hex_str)
            self.update()

        def paintEvent(self, _ev):  # noqa: N802 — Qt API
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setBrush(self._color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(0, 0, 10, 10)

    class _Row(QWidget):
        def __init__(self, name: str, parent=None):
            super().__init__(parent)
            self.name = name
            row = QHBoxLayout(self)
            row.setContentsMargins(4, 1, 4, 1)
            row.setSpacing(6)
            self.dot = _Dot(self)
            self.label = QLabel(name, self)
            self.status = QLabel("no baseline", self)
            self.status.setStyleSheet("color:#888;")
            row.addWidget(self.dot)
            row.addWidget(self.label, 1)
            row.addWidget(self.status)
            self.setToolTip("No baseline profile loaded.")

        def apply(self, verdict: ConsistencyVerdict) -> None:
            self.dot.set_color(verdict.dot_color)
            self.status.setText(_LABEL_TEXT[verdict.label])
            self.setToolTip(verdict.reason)

    class _QtPanel(QWidget):
        def __init__(self, speakers_: list[str]):
            super().__init__()
            self.setMaximumHeight(140)
            self.setObjectName("SpeakerConsistencyPanel")
            self._rows: dict[str, _Row] = {}
            outer = QVBoxLayout(self)
            outer.setContentsMargins(6, 4, 6, 4)
            outer.setSpacing(2)
            outer.addWidget(QLabel("Methodology mirror"))
            self._outer = outer
            for s in speakers_:
                self._add_row(s)

        def _add_row(self, name: str) -> _Row:
            row = _Row(name, self)
            self._rows[name] = row
            self._outer.addWidget(row)
            return row

        def update_verdict(self, verdict: ConsistencyVerdict) -> None:
            row = self._rows.get(verdict.speaker) or self._add_row(verdict.speaker)
            row.apply(verdict)

        def widget(self):
            return self

        def state(self) -> dict[str, dict]:
            out: dict[str, dict] = {}
            for name, row in self._rows.items():
                out[name] = {
                    "name": name,
                    "label": row.status.text(),
                    "reason": row.toolTip(),
                }
            return out

        def is_qt(self) -> bool:
            return True

    return _QtPanel(speakers)
