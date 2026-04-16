"""Scaffold an adopter project from a MIP bundle."""

from __future__ import annotations

import json
from pathlib import Path


def scaffold_adoption(mip_path: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((mip_path / "manifest.json").read_text())
    mip_name = manifest["name"]
    mip_version = manifest["version"]
    methods = manifest.get("methods", [])

    _write_readme(out_dir, mip_name, mip_version, mip_path, methods)
    _write_adapter_stub(out_dir, methods)
    _write_example_workflow(out_dir, methods)
    _write_scoreboard(out_dir, mip_name)
    _write_run_script(out_dir, mip_path, methods)

    return out_dir


def _write_readme(
    out_dir: Path,
    name: str,
    version: str,
    mip_path: Path,
    methods: list[dict],
) -> None:
    method_list = "\n".join(f"- **{m['name']}** v{m['version']}" for m in methods)
    citation_path = mip_path / "CITATION.cff"
    citation_block = ""
    if citation_path.exists():
        citation_block = (
            "\n## Citation\n\n"
            "When publishing results obtained with this MIP, cite as follows:\n\n"
            "```\n" + citation_path.read_text() + "```\n"
        )

    readme = (
        f"# {name} v{version} — Adopter Project\n\n"
        "## Included Methods\n\n"
        f"{method_list}\n\n"
        "## Quick Start\n\n"
        "1. Install Docker.\n"
        "2. Edit `adapter.py` to wire your local data sources.\n"
        "3. Run `bash run.sh` to execute the example workflow.\n"
        "4. Review results in `output/report.json`.\n"
        f"{citation_block}\n"
        "## Scoreboard\n\n"
        "Local run results are tracked in `scoreboard.json`.\n"
    )
    (out_dir / "README.md").write_text(readme)


def _write_adapter_stub(out_dir: Path, methods: list[dict]) -> None:
    lines = [
        '"""Stub adapter — wire your local data sources here."""',
        "",
        "",
        "def load_input(method_name: str) -> dict:",
        '    """Return input data for the given method."""',
    ]
    for m in methods:
        lines.append(f'    if method_name == "{m["name"]}":')
        lines.append(f'        return {{"method": "{m["name"]}", "data": {{}}}}')
    lines.extend([
        '    raise ValueError(f"Unknown method: {method_name}")',
        "",
    ])
    (out_dir / "adapter.py").write_text("\n".join(lines) + "\n")


def _write_example_workflow(out_dir: Path, methods: list[dict]) -> None:
    if not methods:
        return

    steps = []
    for i, m in enumerate(methods):
        step: dict = {
            "id": f"step_{i}",
            "method": m["name"],
            "input": "$input" if i == 0 else f"$steps.step_{i - 1}",
        }
        steps.append(step)

    import yaml
    workflow = {
        "name": "example",
        "steps": steps,
        "output": steps[-1]["id"],
    }
    (out_dir / "example_workflow.yaml").write_text(yaml.dump(workflow, sort_keys=False))


def _write_scoreboard(out_dir: Path, mip_name: str) -> None:
    scoreboard = {
        "mip": mip_name,
        "runs": [],
    }
    (out_dir / "scoreboard.json").write_text(json.dumps(scoreboard, indent=2))


def _write_run_script(out_dir: Path, mip_path: Path, methods: list[dict]) -> None:
    script = (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n\n"
        f'MIP_PATH="{mip_path.resolve()}"\n'
        'OUT_DIR="./output"\n'
        'mkdir -p "$OUT_DIR"\n\n'
        'echo "Running example workflow..."\n'
        "python -c \"\n"
        "from pathlib import Path\n"
        "from noosphere.interop import run_mip\n"
        "from noosphere.ledger.keys import KeyRing\n"
        "import json\n\n"
        f"mip = Path('{mip_path.resolve()}')\n"
        "keyring = KeyRing()\n"
        "result = run_mip(mip, 'example', {}, Path('output'), keyring)\n"
        "print(json.dumps(result, indent=2))\n"
        '"\n'
    )
    run_sh = out_dir / "run.sh"
    run_sh.write_text(script)
    run_sh.chmod(0o755)
