# Noosphere Module Map (Round 19)

Round 17 added thirty-plus modules and subpackages to ``noosphere/`` —
evaluation, distillation, observability, literature, benchmarks, peer-review
providers, methods/composition, temporal, decay/retention, social, and more.
The result was a flat top level where related modules were no longer obvious
neighbours and where layering rules were enforced only by convention.

Round 19 introduces a hierarchical surface without physically relocating
files. Each layer below is a Python package (a directory with an
``__init__.py``) that re-exports the modules belonging to that layer. The
concrete implementations stay where they are; the new packages are stable
import paths and the substrate for the ``import-linter`` contract that runs
in CI.

A future prompt will physically move modules into their new homes and leave
``DeprecationWarning`` shims at the legacy paths. This document is the
target. The shims described in section "Shim policy" are not yet installed.

## Top-level shape

    noosphere/
    ├── core/            ← foundational primitives
    ├── methods/         ← method registry, composition, every method.py
    ├── inquiry/         ← coherence, evaluation, peer review, red-team, mitigations
    ├── temporal/        ← snapshots, lineage, replay, conviction estimation
    ├── literature/      ← external sources, citations, standing, retraction polls
    ├── forecasts/       ← forecast workflows (Polymarket / Kalshi / metaculus)
    ├── currents/        ← Currents pipeline
    ├── dialectic_bridge ← exports, ingestion contracts toward Codex
    ├── io/              ← codex_bridge, storage_client, ingester, ingest_artifacts
    ├── cli/             ← Typer + click commands, plugin registry
    ├── benchmarks/      ← benchmark harness + corpora
    └── docgen/          ← documentation generation

## Layer contracts

| Layer            | May import                                  | Must not import                                   |
|------------------|---------------------------------------------|---------------------------------------------------|
| ``core``         | stdlib, third-party only                    | anything from ``noosphere.*`` other than itself   |
| ``methods``      | ``core``                                    | ``inquiry``, ``cli``, ``io`` (uses core models)   |
| ``inquiry``      | ``core``, ``methods``                       | ``cli``, ``io``, ``literature``                   |
| ``temporal``     | ``core``, ``methods``                       | ``cli``, ``io``                                   |
| ``literature``   | ``core``, ``io``                            | ``cli``                                           |
| ``forecasts``    | ``core``, ``methods``, ``inquiry``          | ``cli``                                           |
| ``currents``     | ``core``, ``methods``, ``inquiry``, ``io``  | ``cli``                                           |
| ``io``           | ``core``                                    | ``inquiry``, ``methods``, ``cli``                 |
| ``cli``          | *any layer*                                 | —                                                 |
| ``benchmarks``   | ``core``, ``methods``, ``inquiry``          | ``cli``                                           |
| ``docgen``       | ``core``, ``methods``                       | ``cli``                                           |

Contracts above mirror the ``[importlinter:contract:*]`` blocks in
``noosphere/.import-linter`` and are checked by
``tests/test_module_hierarchy.py`` plus the CI step
``lint-imports --config noosphere/.import-linter``.

## Per-layer module roster

### ``noosphere.core`` (new facade — implementations remain at legacy paths)

* ``noosphere.models`` — every domain dataclass / SQLModel.
* ``noosphere.store`` — SQLite persistence (raw SQL confined here).
* ``noosphere.ontology`` — the ``OntologyGraph`` aggregate root.
* ``noosphere.orchestrator`` — pipeline driver (``NoosphereOrchestrator``).
* ``noosphere.observability`` — structured logging, spans, metrics.
* ``noosphere.ledger`` — append-only signed audit log + Merkle chaining.
* ``noosphere.ids`` — deterministic ID derivation helpers.
* ``noosphere.config`` — settings via pydantic.

### ``noosphere.methods``

* ``noosphere.methods.*`` — every method package: registry, composition,
  decorator, ``method.py`` + ``RATIONALE.md`` + ``FAILURES.yaml``.

### ``noosphere.inquiry`` (new facade)

