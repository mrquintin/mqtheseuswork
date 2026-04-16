"""Generate a Dockerfile and optionally run ``docker build``."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DOCKERFILE_TEMPLATE = """\
FROM python:{python_version}-slim

WORKDIR /app

COPY implementation/ /app/implementation/
COPY adapter.py /app/adapter.py
{copy_requirements}

{install_requirements}

ENTRYPOINT ["python", "adapter.py"]
"""


def render_dockerfile(
    python_version: str = "3.11",
    has_requirements: bool = True,
) -> str:
    """Return a rendered Dockerfile string."""
    if has_requirements:
        copy_req = "COPY implementation/requirements.txt /app/requirements.txt"
        install_req = 'RUN pip install --no-cache-dir -r requirements.txt'
    else:
        copy_req = ""
        install_req = ""

    return DOCKERFILE_TEMPLATE.format(
        python_version=python_version,
        copy_requirements=copy_req,
        install_requirements=install_req,
    )


def write_dockerfile(out_dir: Path, python_version: str = "3.11") -> Path:
    """Write a Dockerfile into *out_dir* and return its path."""
    has_reqs = (out_dir / "implementation" / "requirements.txt").exists()
    content = render_dockerfile(python_version=python_version, has_requirements=has_reqs)
    df_path = out_dir / "Dockerfile"
    df_path.write_text(content)
    return df_path


def docker_build(
    context_dir: Path,
    tag: Optional[str] = None,
    timeout: int = 300,
) -> Optional[str]:
    """Run ``docker build`` in *context_dir* and return the image digest.

    Returns ``None`` if Docker is not available or the build fails.
    """
    cmd = ["docker", "build", "."]
    if tag:
        cmd.extend(["-t", tag])
    try:
        result = subprocess.run(
            cmd,
            cwd=str(context_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            logger.warning("docker build failed: %s", result.stderr[:500])
            return None

        digest_result = subprocess.run(
            ["docker", "inspect", "--format", "{{.Id}}", tag or "."],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if digest_result.returncode == 0:
            return digest_result.stdout.strip()
        return None
    except FileNotFoundError:
        logger.info("Docker not available on this host")
        return None
    except subprocess.TimeoutExpired:
        logger.warning("docker build timed out after %ds", timeout)
        return None
