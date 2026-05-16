"""Bug-replay regression catalog.

Every bug we have actually hit during this collaboration gets a
regression test here. If it broke once, the test in this package is
what would have caught it. The catalog of human-readable summaries
lives at ``docs/security/BUG_CATALOG.md`` — the freshness test in
``test_catalog_freshness.py`` ensures the catalog and the test
functions stay in lock-step.
"""
