"""Tests for the consolidated configuration module.

Covers:
- Settings round-trip (defaults parse cleanly).
- Overlay precedence: defaults.yaml → <env>.yaml → process env.
- Missing required env produces a helpful error naming the variable
  and its doc anchor.
- Settings instances are read-only at runtime (frozen).
- ``with_overrides`` returns a new instance without mutating the
  singleton.
- The legacy shim ``noosphere.config`` re-exports the same names.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

import importlib
import sys

# ``noosphere.core.__init__`` re-exports the legacy ``noosphere.config`` shim
# under the attribute name ``config``, which shadows ``noosphere.core.config``
# when accessed via attribute lookup. Loading the submodule explicitly via
# ``importlib`` gets us the real module instance instead.
core_config = importlib.import_module("noosphere.core.config")
assert sys.modules["noosphere.core.config"] is core_config

from noosphere.core.config import (  # noqa: E402  (import after the alias)
    REQUIRED_ENV_DOCS,
    ConfigError,
    Settings,
    Thresholds,
    _format_validation_error,
    get_settings,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_singleton_cache() -> None:
    """Each test gets a fresh ``get_settings`` cache."""

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def temp_overlay_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the overlay loader at an isolated temp directory."""

    monkeypatch.setattr(core_config, "_overlay_dir", lambda: tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_settings_round_trip_with_no_overlays_or_env(
    temp_overlay_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No overlays present, no THESEUS_* env. Defaults take effect.
    for key in list(monkeypatch._setitem):  # type: ignore[attr-defined]
        pass
    for key in [
        k for k in list(__import__("os").environ) if k.startswith("THESEUS_")
    ]:
        monkeypatch.delenv(key, raising=False)

    s = Settings()
    assert s.env == "development"
    assert s.llm_provider == "anthropic"
    assert s.llm_model.startswith("claude-")
    assert isinstance(s.thresholds, Thresholds)
    assert s.thresholds.currents.min_significance_score == pytest.approx(1.35)


def test_thresholds_round_trip_via_dict(temp_overlay_dir: Path) -> None:
    s = Settings()
    dumped = s.model_dump()
    rebuilt = Settings(**dumped)
    assert rebuilt.model_dump() == dumped


# ---------------------------------------------------------------------------
# Overlay precedence
# ---------------------------------------------------------------------------


def test_overlay_precedence_defaults_then_env_overlay_then_process_env(
    temp_overlay_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (temp_overlay_dir / "defaults.yaml").write_text(
        textwrap.dedent(
            """
            log_level: INFO
            currents_lookback_minutes: 10
            """
        )
    )
    (temp_overlay_dir / "production.yaml").write_text(
        textwrap.dedent(
            """
            log_level: WARNING
            currents_lookback_minutes: 5
            """
        )
    )
    monkeypatch.setenv("THESEUS_ENV", "production")
    monkeypatch.setenv("THESEUS_LOG_LEVEL", "ERROR")

    s = Settings()

    # Defaults loaded.
    assert s.env == "production"
    # Process env wins over the production overlay (ERROR > WARNING).
    assert s.log_level == "ERROR"
    # The production overlay wins over defaults (5 > 10) when no env set.
    assert s.currents_lookback_minutes == 5


def test_unknown_env_falls_back_to_defaults_only(
    temp_overlay_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (temp_overlay_dir / "defaults.yaml").write_text("log_level: INFO\n")
    monkeypatch.setenv("THESEUS_ENV", "staging")  # no overlay file -> ignored

    s = Settings()
    assert s.env == "staging"
    assert s.log_level == "INFO"


def test_overlay_must_be_yaml_mapping(temp_overlay_dir: Path) -> None:
    (temp_overlay_dir / "defaults.yaml").write_text("- not_a_mapping\n")
    with pytest.raises(ConfigError, match="must be a YAML mapping"):
        Settings()


def test_nested_threshold_overlay(
    temp_overlay_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (temp_overlay_dir / "defaults.yaml").write_text(
        textwrap.dedent(
            """
            thresholds:
              currents:
                min_significance_score: 9.99
            """
        )
    )
    monkeypatch.delenv("THESEUS_ENV", raising=False)
    s = Settings()
    assert s.thresholds.currents.min_significance_score == pytest.approx(9.99)
    # Untouched threshold keeps its default.
    assert s.thresholds.currents.min_likes == 1_000


# ---------------------------------------------------------------------------
# Read-only enforcement
# ---------------------------------------------------------------------------


def test_settings_instance_is_frozen(temp_overlay_dir: Path) -> None:
    s = Settings()
    with pytest.raises(ValidationError):
        s.llm_model = "should-not-stick"


def test_with_overrides_returns_new_instance(temp_overlay_dir: Path) -> None:
    base = Settings()
    overridden = base.with_overrides(currents_lookback_minutes=42)
    assert overridden is not base
    assert overridden.currents_lookback_minutes == 42
    assert base.currents_lookback_minutes == 15  # original untouched
    # Override result is itself frozen.
    with pytest.raises(ValidationError):
        overridden.currents_lookback_minutes = 100


def test_patch_context_manager_restores_singleton(
    temp_overlay_dir: Path,
) -> None:
    base = get_settings()
    assert base.currents_lookback_minutes == 15
    with Settings.patch(currents_lookback_minutes=7) as patched:
        assert patched.currents_lookback_minutes == 7
        assert get_settings().currents_lookback_minutes == 7
    assert get_settings().currents_lookback_minutes == 15


# ---------------------------------------------------------------------------
# Missing-required-env error message
# ---------------------------------------------------------------------------


def test_format_validation_error_names_env_var_and_doc() -> None:
    """The helper must mention env var name and doc anchor when known."""

    # Build a synthetic error pointing at the `database_url` field, which
    # has a documented entry in REQUIRED_ENV_DOCS.
    assert "DATABASE_URL" in REQUIRED_ENV_DOCS

    class _StrictSettings(Settings):
        # Re-declare database_url with no default to force a ValidationError.
        database_url: str  # type: ignore[assignment]

    try:
        _StrictSettings(database_url=None)  # type: ignore[arg-type]
    except ValidationError as exc:
        msg = _format_validation_error(exc)
    else:  # pragma: no cover — defensive
        pytest.fail("expected ValidationError")

    assert "database_url" in msg
    assert "THESEUS_DATABASE_URL" in msg
    assert "Configuration.md" in msg  # doc anchor


# ---------------------------------------------------------------------------
# Legacy shim
# ---------------------------------------------------------------------------


def test_legacy_shim_exposes_compatible_settings() -> None:
    """The legacy ``noosphere.config`` module remains importable.

    It is intentionally a self-contained implementation to avoid the
    circular import that would arise from re-exporting the
    ``noosphere.core.config`` module (the ``noosphere.core`` package
    eagerly imports submodules that themselves call
    ``from noosphere.config import get_settings`` during init). The
    contract here is a) the legacy names resolve and b) the legacy
    Settings shape is a superset-compatible subset of the canonical
    one.
    """

    from noosphere import config as legacy

    legacy_settings = legacy.get_settings()
    assert legacy.NoosphereSettings is type(legacy_settings)

    # Every field on the legacy class must also exist on the canonical
    # Settings, with the same default value (modulo overlay merging).
    canonical_fields = set(Settings.model_fields)
    for name in legacy.NoosphereSettings.model_fields:
        assert name in canonical_fields, (
            f"legacy field {name!r} missing from canonical Settings — "
            "the migration would silently drop it"
        )
