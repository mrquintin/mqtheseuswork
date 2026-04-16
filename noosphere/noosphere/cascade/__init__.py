"""Cascade: typed, cycle-free, append-only evidence-flow graph."""
from noosphere.cascade.graph import CascadeCycleError, CascadeGraph
from noosphere.cascade.traverse import CutReport, cut, downstream, explain
from noosphere.cascade.render import to_graphviz, to_mermaid
from noosphere.cascade.diagnostics import (
    DiagnosticsReport,
    critical_path,
    detect_cycles,
    edge_density,
    run_diagnostics,
    single_points_of_failure,
)
from noosphere.cascade.export import export_proof
from noosphere.cascade.hooks import (
    CascadeEdgeDeclarationError,
    check_declaration_parity,
)

from noosphere.methods._hooks import register_post_hook
from noosphere.cascade.hooks import _emit_edges

register_post_hook("cascade.emit_edges", _emit_edges)

__all__ = [
    "CascadeCycleError",
    "CascadeEdgeDeclarationError",
    "CascadeGraph",
    "CutReport",
    "DiagnosticsReport",
    "check_declaration_parity",
    "critical_path",
    "cut",
    "detect_cycles",
    "downstream",
    "edge_density",
    "explain",
    "export_proof",
    "run_diagnostics",
    "single_points_of_failure",
    "to_graphviz",
    "to_mermaid",
]
