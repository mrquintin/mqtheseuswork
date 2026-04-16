"""Compile a versioned, signed MethodDoc bundle from registry + store data."""
from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from noosphere.ledger.keys import KeyRing
from noosphere.methods._registry import REGISTRY
from noosphere.models import (
    BatteryRunResult,
    CalibrationMetrics,
    CounterfactualEvalRun,
    Method,
    MethodDoc,
    MethodInvocation,
    MethodRef,
    TransferStudy,
)
from noosphere.transfer.signing import write_signed_checksums

logger = logging.getLogger(__name__)

TEMPLATE_VERSION = "1.0.0"
_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _json_pretty(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str, ensure_ascii=False)


def _build_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )


def _read_rationale(method_name: str) -> str:
    methods_dir = Path(__file__).parent.parent / "methods"
    rationale_path = methods_dir / f"{method_name}.RATIONALE.md"
    if rationale_path.exists():
        return rationale_path.read_text()
    return "(No rationale file found.)"


def _git_show_source(git_sha: str, module_path: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "show", f"{git_sha}:{module_path}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout
    except Exception:
        pass
    return None


def _flatten_invocation_stats(
    invocations: list[MethodInvocation],
) -> dict[str, Any]:
    total = len(invocations)
    succeeded = sum(1 for i in invocations if i.succeeded)
    failed = total - succeeded
    failure_rate = (failed / total * 100) if total else 0.0

    error_breakdown: dict[str, int] = {}
    for inv in invocations:
        if not inv.succeeded and inv.error_kind:
            error_breakdown[inv.error_kind] = error_breakdown.get(inv.error_kind, 0) + 1

    first_inv = None
    last_inv = None
    if invocations:
        sorted_invs = sorted(invocations, key=lambda i: i.started_at)
        first_inv = str(sorted_invs[0].started_at)
        last_inv = str(sorted_invs[-1].started_at)

    return {
        "total_invocations": total,
        "successful_invocations": succeeded,
        "failed_invocations": failed,
        "failure_rate_pct": failure_rate,
        "error_breakdown": error_breakdown,
        "first_invocation": first_inv,
        "last_invocation": last_inv,
    }


def _flatten_eval_run(run: CounterfactualEvalRun) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "cut_id": run.cut_id,
        "brier": run.metrics.brier,
        "log_loss": run.metrics.log_loss,
        "ece": run.metrics.ece,
        "resolution": run.metrics.resolution,
        "coverage": run.metrics.coverage,
        "created_at": str(run.created_at),
    }


def _flatten_battery_run(run: BatteryRunResult) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "corpus_name": run.corpus_name,
        "brier": run.metrics.brier,
        "log_loss": run.metrics.log_loss,
        "ece": run.metrics.ece,
        "failure_count": len(run.failures),
    }


def _flatten_transfer_study(study: TransferStudy) -> dict[str, Any]:
    return {
        "study_id": study.study_id,
        "source_domain": str(study.source_domain),
        "target_domain": str(study.target_domain),
        "dataset_path": study.dataset.path,
        "dataset_hash": study.dataset.content_hash,
        "baseline_brier": study.baseline_on_source.brier,
        "baseline_log_loss": study.baseline_on_source.log_loss,
        "baseline_ece": study.baseline_on_source.ece,
        "baseline_resolution": study.baseline_on_source.resolution,
        "baseline_coverage": study.baseline_on_source.coverage,
        "result_brier": study.result_on_target.brier,
        "result_log_loss": study.result_on_target.log_loss,
        "result_ece": study.result_on_target.ece,
        "result_resolution": study.result_on_target.resolution,
        "result_coverage": study.result_on_target.coverage,
        "delta_brier": study.delta.get("brier", 0.0),
        "delta_log_loss": study.delta.get("log_loss", 0.0),
        "delta_ece": study.delta.get("ece", 0.0),
        "delta_resolution": study.delta.get("resolution", 0.0),
        "delta_coverage": study.delta.get("coverage", 0.0),
        "qualitative_notes": study.qualitative_notes,
    }


