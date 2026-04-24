"""Run a MIP workflow via Docker containers."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from noosphere.interop.builder import verify_checksums, verify_manifest
from noosphere.interop.workflow import parse, validate
from noosphere.ledger.keys import KeyRing


def run_mip(
    mip_path: Path,
    workflow_name: str,
    input_data: Any,
    out_dir: Path,
    keyring: KeyRing,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((mip_path / "manifest.json").read_text())

    if not verify_manifest(mip_path, keyring):
        raise RuntimeError("Manifest signature verification failed")

    checksum_errors = verify_checksums(mip_path)
    if checksum_errors:
        raise RuntimeError(f"Checksum verification failed: {checksum_errors}")

    workflow_path = mip_path / "workflows" / f"{workflow_name}.yaml"
    if not workflow_path.exists():
        raise FileNotFoundError(f"Workflow not found: {workflow_path}")

    workflow_yaml = workflow_path.read_text()
    available_methods = [m["name"] for m in manifest["methods"]]
    validation_errors = validate(workflow_yaml, available_methods)
    if validation_errors:
        raise ValueError(f"Workflow validation failed: {validation_errors}")

    workflow = parse(workflow_yaml)
    steps = workflow["steps"]
    output_step_id = workflow["output"]

    run_id = hashlib.sha256(
        f"{mip_path.name}-{workflow_name}-{datetime.now(timezone.utc).isoformat()}".encode()
    ).hexdigest()[:16]

    ledger_entries: list[dict] = []
    step_outputs: dict[str, Any] = {}
    step_reports: list[dict] = []

    for step in steps:
        step_id = step["id"]
        method_name = step["method"]

        if "when" in step:
            when = step["when"]
            field_val = step_outputs.get(when["field"], input_data.get(when["field"]) if isinstance(input_data, dict) else None)
            if field_val != when["equals"]:
                step_reports.append({
                    "step_id": step_id,
                    "method": method_name,
                    "status": "skipped",
                    "reason": f"when predicate not met: {when['field']}={field_val!r} != {when['equals']!r}",
                })
                continue

        step_input = _resolve_input(step["input"], step_outputs, input_data)
        step_input_path = out_dir / f"{step_id}_input.json"
        step_output_path = out_dir / f"{step_id}_output.json"
        step_input_path.write_text(json.dumps(step_input, default=str))

        method_dir = mip_path / "methods" / method_name
        started_at = datetime.now(timezone.utc)

        try:
            _run_docker_step(method_dir, step_input_path, step_output_path)
            ended_at = datetime.now(timezone.utc)

            if step_output_path.exists():
                output = json.loads(step_output_path.read_text())
            else:
                output = None

            step_outputs[step_id] = output

            ledger_entry = {
                "entry_id": f"{run_id}-{step_id}",
                "run_id": run_id,
                "step_id": step_id,
                "method": method_name,
                "inputs_hash": hashlib.sha256(step_input_path.read_bytes()).hexdigest(),
                "outputs_hash": hashlib.sha256(
                    step_output_path.read_bytes() if step_output_path.exists() else b""
                ).hexdigest(),
                "started_at": started_at.isoformat(),
                "ended_at": ended_at.isoformat(),
                "succeeded": True,
            }
            ledger_entries.append(ledger_entry)
            step_reports.append({
                "step_id": step_id,
                "method": method_name,
                "status": "success",
                "duration_s": (ended_at - started_at).total_seconds(),
            })
        except subprocess.CalledProcessError as exc:
            ended_at = datetime.now(timezone.utc)
            step_reports.append({
                "step_id": step_id,
                "method": method_name,
                "status": "failed",
                "error": str(exc),
                "duration_s": (ended_at - started_at).total_seconds(),
            })
            ledger_entries.append({
                "entry_id": f"{run_id}-{step_id}",
                "run_id": run_id,
                "step_id": step_id,
                "method": method_name,
                "started_at": started_at.isoformat(),
                "ended_at": ended_at.isoformat(),
                "succeeded": False,
                "error": str(exc),
            })

    final_output = step_outputs.get(output_step_id)

    report = {
        "run_id": run_id,
        "mip_name": manifest["name"],
        "mip_version": manifest["version"],
        "workflow": workflow_name,
        "started_at": ledger_entries[0]["started_at"] if ledger_entries else None,
        "ended_at": ledger_entries[-1]["ended_at"] if ledger_entries else None,
        "steps": step_reports,
        "output": final_output,
        "ledger_entries": len(ledger_entries),
    }

    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2, default=str))

    ledger_path = out_dir / "ledger.json"
    ledger_path.write_text(json.dumps(ledger_entries, indent=2, default=str))

    return report


def _resolve_input(
    input_spec: Any,
    step_outputs: dict[str, Any],
    run_input: Any,
) -> Any:
    if isinstance(input_spec, str) and input_spec.startswith("$steps."):
        ref_id = input_spec.split(".", 1)[1]
        return step_outputs.get(ref_id, input_spec)
    if isinstance(input_spec, str) and input_spec == "$input":
        return run_input
    return input_spec


def _run_docker_step(
    method_dir: Path,
    input_path: Path,
    output_path: Path,
) -> None:
    image_tag = f"mip-{method_dir.name}:latest"

    subprocess.run(
        ["docker", "build", "-t", image_tag, str(method_dir)],
        check=True,
        capture_output=True,
    )

    subprocess.run(
        [
            "docker", "run", "--rm",
            "--network", "none",
            "-v", f"{input_path.resolve()}:/work/input.json:ro",
            "-v", f"{output_path.resolve().parent}:/work/output",
            image_tag,
            "python", "adapter.py",
            "--input", "/work/input.json",
            "--output", "/work/output/output.json",
        ],
        check=True,
        capture_output=True,
    )

    docker_output = output_path.resolve().parent / "output.json"
    if docker_output.exists() and docker_output != output_path:
        docker_output.rename(output_path)
