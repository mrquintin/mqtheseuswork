"""Unit tests for SP09 interlocutor (no heavy analyzer / sklearn imports)."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from dialectic.config import InterlocutorConfig
from dialectic.interlocutor import InterlocutorController, InterlocutorMode, InterventionKind


@dataclass
class _C:
    statement_a: str
    statement_b: str
    score: float
    timestamp: float
    speaker_a: str
    speaker_b: str


@dataclass
class _Loop:
    description: str
    opened_at: float
    last_referenced: float
    status: str = "open"
    related_text: str = ""


@dataclass
class _Seg:
    text: str
    speaker: str
    start_time: float
    end_time: float
    is_final: bool = True


def test_stand_down_blocks_contradiction() -> None:
    emitted: list = []

    def on_int(c, rid: str) -> None:
        emitted.append((c.kind, rid))

    with tempfile.TemporaryDirectory() as td:
        c = InterlocutorController(
            InterlocutorConfig(T_contradict=0.5),
            session_id="session_test",
            log_dir=Path(td),
            on_intervention=on_int,
        )
        c.set_mode(InterlocutorMode.PASSIVE)
        c.set_participants_opt_in(True)
        c.force_stand_down()
        c.feed_contradiction(
            _C("X is true", "X is false", 0.99, 10.0, "A", "A")  # type: ignore[arg-type]
        )
        assert emitted == []


def test_budget_caps_emissions() -> None:
    emitted: list = []

    def on_int(c, rid: str) -> None:
        emitted.append(rid)

    with tempfile.TemporaryDirectory() as td:
        c = InterlocutorController(
            InterlocutorConfig(
                T_contradict=0.5,
                budget_conversational_seconds=3600.0,
            ),
            session_id="session_test2",
            log_dir=Path(td),
            on_intervention=on_int,
        )
        c.set_mode(InterlocutorMode.PASSIVE)
        c.set_participants_opt_in(True)
        c.feed_contradiction(
            _C("p", "not p", 0.95, 1.0, "A", "B")  # type: ignore[arg-type]
        )
        assert len(emitted) == 1
        c.feed_contradiction(
            _C("q", "not q", 0.95, 2.0, "A", "B")  # type: ignore[arg-type]
        )
        assert len(emitted) == 1


def test_reflection_bundle_written() -> None:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        c = InterlocutorController(
            InterlocutorConfig(T_contradict=0.5),
            session_id="session_x",
            log_dir=p,
            on_intervention=lambda *_: None,
        )
        c.set_mode(InterlocutorMode.PASSIVE)
        c.set_participants_opt_in(True)
        c.feed_contradiction(
            _C("a", "b", 0.95, 1.0, "A", "B")  # type: ignore[arg-type]
        )
        out = c.save_reflection_bundle()
        assert out is not None and out.is_file()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["session_id"] == "session_x"
        assert len(data["interventions"]) >= 1


def test_prediction_trigger() -> None:
    emitted: list = []

    def on_int(c, rid: str) -> None:
        emitted.append(c.kind)

    with tempfile.TemporaryDirectory() as td:
        c = InterlocutorController(
            InterlocutorConfig(),
            session_id="session_p",
            log_dir=Path(td),
            on_intervention=on_int,
        )
        c.set_mode(InterlocutorMode.CONVERSATIONAL)
        c.set_participants_opt_in(True)
        seg = _Seg(
            text="I predict we will ship this quarter with 80% confidence.",
            speaker="Host",
            start_time=5.0,
            end_time=6.0,
        )
        c.feed_segment(seg)  # type: ignore[arg-type]
        assert InterventionKind.PREDICTION_RESOLUTION in emitted


def test_open_loop_after_delay() -> None:
    emitted: list = []

    def on_int(c, rid: str) -> None:
        emitted.append(c.kind)

    with tempfile.TemporaryDirectory() as td:
        c = InterlocutorController(
            InterlocutorConfig(),
            session_id="session_o",
            log_dir=Path(td),
            on_intervention=on_int,
        )
        c.set_mode(InterlocutorMode.PASSIVE)
        c.set_participants_opt_in(True)
        c.feed_segment(_Seg("hello", "Host", 100.0, 101.0))  # type: ignore[arg-type]
        c.feed_open_loop(
            _Loop("What about ethics?", 50.0, 50.0)  # type: ignore[arg-type]
        )
        assert InterventionKind.OPEN_QUESTION in emitted