* ``noosphere.coherence`` — six-layer engine, NLI, calibration, scheduler.
* ``noosphere.evaluation`` — slicer, outcomes, metrics, counterfactual.
* ``noosphere.peer_review`` — reviewer, swarm, rebuttal, tournament, providers.
* ``noosphere.redteam`` — synthetic attack suite.
* ``noosphere.mitigations`` — shipped defensive checks.

### ``noosphere.temporal``

* ``noosphere.temporal`` — ``TemporalTracker``, ``EvolutionAnalyzer``,
  ``ConvictionEstimator``, stance-embedding series & drift detection.
* ``noosphere.temporal.lineage`` — per-conclusion lineage assembler + diff.
* ``noosphere.temporal_replay`` — replay infrastructure (legacy path; moves under
  ``temporal/`` in a follow-up).

### ``noosphere.literature``

* ``noosphere.literature`` — connectors, ingestion, chunking, claims.
* ``noosphere.literature.standing_polls``, ``citation_chain``, ``response_triage``,
  ``source_credibility``, ``source_priors``, ``standing``.

### ``noosphere.forecasts``

* ``noosphere.forecasts.*`` — adapters (polymarket, kalshi, claim_review,
  metaculus, GJP, replication), pipeline, scheduler.

### ``noosphere.currents``

* ``noosphere.currents.*`` — Currents inversion pipeline + dialectic glue.

### ``noosphere.io`` (new facade)

* ``noosphere.codex_bridge`` — Codex Postgres ingest worker.
* ``noosphere.storage_client`` — local disk / MinIO / S3 / R2.
* ``noosphere.ingester`` — transcript ingestion pipeline.
* ``noosphere.ingest_artifacts`` — markdown / plain-text artifact ingestion.

### ``noosphere.cli`` (new facade)

* ``noosphere.cli`` — Click root group, ``get_orchestrator`` helper, every
  command (legacy ``cli.py`` source, shadowed by this package and re-exported
  in-place).
* ``noosphere.typer_cli`` — primary Typer app, ``python -m noosphere`` entry.
* ``noosphere.cli_commands.*`` — plugin command modules attached at startup.

### ``noosphere.benchmarks``

* ``noosphere.benchmarks.*`` — corpora, runner, golden-set fixtures.

### ``noosphere.docgen``

* ``noosphere.docgen.*`` — README / manifest / methodology renderers.

## Shim policy

This prompt is non-breaking: no module file is moved or deleted. The new
packages above re-export from the legacy paths. When a future prompt moves a
module physically (e.g. ``noosphere/store.py`` → ``noosphere/core/store.py``),
that prompt must:

1. Place the implementation at the new path.
2. Leave a one-line shim at the old path:
   ```python
   import warnings
   warnings.warn(
       "noosphere.store moved to noosphere.core.store; update your import",
       DeprecationWarning,
       stacklevel=2,
   )
   from noosphere.core.store import *  # noqa: F401,F403
   ```
3. Update all in-package imports to use the new path so the shim has only
   external callers.
4. Schedule shim removal for a follow-up prompt at least 30 days later.

## CI enforcement

* ``noosphere/.import-linter`` — declarative contract, one ``[importlinter:contract:layer]`` per layer above.
* ``noosphere/tests/test_module_hierarchy.py`` — runs the linter against the
  live package and walks every public module to assert it is reachable from
  exactly one facade.
* Repository CI step (``lint-imports --config noosphere/.import-linter``)
  fails the build on any contract violation.

## Open questions for a future prompt

* Whether ``temporal_replay`` should physically move under ``temporal/`` or
  under ``inquiry/`` (it is half-replay, half-evaluation).
* Whether ``social/`` and ``decay/retention*`` modules belong under
  ``inquiry`` or stay top-level (they have light cross-cutting use today).
* Final home for ``cascade``, ``cases``, ``conclusions``, ``decisions``,
  ``principles``, ``voices`` — these are domain aggregates that may warrant
  a ``noosphere.domain/`` layer rather than living under ``core/``.
