"""PyQt6 widget that renders the live argument map.

Sits next to the transcript pane in the three-pane dashboard. The
widget is a *consumer* of :class:`ArgumentMapBuilder` events — it
never blocks the builder, and it never reaches into the builder's
internal state. Events arrive on the builder thread and are marshalled
to the Qt thread via :class:`pyqtSignal`.

The layout is a force-directed simulation that runs on a Qt timer
(20 fps). New nodes pulse for ``BuilderConfig.pulse_seconds``; the
pulse is just an animated ring radius, not a heavy effect.

If PyQt6 is not installed (CI / headless test boxes), this module
imports lazily and exposes ``ArgumentMapWidget = None`` so the rest
of the package can keep working.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import Optional

try:
    from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, pyqtSignal
    from PyQt6.QtGui import (
        QBrush,
        QColor,
        QFont,
        QPainter,
        QPen,
    )
    from PyQt6.QtWidgets import (
        QGraphicsScene,
        QGraphicsView,
        QLabel,
        QVBoxLayout,
        QWidget,
    )
    _QT_AVAILABLE = True
except Exception:  # pragma: no cover - exercised on headless CI
    _QT_AVAILABLE = False

from ..argument_map_builder import (
    ArgumentMapBuilder,
    BuilderEvent,
    RELATION_ASKS_ABOUT,
    RELATION_CONTRADICTS,
    RELATION_REFINES,
    RELATION_SUPPORTS,
)


_SPEAKER_PALETTE = [
    "#1565c0",
    "#6a1b9a",
    "#00838f",
    "#ef6c00",
    "#37474f",
    "#c2185b",
]


_TYPE_FILL = {
    "empirical": "#e3f2fd",
    "normative": "#f3e5f5",
    "methodological": "#e0f7fa",
    "predictive": "#fff3e0",
    "definitional": "#eceff1",
    "question": "#fafafa",
}


_STATE_RING = {
    "active": "#bdbdbd",
    "amber": "#ffb300",
    "red": "#e53935",
    "answered": "#43a047",
}


_RELATION_COLOR = {
    RELATION_SUPPORTS: "#2e7d32",
    RELATION_CONTRADICTS: "#c62828",
    RELATION_REFINES: "#1565c0",
    RELATION_ASKS_ABOUT: "#9e9e9e",
}


@dataclass
class _NodeView:
    node_id: str
    text: str
    speaker: str
    claim_type: str
    state: str
    is_question: bool
    seen_count: int
    pulse_until: float
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0


@dataclass
class _EdgeView:
    src: str
    dst: str
    relation: str
    confidence: float


if _QT_AVAILABLE:

    class ArgumentMapWidget(QWidget):
        """Live force-directed view of an argument map.

        Subscribe by passing the widget's :py:meth:`on_event` to the
        builder's ``on_event`` argument. Events are marshalled across
        threads via a Qt signal.
        """

        # cross-thread bridge — builder thread emits, Qt thread receives.
        eventReceived = pyqtSignal(object)

        def __init__(
            self,
            builder: Optional[ArgumentMapBuilder] = None,
            parent: Optional[QWidget] = None,
        ) -> None:
            super().__init__(parent)
            self._nodes: dict[str, _NodeView] = {}
            self._edges: list[_EdgeView] = []
            self._speaker_color: dict[str, str] = {}
            self._drift_value = 0.0
            self._drift_flagged = False

            self._scene = QGraphicsScene(self)
            self._view = QGraphicsView(self._scene, self)
            self._view.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            self._view.setBackgroundBrush(QBrush(QColor("#fafafa")))

            self._status = QLabel(self)
            self._status.setText("argument map: idle")
            self._status.setStyleSheet("color:#555;padding:4px 6px;")

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            layout.addWidget(self._status)
            layout.addWidget(self._view, 1)

            self.eventReceived.connect(self._on_event_qt)

            self._timer = QTimer(self)
            self._timer.setInterval(50)  # 20 fps; smooth enough, not heavy
            self._timer.timeout.connect(self._tick)
            self._timer.start()

            self._builder = builder
            if builder is not None:
                # Replay any state already present (eg. when a builder
                # was warmed up before the widget was constructed).
                snap = builder.snapshot()
                for nd in snap["nodes"]:
                    self._upsert_node_dict(nd)
                for ed in snap["edges"]:
                    self._edges.append(
                        _EdgeView(
                            src=ed["src"],
                            dst=ed["dst"],
                            relation=ed["relation"],
                            confidence=ed.get("confidence", 0.0),
                        )
                    )

        # ── public ────────────────────────────────────────────────
        def on_event(self, event: BuilderEvent) -> None:
            """Thread-safe entry point for the builder."""

            self.eventReceived.emit(event)

        # ── Qt-side handler ───────────────────────────────────────
        def _on_event_qt(self, event: BuilderEvent) -> None:
            payload = event.payload or {}
            if event.kind in ("node_added", "node_updated", "unresolved"):
                self._upsert_node_dict(payload)
            elif event.kind == "edge_added":
                self._edges.append(
                    _EdgeView(
                        src=payload["src"],
                        dst=payload["dst"],
                        relation=payload["relation"],
                        confidence=payload.get("confidence", 0.0),
                    )
                )
            elif event.kind == "drift":
                self._drift_value = float(payload.get("drift", 0.0))
                self._drift_flagged = bool(payload.get("flagged", False))
            self._refresh_status()

        def _upsert_node_dict(self, payload: dict) -> None:
            nid = payload.get("node_id")
            if not nid:
                return
            existing = self._nodes.get(nid)
            if existing is None:
                rect = self._view.viewport().rect()
                cx = rect.width() / 2 if rect.width() else 400.0
                cy = rect.height() / 2 if rect.height() else 300.0
                # Place new nodes near the centre with a small jitter so
                # the layout sim has room to push them apart.
                jitter = 30.0
                node = _NodeView(
                    node_id=nid,
                    text=payload.get("text", ""),
                    speaker=payload.get("speaker", "unknown"),
                    claim_type=payload.get("claim_type", "empirical"),
                    state=payload.get("state", "active"),
                    is_question=bool(payload.get("is_question")),
                    seen_count=int(payload.get("seen_count", 1)),
                    pulse_until=float(payload.get("pulse_until", 0.0)),
                    x=cx + (random.random() - 0.5) * jitter,
                    y=cy + (random.random() - 0.5) * jitter,
                )
                self._nodes[nid] = node
            else:
                existing.text = payload.get("text", existing.text)
                existing.speaker = payload.get("speaker", existing.speaker)
                existing.claim_type = payload.get("claim_type", existing.claim_type)
                existing.state = payload.get("state", existing.state)
                existing.is_question = bool(payload.get("is_question", existing.is_question))
                existing.seen_count = int(payload.get("seen_count", existing.seen_count))
                existing.pulse_until = float(payload.get("pulse_until", existing.pulse_until))

        def _refresh_status(self) -> None:
            n = len(self._nodes)
            e = len(self._edges)
            unresolved = sum(
                1 for v in self._nodes.values() if v.is_question and v.state in ("amber", "red")
            )
            drift = "drifting" if self._drift_flagged else "centered"
            self._status.setText(
                f"argument map: {n} claims · {e} relations · {unresolved} unresolved · {drift} ({self._drift_value:.2f})"
            )

        # ── physics tick ──────────────────────────────────────────
        def _tick(self) -> None:
            if not self._nodes:
                self._scene.clear()
                return
            self._step_layout()
            self._render()

        def _step_layout(self) -> None:
            rect = self._view.viewport().rect()
            w = max(200, rect.width())
            h = max(200, rect.height())
            ids = list(self._nodes.keys())
            n = len(ids)
            if n == 0:
                return
            k = math.sqrt((w * h) / n)
            disp: dict[str, list[float]] = {nid: [0.0, 0.0] for nid in ids}
            for i in range(n):
                a = self._nodes[ids[i]]
                for j in range(i + 1, n):
                    b = self._nodes[ids[j]]
                    dx = a.x - b.x
                    dy = a.y - b.y
                    dist = math.sqrt(dx * dx + dy * dy) or 0.5
                    if dist > 5 * k:
                        continue
                    f = (k * k) / dist
                    disp[a.node_id][0] += dx / dist * f
                    disp[a.node_id][1] += dy / dist * f
                    disp[b.node_id][0] -= dx / dist * f
                    disp[b.node_id][1] -= dy / dist * f
            for e in self._edges:
                a = self._nodes.get(e.src)
                b = self._nodes.get(e.dst)
                if not a or not b:
                    continue
                dx = a.x - b.x
                dy = a.y - b.y
                dist = math.sqrt(dx * dx + dy * dy) or 0.5
                f = (dist * dist) / k
                disp[e.src][0] -= dx / dist * f
                disp[e.src][1] -= dy / dist * f
                disp[e.dst][0] += dx / dist * f
                disp[e.dst][1] += dy / dist * f
            damp = 0.18
            for nid, (dx, dy) in disp.items():
                node = self._nodes[nid]
                mag = math.sqrt(dx * dx + dy * dy) or 0.5
                cap = min(mag, 30.0)
                node.x += dx / mag * cap * damp
                node.y += dy / mag * cap * damp
                node.x = max(20.0, min(w - 20.0, node.x))
                node.y = max(20.0, min(h - 20.0, node.y))

        def _render(self) -> None:
            scene = self._scene
            scene.clear()
            now = time.time()

            for e in self._edges:
                a = self._nodes.get(e.src)
                b = self._nodes.get(e.dst)
                if not a or not b:
                    continue
                color = QColor(_RELATION_COLOR.get(e.relation, "#888"))
                pen = QPen(color)
                pen.setWidthF(1.4)
                if e.relation == RELATION_ASKS_ABOUT:
                    pen.setStyle(Qt.PenStyle.DashLine)
                scene.addLine(a.x, a.y, b.x, b.y, pen)

            for node in self._nodes.values():
                fill = QColor(_TYPE_FILL.get(node.claim_type, "#ffffff"))
                ring = QColor(_STATE_RING.get(node.state, "#777"))
                speaker_color = QColor(self._color_for_speaker(node.speaker))
                radius = 10.0 + min(10.0, 2.0 * (node.seen_count - 1))
                # pulse ring for newly added / re-touched nodes
                if node.pulse_until > now:
                    glow = QPen(speaker_color)
                    glow.setWidthF(3.0)
                    extra = 6.0 * ((node.pulse_until - now) / max(0.01, 1.5))
                    scene.addEllipse(
                        node.x - radius - extra,
                        node.y - radius - extra,
                        2 * (radius + extra),
                        2 * (radius + extra),
                        glow,
                        QBrush(Qt.GlobalColor.transparent),
                    )
                # base body
                body_pen = QPen(ring)
                body_pen.setWidthF(2.0)
                scene.addEllipse(
                    node.x - radius,
                    node.y - radius,
                    2 * radius,
                    2 * radius,
                    body_pen,
                    QBrush(fill),
                )
                # speaker dot in the centre
                spk_pen = QPen(speaker_color)
                spk_pen.setWidthF(1.0)
                scene.addEllipse(
                    node.x - 3,
                    node.y - 3,
                    6,
                    6,
                    spk_pen,
                    QBrush(speaker_color),
                )
                label = node.text[:50] + ("…" if len(node.text) > 50 else "")
                text_item = scene.addText(label, QFont("Helvetica", 9))
                text_item.setDefaultTextColor(QColor("#222"))
                text_item.setPos(node.x + radius + 4, node.y - 8)

            scene.setSceneRect(QRectF(0, 0, self._view.viewport().width(), self._view.viewport().height()))

        def _color_for_speaker(self, speaker: str) -> str:
            if speaker not in self._speaker_color:
                idx = len(self._speaker_color) % len(_SPEAKER_PALETTE)
                self._speaker_color[speaker] = _SPEAKER_PALETTE[idx]
            return self._speaker_color[speaker]

else:  # pragma: no cover - headless

    ArgumentMapWidget = None  # type: ignore[assignment]


__all__ = ["ArgumentMapWidget"]
