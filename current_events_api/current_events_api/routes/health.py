"""Health endpoints that surface env validation reports.

Sibling to the ``/readyz`` block in ``current_events_api.main`` — this
router adds the explicit ``/readyz/env`` endpoint so an operator can
curl just the env validation report (secrets redacted) without
inspecting scheduler freshness or DB connectivity.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter

from noosphere.core.env_validation import parse_mode, validate_env


router = APIRouter()


@router.get("/readyz/env")
def readyz_env() -> dict[str, Any]:
    """Return the env validation report for the current process.

    Secret values are masked (``"***"``) inside the env_validation
    layer; this endpoint never sees the raw secret.
    """
    mode = parse_mode(os.environ.get("THESEUS_MODE"))
    report = validate_env(mode)
    return report.to_dict()
