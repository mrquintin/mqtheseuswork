"""CI regression: mitigated attack checks from noosphere.redteam."""

from __future__ import annotations

from noosphere.redteam import run_attack_suite


def test_mitigated_attack_suite_passes() -> None:
    out = run_attack_suite()
    assert out["attack_suite_version"]
    assert all(out["results"].values())


def test_single_attack_class_filter() -> None:
    out = run_attack_suite(attack_class="temporal_backdating")
    assert set(out["results"].keys()) == {"temporal_backdating"}
