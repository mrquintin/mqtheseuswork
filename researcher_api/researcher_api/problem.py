"""RFC 7807 Problem Details for HTTP APIs (application/problem+json)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Problem(BaseModel):
    type: str = Field(default="about:blank")
    title: str
    status: int
    detail: str
    instance: str | None = None
    extensions: dict[str, Any] = Field(default_factory=dict)
