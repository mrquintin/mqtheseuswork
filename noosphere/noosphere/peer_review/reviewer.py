from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from noosphere.models import Conclusion, ReviewReport


@dataclass
class BiasProfile:
    name: str
    prior: str
    known_blindspots: list[str] = field(default_factory=list)


class Reviewer(ABC):
    name: str
    bias_profile: BiasProfile

    @abstractmethod
    def review(self, conclusion: Conclusion, context: dict[str, Any]) -> ReviewReport:
        ...
