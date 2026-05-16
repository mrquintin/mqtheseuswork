"""Synthetic schema-drift fixture for the API type-sync gate.

``FixtureModel`` below is the *committed* shape. ``FixtureModelDrifted``
is what the same model would look like if a developer renamed a field
without regenerating the TS types — the drift test instantiates a
mini-FastAPI app with the drifted model, runs the generator in a temp
directory, and asserts the output differs from the committed
``synthetic_drift_fixture.ts`` baseline.

The fixture is not on the production import path; only the test pulls
it in.
"""

from __future__ import annotations

from pydantic import BaseModel


class FixtureModel(BaseModel):
    """Baseline shape — must match ``synthetic_drift_fixture.ts``."""

    id: str
    name: str
    score: float


class FixtureModelDrifted(BaseModel):
    """Drifted shape — adds ``new_field``; the generator must surface it."""

    id: str
    name: str
    score: float
    new_field: int
