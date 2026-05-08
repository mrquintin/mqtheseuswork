"""Tests for the curated failure-mode catalog subsystem."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import pytest
import yaml

from noosphere.methods import failure_modes as fm


# ── Catalog validation ────────────────────────────────────────────────


def _write(path: Path, payload: dict) -> Path:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _good_mode(name: str = "x") -> dict:
    return {
        "name": name,
        "description": "First sentence describing the failure. Second sentence on detection.",
        "worked_example": "A real or constructed case where this fired.",
        "trigger_conditions": "Free text trigger conditions.",
        "mitigation": "What to do.",
        "severity": "medium",
        "citations": [],
        "public": True,
    }


def test_valid_catalog_loads(tmp_path: Path) -> None:
    cat_path = _write(
        tmp_path / "demo.FAILURES.yaml",
        {"method": "demo", "modes": [_good_mode()]},
    )
    catalog = fm.load_catalog("demo", methods_dir=tmp_path)
    assert catalog.method == "demo"
    assert len(catalog.modes) == 1
    assert catalog.modes[0].severity == "medium"
    assert cat_path.exists()


def test_missing_catalog_raises(tmp_path: Path) -> None:
    with pytest.raises(fm.FailureCatalogError, match="missing failure-mode catalog"):
        fm.load_catalog("nope", methods_dir=tmp_path)


def test_empty_modes_without_optout_rejected(tmp_path: Path) -> None:
    _write(tmp_path / "demo.FAILURES.yaml", {"method": "demo", "modes": []})
    with pytest.raises(fm.FailureCatalogError, match="at least one mode"):
        fm.load_catalog("demo", methods_dir=tmp_path)


def test_deliberately_empty_requires_two_sentence_justification(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "demo.FAILURES.yaml",
        {
            "method": "demo",
            "failures": "deliberately-empty",
            "justification": "Only one sentence here.",
        },
    )
    with pytest.raises(fm.FailureCatalogError, match="at least two sentences"):
        fm.load_catalog("demo", methods_dir=tmp_path)


def test_deliberately_empty_accepted_with_justification(tmp_path: Path) -> None:
    _write(
        tmp_path / "demo.FAILURES.yaml",
        {
            "method": "demo",
            "failures": "deliberately-empty",
            "justification": (
                "This is a pure data-conversion method with no "
                "interpretation step. There is nothing to fail in a "
                "way that maps to the catalog shape."
            ),
        },
    )
    catalog = fm.load_catalog("demo", methods_dir=tmp_path)
    assert catalog.failures == "deliberately-empty"
    assert catalog.modes == []


def test_short_description_rejected(tmp_path: Path) -> None:
    bad = _good_mode()
    bad["description"] = "One sentence only no separator"
    _write(tmp_path / "demo.FAILURES.yaml", {"method": "demo", "modes": [bad]})
    with pytest.raises(fm.FailureCatalogError, match="at least two sentences"):
        fm.load_catalog("demo", methods_dir=tmp_path)


def test_invalid_severity_rejected(tmp_path: Path) -> None:
    bad = _good_mode()
    bad["severity"] = "catastrophic"
    _write(tmp_path / "demo.FAILURES.yaml", {"method": "demo", "modes": [bad]})
    with pytest.raises(fm.FailureCatalogError):
        fm.load_catalog("demo", methods_dir=tmp_path)


def test_load_all_catalogs_picks_up_every_file(tmp_path: Path) -> None:
    _write(tmp_path / "a.FAILURES.yaml", {"method": "a", "modes": [_good_mode()]})
    _write(tmp_path / "b.FAILURES.yaml", {"method": "b", "modes": [_good_mode()]})
    catalogs = fm.load_all_catalogs(methods_dir=tmp_path)
    assert set(catalogs) == {"a", "b"}


def test_shipped_catalogs_validate() -> None:
    """The catalogs that live next to real methods must validate at
    module import time. Each method we shipped a catalog for in scope
    must be present here."""
    catalogs = fm.load_all_catalogs()
    for required in (
        "six_layer_coherence",
        "contradiction_geometry",
        "extract_methodology",
        "synthesize_conclusion",
    ):
        assert required in catalogs, f"missing shipped catalog: {required}"
        cat = catalogs[required]
        assert cat.failures != "deliberately-empty", required
        assert cat.modes, required


# ── Match query + cache ────────────────────────────────────────────────


def _three_mode_catalog(tmp_path: Path) -> Path:
    modes = [
        {
            **_good_mode("trigger_a"),
            "trigger_conditions": "specific trigger phrase widget alpha beta",
        },
        {
            **_good_mode("trigger_b"),
            "trigger_conditions": "completely unrelated catalog rocketry orbital physics",
        },
        {
            **_good_mode("trigger_c"),
            "trigger_conditions": "another distinct topic neural protein folding",
        },
    ]
    _write(tmp_path / "demo.FAILURES.yaml", {"method": "demo", "modes": modes})
    return tmp_path


def test_failure_modes_for_filters_by_threshold(tmp_path: Path) -> None:
    methods_dir = _three_mode_catalog(tmp_path)
    cache = tmp_path / "cache.json"
    text = "specific trigger phrase widget alpha appears in this conclusion."
    result = fm.failure_modes_for(
        "demo",
        text,
        methods_dir=methods_dir,
        cache_path=cache,
        threshold=0.4,
    )
    matched = {m.mode_name for m in result.matches if m.matched}
    assert matched == {"trigger_a"}


def test_failure_modes_cache_persists_decision(tmp_path: Path) -> None:
    methods_dir = _three_mode_catalog(tmp_path)
    cache = tmp_path / "cache.json"
    text = "specific trigger phrase widget alpha"

    first = fm.failure_modes_for(
        "demo", text, methods_dir=methods_dir, cache_path=cache
    )
    assert cache.exists()
    raw = json.loads(cache.read_text("utf-8"))
    assert first.input_hash in raw

    # Second call must hit the cache exactly — even if we hand it a
    # matcher that would explode if invoked.
    def _exploding(_mode, _text):  # pragma: no cover - guard
        raise AssertionError("matcher should not be called on cache hit")

    second = fm.failure_modes_for(
        "demo",
        text,
        methods_dir=methods_dir,
        cache_path=cache,
        matcher=_exploding,
    )
    assert second.input_hash == first.input_hash
    assert [m.model_dump() for m in second.matches] == [
        m.model_dump() for m in first.matches
    ]


def test_matcher_override(tmp_path: Path) -> None:
    methods_dir = _three_mode_catalog(tmp_path)
    cache = tmp_path / "cache.json"

    def _always_one(_mode, _text):
        return 1.0, "stub"

    result = fm.failure_modes_for(
        "demo",
        "anything",
        methods_dir=methods_dir,
        cache_path=cache,
        matcher=_always_one,
        threshold=0.5,
    )
    assert all(m.matched for m in result.matches)
    assert all(m.score == 1.0 for m in result.matches)


def test_matched_modes_resolves_objects(tmp_path: Path) -> None:
    methods_dir = _three_mode_catalog(tmp_path)
    cache = tmp_path / "cache.json"
    catalog = fm.load_catalog("demo", methods_dir=methods_dir)
    result = fm.failure_modes_for(
        "demo",
        "specific trigger phrase widget alpha beta",
        methods_dir=methods_dir,
        cache_path=cache,
        threshold=0.4,
    )
    modes = fm.matched_modes(result, catalog)
    assert {m.name for m in modes} == {"trigger_a"}


def test_extract_text_handles_objects() -> None:
    class _Stub:
        text = "alpha beta gamma"

    assert fm._extract_conclusion_text(_Stub()) == "alpha beta gamma"
    assert fm._extract_conclusion_text({"text": "x"}) == "x"
    assert fm._extract_conclusion_text("plain") == "plain"


# ── Scaffold + lint ────────────────────────────────────────────────────


def test_scaffold_writes_template(tmp_path: Path) -> None:
    path = fm.scaffold_catalog("brand_new", methods_dir=tmp_path)
    assert path.exists()
    text = path.read_text("utf-8")
    assert "method: brand_new" in text
    assert "example_failure_mode" in text


def test_scaffold_refuses_overwrite(tmp_path: Path) -> None:
    fm.scaffold_catalog("brand_new", methods_dir=tmp_path)
    with pytest.raises(fm.FailureCatalogError, match="refusing to overwrite"):
        fm.scaffold_catalog("brand_new", methods_dir=tmp_path)


def test_lint_all_round_trips(tmp_path: Path) -> None:
    _write(
        tmp_path / "demo.FAILURES.yaml",
        {"method": "demo", "modes": [_good_mode()]},
    )
    catalogs = fm.lint_all(methods_dir=tmp_path)
    assert "demo" in catalogs


# ── Reviewer integration ──────────────────────────────────────────────


def _force_match_all(monkeypatch, target_module) -> None:
    """Replace the LLM-assisted matcher with a deterministic stub
    that flags every mode as matched. Used to exercise the integration
    paths in the reviewers without depending on the strength of the
    lexical-overlap heuristic."""

    def _stub(method, conclusion, **_kwargs):
        catalog = fm.load_catalog(method)
        return fm.FailureMatchResult(
            method=method,
            input_hash="stub" * 8,
            model_name="stub",
            prompt_version="stub",
            threshold=0.0,
            matches=[
                fm.FailureMatch(
                    mode_name=m.name, score=1.0, matched=True, rationale="stub"
                )
                for m in catalog.modes
            ],
        )

    monkeypatch.setattr(target_module, "failure_modes_for", _stub)


def test_blindspot_reviewer_emits_failure_mode_findings(monkeypatch) -> None:
    """When the matcher reports a curated mode fires, the blindspot
    reviewer must emit a finding that cites that mode by name."""

    from noosphere.peer_review import blindspot

    _force_match_all(monkeypatch, blindspot)

    class _StubConclusion:
        id = "c-stub"
        text = "anything"
        reasoning = ""

    findings = blindspot._findings_from_failure_modes(
        _StubConclusion(),
        {"methods_used": [{"name": "synthesize_conclusion"}]},
    )
    cited = [f for f in findings if f.category == "failure_mode_prior"]
    assert cited, "expected at least one failure-mode-cited finding"
    sample = cited[0]
    assert any("failure_mode=" in e for e in sample.evidence)
    assert any("method=synthesize_conclusion" in e for e in sample.evidence)


def test_blindspot_reviewer_flags_missing_catalog(monkeypatch) -> None:
    from noosphere.peer_review import blindspot

    class _StubConclusion:
        id = "c-stub"
        text = "anything"
        reasoning = ""

    findings = blindspot._findings_from_failure_modes(
        _StubConclusion(),
        {"methods_used": [{"name": "this_method_has_no_catalog_xyz"}]},
    )
    info = [f for f in findings if f.category == "missing_failure_catalog"]
    assert info, "missing catalog must surface as an info-severity finding"


def test_inverse_reviewer_returns_top_severity(monkeypatch) -> None:
    from noosphere.peer_review import inverse

    _force_match_all(monkeypatch, inverse)

    class _StubConclusion:
        id = "c-stub"
        text = "anything"
        reasoning = ""

    findings = inverse._findings(
        _StubConclusion(),
        {"methods_used": [{"name": "extract_methodology"}]},
    )
    assert len(findings) == 1, "inverse should aggregate to one finding per method"
    finding = findings[0]
    assert finding.category == "inverse_failure_mode"
    assert any("failure_mode=" in e for e in finding.evidence)
    # The shipped extract_methodology catalog has at least one
    # high-severity entry; inverse should pick a high-severity mode and
    # therefore emit a blocker.
    assert finding.severity == "blocker"