def compile_method_doc(
    method_ref: MethodRef,
    out_dir: Path,
    keyring: KeyRing,
    *,
    eval_runs: Optional[list[CounterfactualEvalRun]] = None,
    battery_runs: Optional[list[BatteryRunResult]] = None,
    transfer_studies: Optional[list[TransferStudy]] = None,
    invocations: Optional[list[MethodInvocation]] = None,
    examples: Optional[list[dict[str, Any]]] = None,
    reviewed_by: Optional[str] = None,
    require_review: bool = False,
) -> MethodDoc:
    """Compile a full MethodDoc bundle.

    Reads method spec from REGISTRY, rationale from the methods directory,
    and accepts pre-fetched store data as parameters for testability.
    """
    if require_review and not reviewed_by:
        raise ValueError(
            "Examples require review: set reviewed_by or remove --require-review"
        )

    spec, _fn = REGISTRY.get(method_ref.name, method_ref.version)

    env = _build_jinja_env()
    version_dir = out_dir / spec.name / spec.version
    version_dir.mkdir(parents=True, exist_ok=True)

    # --- spec.md ---
    spec_tmpl = env.get_template("spec.md.j2")
    spec_md = spec_tmpl.render(
        name=spec.name,
        version=spec.version,
        method_type=spec.method_type.value,
        owner=spec.owner,
        status=spec.status,
        created_at=str(spec.created_at),
        description=spec.description,
        input_schema=_json_pretty(spec.input_schema),
        output_schema=_json_pretty(spec.output_schema),
        preconditions=spec.preconditions,
        postconditions=spec.postconditions,
        dependencies=spec.dependencies,
        impl_module=spec.implementation.module,
        impl_fn_name=spec.implementation.fn_name,
        impl_git_sha=spec.implementation.git_sha,
        impl_image_digest=spec.implementation.image_digest,
        nondeterministic=spec.nondeterministic,
    )
    (version_dir / "spec.md").write_text(spec_md)

    # --- rationale.md ---
    rationale_body = _read_rationale(spec.name)
    rationale_tmpl = env.get_template("rationale.md.j2")
    rationale_md = rationale_tmpl.render(
        name=spec.name,
        version=spec.version,
        rationale_body=rationale_body,
    )
    (version_dir / "rationale.md").write_text(rationale_md)

    # --- examples.md ---
    examples_tmpl = env.get_template("examples.md.j2")
    ex_data = []
    for ex in (examples or []):
        ex_data.append({
            "title": ex.get("title", "Untitled"),
            "input_json": _json_pretty(ex.get("input", {})),
            "output_json": _json_pretty(ex.get("output", {})),
            "narrative": ex.get("narrative", ""),
        })
    inv_summaries: list[str] = []
    for inv in (invocations or [])[:10]:
        status = "success" if inv.succeeded else f"failed ({inv.error_kind})"
        inv_summaries.append(f"Invocation {inv.id[:8]}: {status}")

    examples_md = examples_tmpl.render(
        name=spec.name,
        version=spec.version,
        reviewed_by=reviewed_by or "",
        examples=ex_data,
        invocation_summaries=inv_summaries,
    )
    (version_dir / "examples.md").write_text(examples_md)

    # --- calibration.md ---
    cal_tmpl = env.get_template("calibration.md.j2")
    cal_md = cal_tmpl.render(
        name=spec.name,
        version=spec.version,
        eval_runs=[_flatten_eval_run(r) for r in (eval_runs or [])],
        battery_runs=[_flatten_battery_run(r) for r in (battery_runs or [])],
    )
    (version_dir / "calibration.md").write_text(cal_md)

    # --- transfer.md ---
    transfer_tmpl = env.get_template("transfer.md.j2")
    transfer_md = transfer_tmpl.render(
        name=spec.name,
        version=spec.version,
        studies=[_flatten_transfer_study(s) for s in (transfer_studies or [])],
    )
    (version_dir / "transfer.md").write_text(transfer_md)

    # --- operations.md ---
    ops_tmpl = env.get_template("operations.md.j2")
    ops_stats = _flatten_invocation_stats(invocations or [])
    ops_md = ops_tmpl.render(name=spec.name, version=spec.version, **ops_stats)
    (version_dir / "operations.md").write_text(ops_md)

    # --- index.md ---
    index_tmpl = env.get_template("index.md.j2")
    index_md = index_tmpl.render(
        name=spec.name,
        version=spec.version,
        template_version=TEMPLATE_VERSION,
        signed_by=keyring.active_key_id,
        doi=None,
    )
    (version_dir / "index.md").write_text(index_md)

    # --- sign ---
    write_signed_checksums(version_dir, keyring)

    return MethodDoc(
        method_ref=method_ref,
        spec_md_path=str(version_dir / "spec.md"),
        rationale_md_path=str(version_dir / "rationale.md"),
        examples_md_path=str(version_dir / "examples.md"),
        calibration_md_path=str(version_dir / "calibration.md"),
        transfer_md_path=str(version_dir / "transfer.md"),
        operations_md_path=str(version_dir / "operations.md"),
        template_version=TEMPLATE_VERSION,
        signed_by=keyring.active_key_id,
    )
