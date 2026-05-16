"""Fixture module ``a``. Cycles with ``b``."""

from tests.static.fixtures.synthetic_cycle import b  # noqa: F401 — intentional cycle

A = "a"
