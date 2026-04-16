from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from noosphere.peer_review.reviewer import Reviewer

_REVIEWERS: dict[str, type[Reviewer]] = {}


def register(cls: type[Reviewer]) -> type[Reviewer]:
    _REVIEWERS[cls.name] = cls
    return cls


def all_reviewers() -> list[type[Reviewer]]:
    return list(_REVIEWERS.values())


from noosphere.peer_review.reviewers import methodological as _methodological  # noqa: E402, F401
from noosphere.peer_review.reviewers import evidential as _evidential  # noqa: E402, F401
from noosphere.peer_review.reviewers import statistical as _statistical  # noqa: E402, F401
from noosphere.peer_review.reviewers import adv_literature as _adv_literature  # noqa: E402, F401
from noosphere.peer_review.reviewers import replication as _replication  # noqa: E402, F401
from noosphere.peer_review.reviewers import rhetorical as _rhetorical  # noqa: E402, F401
from noosphere.peer_review.reviewers import humility as _humility  # noqa: E402, F401
