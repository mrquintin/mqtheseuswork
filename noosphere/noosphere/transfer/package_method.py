"""Package a registered method into a self-contained, Docker-reproducible artifact."""

from __future__ import annotations

import importlib
import inspect
import json
import logging
import shutil
import ast
import textwrap
from pathlib import Path
from typing import Any, NewType, Optional

from pydantic import BaseModel

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
        lines.append(
            f"- **{r.run_id}** (cut={r.cut_id}): "
            f"brier={r.metrics.brier:.4f}, ece={r.metrics.ece:.4f}, "
            f"coverage={r.metrics.coverage:.2f}"
        )
    return "\n".join(lines)


def _format_battery_runs(runs: list[BatteryRunResult]) -> str:
    if not runs:
        return "None recorded."
    lines: list[str] = []
    for r in runs:
        lines.append(
            f"- **{r.run_id}** ({r.corpus_name}): "
            f"brier={r.metrics.brier:.4f}, ece={r.metrics.ece:.4f}, "
            f"failures={len(r.failures)}"
        )
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
        return [
            l.strip()
            for l in req_path.read_text().splitlines()
            if l.strip() and not l.startswith("#")
        ]
    return []


def _is_local_or_test_function(fn: Any, module_path: Path) -> bool:
    """Return True for functions that cannot be packaged by copying their module.

    Test-local methods are often nested in a pytest module whose top-level imports
    include pytest/noosphere. Copying that file makes the exported adapter depend
    on the source repository, defeating the self-contained package contract.
    """

    original = getattr(fn, "__wrapped__", fn)
    return "<locals>" in getattr(original, "__qualname__", "") or "/tests/" in (
        "/" + str(module_path).replace("\\", "/")
    )


def _model_class_source(name: str, model_cls: type[BaseModel]) -> str:
    lines = [f"class {name}(BaseModel):"]
    fields = getattr(model_cls, "model_fields", {})
    if not fields:
        lines.append("    pass")
        return "\n".join(lines)
    for field_name in fields:
        lines.append(f"    {field_name}: Any = None")
    return "\n".join(lines)


def _write_local_function_shim(
    *,
    fn: Any,
    impl_out: Path,
    entry_module: str,
    entry_fn: str,
) -> None:
    """Write a minimal implementation module for a local/test-registered method."""

    original = getattr(fn, "__wrapped__", fn)
    source = textwrap.dedent(inspect.getsource(original))
    tree = ast.parse(source)
    function_node = next(
        (node for node in tree.body if isinstance(node, ast.FunctionDef)),
        None,
    )
    if function_node is None:
        raise ValueError(f"Could not extract source for packaged method {entry_fn}")
    function_node.decorator_list = []
    impl_fn_name = f"_{entry_fn}_impl"
    function_node.name = impl_fn_name
    impl_source = ast.unparse(function_node)

    model_sources: list[str] = []
    globals_map = getattr(original, "__globals__", {})
    for name, value in sorted(globals_map.items()):
        if name not in source:
            continue
        if inspect.isclass(value) and issubclass(value, BaseModel):
            model_sources.append(_model_class_source(name, value))

    module_source = "\n\n".join(
        [
            "from __future__ import annotations",
            "from types import SimpleNamespace",
            "from typing import Any",
            "from pydantic import BaseModel",
            *model_sources,
            impl_source,
            (
                f"def {entry_fn}(input_data: Any) -> Any:\n"
                "    if isinstance(input_data, dict):\n"
                "        input_data = SimpleNamespace(**input_data)\n"
                f"    return {impl_fn_name}(input_data)\n"
            ),
        ]
    )
    (impl_out / f"{entry_module}.py").write_text(module_source + "\n")


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
        module_file = Path(inspect.getfile(getattr(fn, "__wrapped__", fn)))
        raw_fn = spec.implementation.fn_name
        bare_fn = raw_fn.rsplit(".", 1)[-1] if "." in raw_fn else raw_fn
        entry_module = module_parts[-1] if module_parts else spec.implementation.module
        if _is_local_or_test_function(fn, module_file):
            _write_local_function_shim(
                fn=fn,
                impl_out=impl_out,
                entry_module=entry_module,
                entry_fn=bare_fn,
            )
        else:
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
    # fn_name from __qualname__ may contain '<locals>.' — extract the bare name
    raw_fn = spec.implementation.fn_name
    bare_fn = raw_fn.rsplit(".", 1)[-1] if "." in raw_fn else raw_fn
    entry_module = module_parts[-1] if module_parts else spec.implementation.module
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
