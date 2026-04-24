"""Tests for noosphere.frozen_support path resolver."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from noosphere import frozen_support


@pytest.fixture
def fresh_module():
    """Return a freshly reloaded frozen_support module so sys.frozen patches apply."""
    yield importlib.reload(frozen_support)
    importlib.reload(frozen_support)


def test_is_frozen_false_in_dev():
    assert frozen_support.is_frozen() is False


def test_bundle_dir_points_at_noosphere_root_in_dev():
    root = frozen_support.bundle_dir()
    assert root.is_dir()
    # In dev, bundle_dir() is the parent of the noosphere package directory
    # (i.e. the repo's `noosphere/` folder, which contains the inner `noosphere/` package).
    assert (root / "noosphere" / "__init__.py").exists()


def test_data_dir_is_writable(tmp_path, monkeypatch):
    monkeypatch.setenv("THESEUS_DATA_DIR", str(tmp_path / "nh"))
    d = frozen_support.data_dir()
    assert d == tmp_path / "nh"
    assert d.is_dir()
    probe = d / "probe.txt"
    probe.write_text("ok")
    assert probe.read_text() == "ok"


def test_data_dir_respects_env_var(tmp_path, monkeypatch):
    target = tmp_path / "custom_data"
    monkeypatch.setenv("THESEUS_DATA_DIR", str(target))
    assert frozen_support.data_dir() == target
    assert target.is_dir()


def test_data_dir_platform_default_when_env_unset(monkeypatch):
    monkeypatch.delenv("THESEUS_DATA_DIR", raising=False)
    d = frozen_support.data_dir()
    assert d.is_dir()
    if sys.platform == "darwin":
        assert "Library/Application Support/Noosphere" in str(d)
    elif sys.platform == "win32":
        assert "Noosphere" in str(d)
    else:
        assert d.name == ".noosphere"


def test_alembic_dir_points_at_real_dir_in_dev():
    ad = frozen_support.alembic_dir()
    assert ad.is_dir()
    assert (ad / "env.py").exists()


def test_alembic_ini_points_at_real_file_in_dev():
    assert frozen_support.alembic_ini().is_file()


def test_frozen_mode_paths(monkeypatch, tmp_path):
    """With sys.frozen and sys._MEIPASS set, paths resolve inside the bundle."""
    fake_bundle = tmp_path / "bundle"
    fake_bundle.mkdir()
    (fake_bundle / "alembic").mkdir()
    (fake_bundle / "alembic.ini").write_text("[alembic]\n")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(fake_bundle), raising=False)

    assert frozen_support.is_frozen() is True
    assert frozen_support.bundle_dir() == Path(str(fake_bundle))
    assert frozen_support.alembic_dir() == Path(str(fake_bundle)) / "alembic"
    assert frozen_support.alembic_ini() == Path(str(fake_bundle)) / "alembic.ini"
