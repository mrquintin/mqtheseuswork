"""Package a registered method into a self-contained, Docker-reproducible artifact."""
from __future__ import annotations

import importlib
import inspect
import json
import logging
import shutil
from pathlib import Path
from typing import NewType, Optional

from noosphere.ledger.keys import KeyRing
from noosphere.methods._registry import REGISTRY
from noosphere.models import (
    BatteryRunResult,
    CounterfactualEvalRun,
    MethodRef,
)
from noosphere.transfer.adapter_template import render_adapter
from noosphere.transfer.docker_build import docker_build, write_dockerfile
from noosphere.transfer.signing import write_signed_checksums

logger = logging.getLogger(__name__)

PackagePath = NewType("PackagePath", Path)

_APACHE2_HEADER = """\
Apache License, Version 2.0

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

_README_TEMPLATE = """\
# {name} v{version}

## How to run

```bash
docker build -t {name} .
docker run --rm {name} input.json
```

Or without Docker:

```bash
cd implementation && pip install -r requirements.txt
python ../adapter.py input.json
```

## Input schema

```json
{input_schema}
```

## Output schema

```json
{output_schema}
```

## Known limitations

{limitations}
"""

_EVAL_CARD_STUB = """\
# Evaluation Card — {name} v{version}

No evaluation runs recorded yet.
"""

_EVAL_CARD_TEMPLATE = """\
# Evaluation Card — {name} v{version}

## Counterfactual Evaluations

{cf_section}

## Battery Run Results

{battery_section}
"""


def _format_cf_runs(runs: list[CounterfactualEvalRun]) -> str:
    if not runs:
        return "None recorded."
    lines: list[str] = []
    for r in runs:
        lines.append(f"- **{r.run_id}** (cut={r.cut_id}): "
                      f"brier={r.metrics.brier:.4f}, ece={r.metrics.ece:.4f}, "
                      f"coverage={r.metrics.coverage:.2f}")
    return "\n".join(lines)


def _format_battery_runs(runs: list[BatteryRunResult]) -> str:
    if not runs:
        return "None recorded."
    lines: list[str] = []
    for r in runs:
        lines.append(f"- **{r.run_id}** ({r.corpus_name}): "
                      f"brier={r.metrics.brier:.4f}, ece={r.metrics.ece:.4f}, "
                      f"failures={len(r.failures)}")
    return "\n".join(lines)


def _resolve_module_source(module_name: str) -> Path:
    """Return the filesystem directory for a dotted module path."""
    mod = importlib.import_module(module_name)
    mod_file = inspect.getfile(mod)
    return Path(mod_file).parent


def _find_rationale(method_name: str) -> Optional[str]:
    """Look for ``methods/<name>.RATIONALE.md`` relative to the methods package."""
    from noosphere.methods import __file__ as methods_init

    methods_dir = Path(methods_init).parent
    candidate = methods_dir / f"{method_name}.RATIONALE.md"
    if candidate.exists():
        return candidate.read_text()
    return None


def _collect_requirements(impl_dir: Path) -> list[str]:
    """Collect requirements.txt entries from the implementation dir (if any)."""
    req_path = impl_dir / "requirements.txt"
    if req_path.exists():
        return [l.strip() for l in req_path.read_text().splitlines() if l.strip() and not l.startswith("#")]
    return []


def package(
    method_ref: MethodRef,
    out_dir: Path,
    keyring: KeyRing,
    *,
    cf_runs: Optional[list[CounterfactualEvalRun]] = None,
    battery_runs: Optional[list[BatteryRunResult]] = None,
    python_version: str = "3.11",
    run_docker: bool = False,
    limitations: str = "See evaluation card for known domain limitations.",
) -> PackagePath:
    """Package a registered method into *out_dir*.

    Produces:
        method.json, rationale.md, implementation/, adapter.py,
        Dockerfile, CHECKSUMS, CHECKSUMS.sig, README.md, EVAL_CARD.md, LICENSE
    """
    spec, fn = REGISTRY.get(method_ref.name, version=method_ref.version)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # method.json
    (out_dir / "method.json").write_text(
        json.dumps(spec.model_dump(mode="json"), indent=2, default=str)
    )

    # rationale.md
    rationale_text = _find_rationale(spec.name) or spec.rationale
    (out_dir / "rationale.md").write_text(rationale_text)

    # implementation/
    impl_out = out_dir / "implementation"
    impl_out.mkdir(exist_ok=True)

    module_parts = spec.implementation.module.split(".")
    if len(module_parts) >= 2:
        source_module = ".".join(module_parts[:-1])
    else:
        source_module = spec.implementation.module

    try:
        source_dir = _resolve_module_source(source_module)
        for src_file in source_dir.iterdir():
            if src_file.is_file() and not src_file.name.startswith("__pycache__"):
                shutil.copy2(src_file, impl_out / src_file.name)
    except (ImportError, TypeError):
        logger.warning("Could not resolve source for %s", source_module)

    reqs = _collect_requirements(impl_out)
    if not reqs:
        reqs = ["pydantic>=2.0"]
    (impl_out / "requirements.txt").write_text("\n".join(reqs) + "\n")

    # adapter.py
    entry_module = module_parts[-1] if module_parts else spec.implementation.module
    # fn_name from __qualname__ may contain '<locals>.' — extract the bare name
    raw_fn = spec.implementation.fn_name
    bare_fn = raw_fn.rsplit(".", 1)[-1] if "." in raw_fn else raw_fn
    adapter_code = render_adapter(
        method_name=spec.name,
        method_version=spec.version,
        entry_module=entry_module,
        entry_fn=bare_fn,
    )
    (out_dir / "adapter.py").write_text(adapter_code)

    # Dockerfile
    write_dockerfile(out_dir, python_version=python_version)

    # README.md
    readme = _README_TEMPLATE.format(
        name=spec.name,
        version=spec.version,
        input_schema=json.dumps(spec.input_schema, indent=2),
        output_schema=json.dumps(spec.output_schema, indent=2),
        limitations=limitations,
    )
    (out_dir / "README.md").write_text(readme)

    # EVAL_CARD.md
    if cf_runs or battery_runs:
        eval_card = _EVAL_CARD_TEMPLATE.format(
            name=spec.name,
            version=spec.version,
            cf_section=_format_cf_runs(cf_runs or []),
            battery_section=_format_battery_runs(battery_runs or []),
        )
    else:
        eval_card = _EVAL_CARD_STUB.format(name=spec.name, version=spec.version)
    (out_dir / "EVAL_CARD.md").write_text(eval_card)

    # LICENSE
    (out_dir / "LICENSE").write_text(_APACHE2_HEADER)

    # CHECKSUMS + CHECKSUMS.sig (must be last)
    write_signed_checksums(out_dir, keyring)

    # Optional Docker build
    if run_docker:
        tag = f"{spec.name}:{spec.version}"
        digest = docker_build(out_dir, tag=tag)
        if digest:
            logger.info("Docker image built: %s (%s)", tag, digest)

    return PackagePath(out_dir)
