"""
Source-type priors for the credibility ledger.

Each cited source has a *prior* on its credibility — the firm's belief,
before having seen any track record, about how often evidence from this
type of source holds up under later scrutiny. The priors are encoded as
Beta distributions ``Beta(alpha, beta)`` because the credibility
posterior is updated by counting confirmations and failures, which is
the textbook conjugate update for a Bernoulli-like outcome model.

We parameterise priors by ``(prior_credibility, prior_strength)`` rather
than by raw alpha/beta because that is the language in which the firm
reasons about source classes:

* ``prior_credibility`` ∈ (0, 1) — the prior mean, i.e. the firm's
  initial belief about how often a piece of evidence from this source
  type holds up.
* ``prior_strength`` > 0 — the *concentration* of the prior: how many
  pseudo-observations of evidence we treat ourselves as having already
  seen for sources of this type. A peer-reviewed paper has a stronger
  prior (more pseudo-observations) than a personal blog because the
  firm has a richer base rate to draw on; "strength" is dialled up only
  when the firm has reason to be confident in the prior, never to gloss
  over a thin track record.

Conversion: ``alpha = prior_credibility * prior_strength`` and
``beta = (1 - prior_credibility) * prior_strength``.

Citations to the firm's own reasoning live alongside each entry below.
The priors are deliberately *modest* — even peer-reviewed papers do not
start at 0.95 because the empirical replication-failure literature
(Ioannidis 2005, Open Science Collaboration 2015, Camerer et al. 2018)
puts the field-wide replication rate well below that. The firm's own
outputs (firm podcast, firm conclusions used as upstream sources) start
with a *neutral* prior (0.5) and earn credibility from the same loop
as everyone else: no self-flattering head start.

The threshold ``MIN_UPDATES_FOR_CONFIDENT_DISPLAY`` is the number of
realised updates below which the UI displays an "n=K updates" caveat
instead of a confident credibility number — five resolutions is the
firm's chosen floor (small enough that conviction can be earned in a
quarter of forecast resolutions, large enough that a single fluke does
not anchor a number).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class SourceType(str, Enum):
    """Classes of source the firm cites.

    Membership is closed: every canonical source resolves to exactly
    one of these. New types should be added explicitly here (with a
    documented prior) rather than fudged in at call sites.
    """

    PEER_REVIEWED_PAPER = "peer_reviewed_paper"
    CONFERENCE_PAPER = "conference_paper"
    PREPRINT = "preprint"
    GOVERNMENT_DATA = "government_data"
    FIRM_PODCAST = "firm_podcast"
    FIRM_CONCLUSION = "firm_conclusion"
    NEWS_MAJOR = "news_major"
    NEWS_TABLOID = "news_tabloid"
    X_POST = "x_post"
    BLOG_SELF_PUB = "blog_self_pub"
    PERSONAL_CORRESPONDENCE = "personal_correspondence"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SourcePrior:
    """A Beta prior on a source-type's credibility.

    Stored in the parameterisation the firm reasons about
    (``prior_credibility``, ``prior_strength``); the equivalent
    ``alpha``/``beta`` parameters are computed lazily.
    """

    source_type: SourceType
    prior_credibility: float
    prior_strength: float
    rationale: str

    def __post_init__(self) -> None:
        if not 0.0 < self.prior_credibility < 1.0:
            raise ValueError(
                f"prior_credibility must be in (0, 1); got {self.prior_credibility}"
            )
        if self.prior_strength <= 0.0:
            raise ValueError(
                f"prior_strength must be positive; got {self.prior_strength}"
            )

    @property
    def alpha(self) -> float:
        return self.prior_credibility * self.prior_strength

    @property
    def beta(self) -> float:
        return (1.0 - self.prior_credibility) * self.prior_strength


MIN_UPDATES_FOR_CONFIDENT_DISPLAY: int = 5


# ── The prior table ────────────────────────────────────────────────────
#
# Numbers were chosen by the firm's research lead with the rationale
# attached. They are not magic; they are starting points and will drift
# as the ledger accumulates data. Every entry has a documented reason.

_PRIOR_TABLE: dict[SourceType, SourcePrior] = {
    SourceType.PEER_REVIEWED_PAPER: SourcePrior(
        source_type=SourceType.PEER_REVIEWED_PAPER,
        prior_credibility=0.70,
        prior_strength=10.0,
        rationale=(
            "Replication-failure literature (Ioannidis 2005, "
            "Open Science Collaboration 2015 ~36% replication rate, "
            "Camerer et al. 2018 ~62%) places the field-wide rate of "
            "claims-that-hold below the rhetorical 'peer-review = truth' "
            "default. 0.70 is generous to fields with stronger track "
            "records; strength=10 because a known base rate exists."
        ),
    ),
    SourceType.CONFERENCE_PAPER: SourcePrior(
        source_type=SourceType.CONFERENCE_PAPER,
        prior_credibility=0.55,
        prior_strength=6.0,
        rationale=(
            "Conference review is faster and shallower than journal "
            "review; many fields treat the conference as a checkpoint "
            "rather than a verdict. Slightly above neutral, slightly "
            "below journal."
        ),
    ),
    SourceType.PREPRINT: SourcePrior(
        source_type=SourceType.PREPRINT,
        prior_credibility=0.45,
        prior_strength=4.0,
        rationale=(
            "Preprints have not been refereed. Some fields' preprints "
            "(maths, parts of physics) are reliable; others "
            "(biomedical) are notoriously volatile. Below neutral, low "
            "strength, so a track record can move it quickly."
        ),
    ),
    SourceType.GOVERNMENT_DATA: SourcePrior(
        source_type=SourceType.GOVERNMENT_DATA,
        prior_credibility=0.75,
        prior_strength=8.0,
        rationale=(
            "Statistical agencies (BLS, ONS, Eurostat, World Bank) "
            "publish methodology, errata, and revisions; their numbers "
            "are usually reproducible. The cap below 1 reflects "
            "definitional drift (CPI basket changes, GDP rebasing) and "
            "the rare politicised release."
        ),
    ),
    SourceType.FIRM_PODCAST: SourcePrior(
        source_type=SourceType.FIRM_PODCAST,
        prior_credibility=0.50,
        prior_strength=2.0,
        rationale=(
            "The firm's own podcast starts at neutral. We earn "
            "credibility through the same loop as everyone else; a "
            "self-flattering prior would corrupt the system. Low "
            "strength so the prior is overrideable quickly."
        ),
    ),
    SourceType.FIRM_CONCLUSION: SourcePrior(
        source_type=SourceType.FIRM_CONCLUSION,
        prior_credibility=0.50,
        prior_strength=2.0,
        rationale=(
            "Firm conclusions cited as upstream evidence start at "
            "neutral, by the same self-discipline as the firm podcast."
        ),
    ),
    SourceType.NEWS_MAJOR: SourcePrior(
        source_type=SourceType.NEWS_MAJOR,
        prior_credibility=0.55,
        prior_strength=5.0,
        rationale=(
            "Major outlets (NYT, FT, Reuters, AP, Bloomberg) have "
            "editorial process and corrections desks. Above neutral; "
            "well below government data because reporting frequently "
            "outruns evidence."
        ),
    ),
    SourceType.NEWS_TABLOID: SourcePrior(
        source_type=SourceType.NEWS_TABLOID,
        prior_credibility=0.30,
        prior_strength=4.0,
        rationale=(
            "Tabloid-format outlets prioritise narrative over "
            "verification. The prior is low but not crushing — a "
            "tabloid still gets simple facts right most of the time."
        ),
    ),
    SourceType.X_POST: SourcePrior(
        source_type=SourceType.X_POST,
        prior_credibility=0.30,
        prior_strength=2.0,
        rationale=(
            "An anonymous-or-pseudonymous post with no editorial "
            "process. Useful as a *signal*, weak as evidence. Low "
            "strength so credible posters can be lifted by their track "
            "record without dragging the class up."
        ),
    ),
    SourceType.BLOG_SELF_PUB: SourcePrior(
        source_type=SourceType.BLOG_SELF_PUB,
        prior_credibility=0.40,
        prior_strength=2.0,
        rationale=(
            "Self-published blog posts span the range from "
            "domain-expert long-form to crank. Below neutral; low "
            "strength so individual track records dominate."
        ),
    ),
    SourceType.PERSONAL_CORRESPONDENCE: SourcePrior(
        source_type=SourceType.PERSONAL_CORRESPONDENCE,
        prior_credibility=0.50,
        prior_strength=1.0,
        rationale=(
            "Private email or DM from an identified individual. "
            "Neutral — credibility is wholly derived from the "
            "individual's track record, not the channel."
        ),
    ),
    SourceType.UNKNOWN: SourcePrior(
        source_type=SourceType.UNKNOWN,
        prior_credibility=0.50,
        prior_strength=1.0,
        rationale=(
            "Sources whose type we cannot determine get a neutral, "
            "low-strength prior. This is a safety default, not a "
            "judgement."
        ),
    ),
}


def prior_for(source_type: SourceType | str | None) -> SourcePrior:
    """Resolve the prior for a source type.

    Strings are accepted for ergonomics at call sites that read source
    types out of JSON; ``None`` and unrecognised values fall through to
    ``SourceType.UNKNOWN``. Always returns a SourcePrior — never raises.
    """

    if source_type is None:
        return _PRIOR_TABLE[SourceType.UNKNOWN]
    if isinstance(source_type, SourceType):
        return _PRIOR_TABLE[source_type]
    try:
        return _PRIOR_TABLE[SourceType(str(source_type).strip().lower())]
    except ValueError:
        return _PRIOR_TABLE[SourceType.UNKNOWN]


def all_priors() -> dict[SourceType, SourcePrior]:
    """A defensive copy of the full prior table — for UI/audit views."""

    return dict(_PRIOR_TABLE)


def is_firm_source(source_type: SourceType | str | None) -> bool:
    """True for source types produced by the firm itself.

    Used by audits that confirm the firm's own outputs do not carry a
    self-flattering head-start prior.
    """

    if source_type is None:
        return False
    if isinstance(source_type, SourceType):
        st: Optional[SourceType] = source_type
    else:
        try:
            st = SourceType(str(source_type).strip().lower())
        except ValueError:
            st = None
    return st in {SourceType.FIRM_PODCAST, SourceType.FIRM_CONCLUSION}
