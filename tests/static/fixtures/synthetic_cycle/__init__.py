"""Synthetic two-module cycle (a -> b -> a).

Lives under ``tests/static/fixtures/`` so the production import path
never reaches it. The cycle is asserted in
``tests/static/test_no_import_cycles.py::test_synthetic_cycle_is_caught``
to prove the AST walker (and, when installed, import-linter) detects
fresh cycles.

The two modules deliberately reach each other at module top level —
that's the *only* place a cyclic import becomes a runtime ImportError,
which is exactly the failure mode the gate guards against.
"""
