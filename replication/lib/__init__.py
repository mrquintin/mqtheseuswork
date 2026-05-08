"""Replication harness library: envelope + verification.

Used by ``replication/Makefile`` targets to wrap the firm's existing
benchmark, cross-model, and ablation runners in a reproducibility
record. Nothing here is imported by production code; the harness is
strictly downstream evidence.

This package does not eagerly re-export submodule contents — running
``python -m replication.lib.verify`` would otherwise warn about the
module already being imported. Import the symbols directly from
``replication.lib.envelope`` / ``replication.lib.verify``.
"""
