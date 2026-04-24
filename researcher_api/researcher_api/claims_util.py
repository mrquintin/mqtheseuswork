from __future__ import annotations

import uuid
from datetime import date

from noosphere.models import Claim, ClaimOrigin, ClaimType, InputSourceType, Speaker


def synthetic_claim(text: str, *, slot: str) -> Claim:
    """Minimal Claim for API-only coherence (no firm linkage)."""
    return Claim(
        id=str(uuid.uuid4()),
        text=text.strip(),
        speaker=Speaker(id=f"api-{slot}", name=f"Researcher {slot}", role="api"),
        episode_id="researcher-api",
        episode_date=date.today(),
        claim_type=ClaimType.EMPIRICAL,
        claim_origin=ClaimOrigin.FOUNDER,
        source_type=InputSourceType.WRITTEN,
        founder_id="",
        voice_id="",
    )
