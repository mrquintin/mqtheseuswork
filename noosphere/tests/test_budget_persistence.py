"""Currents budget persistence tests."""

from __future__ import annotations

from noosphere.currents import budget as subject
from noosphere.currents.budget import HourlyBudgetGuard


def test_budget_persistence_preserves_same_hour_and_resets_next_hour(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "currents_budget.json"
    monkeypatch.setattr(
        subject,
        "_current_hour_iso",
        lambda: "2026-04-29T12:00:00+00:00",
    )
    guard = HourlyBudgetGuard(max_prompt_tokens=1000, max_completion_tokens=500)
    guard.charge(123, 45)
    guard.save(path)

    same_hour = HourlyBudgetGuard.load(path)
    assert same_hour.window_start_iso == "2026-04-29T12:00:00+00:00"
    assert same_hour.prompt_tokens == 123
    assert same_hour.completion_tokens == 45

    monkeypatch.setattr(
        subject,
        "_current_hour_iso",
        lambda: "2026-04-29T13:00:00+00:00",
    )
    next_hour = HourlyBudgetGuard.load(path)
    assert next_hour.window_start_iso == "2026-04-29T13:00:00+00:00"
    assert next_hour.prompt_tokens == 0
    assert next_hour.completion_tokens == 0
