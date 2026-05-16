"""Broken fixtures for the smoke-harness self-tests.

Each subdirectory plants a deliberate regression. The tests in
``tests/static/test_smoke_harness_itself.py`` point a smoke section
at the fixture and assert the failure is reported in the harness's
JSON output. If a fixture stops triggering its assertion, the smoke
harness is silently no longer catching the regression class — that
is itself a regression these self-tests exist to surface.
"""
