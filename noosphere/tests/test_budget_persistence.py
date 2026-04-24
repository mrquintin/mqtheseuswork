"""Budget persistence tests (prompt 05 / 15).

HourlyBudgetGuard.load(path) / implicit _save() must round-trip counters
across process restarts within the same hour window, and must reset on
hour rollover.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from noosphere.currents.budget import HourlyBudgetGuard


def test_budget_roundtrip(tmp_path: Path):
    path = tmp_path / "currents_budget.json"

    g1 = HourlyBudgetGuard.load(path)
    g1.record(100, 50)

    g2 = HourlyBudgetGuard.load(path)
    snap = g2.snapshot()
    assert snap.prompt_tokens == 100
    assert snap.completion_tokens == 50


def test_budget_save_is_atomic_on_disk(tmp_path: Path):
    path = tmp_path / "currents_budget.json"
    g = HourlyBudgetGuard.load(path)
    g.record(10, 5)
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["prompt_tokens"] == 10
    assert data["completion_tokens"] == 5
    assert "window_start_iso" in data


def test_budget_rolls_over_on_new_hour(tmp_path: Path):
    path = tmp_path / "currents_budget.json"
    # Seed a budget file with a window_start_iso that is 2 hours in the past.
    stale_start = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    path.write_text(
        json.dumps(
            {
                "window_start_iso": stale_start,
                "prompt_tokens": 999,
                "completion_tokens": 888,
            }
        )
    )

    g = HourlyBudgetGuard.load(path)
    snap = g.snapshot()
    # On load, the stale window triggers a roll: counters reset to 0.
    assert snap.prompt_tokens == 0
    assert snap.completion_tokens == 0


def test_budget_corrupt_file_starts_fresh(tmp_path: Path):
    path = tmp_path / "currents_budget.json"
    path.write_text("{ not json")
    g = HourlyBudgetGuard.load(path)
    snap = g.snapshot()
    assert snap.prompt_tokens == 0
    assert snap.completion_tokens == 0
