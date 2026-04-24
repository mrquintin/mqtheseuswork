"""Tests for dialectic.resources path resolution."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from dialectic import resources


DIALECTIC_ROOT = Path(__file__).resolve().parent.parent


def test_is_frozen_false_under_normal_python():
    assert resources.is_frozen() is False


def test_base_path_is_project_root_in_dev():
    assert resources.base_path() == DIALECTIC_ROOT


def test_asset_path_points_to_assets_dir():
    p = resources.asset_path("icon.png")
    assert p == DIALECTIC_ROOT / "assets" / "icon.png"
    # Placeholder created in prompt 01 setup
    assert p.exists(), f"expected placeholder at {p}"


def test_data_dir_is_writable_directory():
    d = resources.data_dir()
    assert d.exists()
    assert d.is_dir()
    probe = d / ".dialectic_write_probe"
    try:
        probe.write_text("ok")
        assert probe.read_text() == "ok"
    finally:
        if probe.exists():
            probe.unlink()


def test_data_dir_platform_location():
    d = resources.data_dir()
    if sys.platform == "darwin":
        assert d == Path.home() / "Library" / "Application Support" / "Dialectic"
    elif sys.platform == "win32":
        expected_parent = Path(os.environ.get("APPDATA", str(Path.home())))
        assert d == expected_parent / "Dialectic"
    else:
        assert d == Path.home() / ".dialectic"


def test_frozen_mode_uses_meipass(monkeypatch, tmp_path):
    fake_meipass = tmp_path / "meipass"
    fake_meipass.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(fake_meipass), raising=False)

    assert resources.is_frozen() is True
    assert resources.base_path() == fake_meipass
    assert resources.asset_path("icon.png") == fake_meipass / "assets" / "icon.png"


def test_not_frozen_when_meipass_missing(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    # Remove _MEIPASS if a prior test left it
    if hasattr(sys, "_MEIPASS"):
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    assert resources.is_frozen() is False
