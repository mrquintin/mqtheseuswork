# Known Import Cycles

Source of truth for **every** import cycle the cyclic-import detector
(`scripts/detect_import_cycles.py`) is allowed to find in the Python
graph. The corresponding tests
(`noosphere/tests/test_no_import_cycles.py`) and the import-linter
contract (`noosphere/.import-linter`) both read this file: an unlisted
cycle is a test failure, and a listed cycle past its expiry date is also
a test failure.

## How a cycle ends up in this document

A cycle gets a row here only when **both** are true:

1. Breaking the cycle structurally would require an outsized refactor —
   it touches a registry pattern, a plug-in surface, or a packaging
   boundary that cannot be moved in a single prompt without breaking
   external callers.
2. The runtime impact is bounded: import-time side effects are idempotent
   and Python's partially-initialized-module behaviour is observed to
   produce the same module objects regardless of which side of the cycle
   imports first.

Every entry has an **expiry date**. When the expiry passes, the cycle
becomes a hard test failure — the design intent is that no entry should
live here forever; either it gets fixed and removed, or its expiry gets
re-justified in a follow-up prompt with a written reason.

## Entry format

```
### <slug>
- Modules: <comma-separated, sorted>
- Expires: YYYY-MM-DD
- Why hard to break: <one paragraph>
- Mitigation in place: <how runtime risk is bounded today>
- Planned resolution: <interface module, registry split, or lazy import>
```

The `Modules:` line must list every module in the strongly-connected
component in sorted order. The test parses each `### slug` block and
matches the detected SCC's sorted module tuple against the `Modules:`
line literally.

---

### peer-review-reviewer-registry

- Modules:
  noosphere.peer_review,
  noosphere.peer_review.blindspot,
  noosphere.peer_review.geometric_blindspot,
  noosphere.peer_review.inverse,
  noosphere.peer_review.reviewers,
  noosphere.peer_review.reviewers.adv_literature,
  noosphere.peer_review.reviewers.evidential,
  noosphere.peer_review.reviewers.humility,
  noosphere.peer_review.reviewers.methodological,
  noosphere.peer_review.reviewers.replication,
  noosphere.peer_review.reviewers.rhetorical,
  noosphere.peer_review.reviewers.statistical,
  noosphere.peer_review.swarm
- Expires: 2026-09-30
- Why hard to break: The `reviewers/__init__.py` module is the registry
  *and* the import-side-effect entry point that registers every
  concrete reviewer. Each concrete reviewer (`methodological`,
  `evidential`, `statistical`, ..., plus the cross-cutting `blindspot`,
  `geometric_blindspot`, and `inverse`) imports the registry to call
  `_registry.register(cls)`. The package `__init__` re-exports
  `SwarmOrchestrator`, which depends on `all_reviewers()` from the same
  registry. Breaking this cleanly requires extracting the registry
  state into a dedicated leaf module (`noosphere.peer_review._registry`)
  and rewriting every concrete reviewer's import. That is in scope for
  a follow-up prompt; doing it here would balloon the diff well past
  the prompt's stated SCOPE.
- Mitigation in place: All edges in the cycle are pure module-load
  side effects (decorator-driven registration). Python's
  partially-initialized-module semantics are stable for this pattern
  because no top-level code on either side reads attributes that the
  other side has not yet populated. The cycle is *detected* at import
  time and held to a known shape by this allowlist, so a new module
  joining the cycle is a test failure.
- Planned resolution: Introduce
  `noosphere.peer_review._registry` as the leaf registry. Move
  `_REVIEWERS`, `register`, and `all_reviewers` out of
  `reviewers/__init__.py`; have every concrete reviewer import from
  the leaf; have `reviewers/__init__.py` re-export for the public API
  only. Once that lands, this entry is deleted.
