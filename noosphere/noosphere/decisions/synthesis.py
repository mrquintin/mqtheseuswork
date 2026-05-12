"""Synthesis rule — combine multiple frame verdicts into one action.

The rule, in priority order:

1. Any :class:`FrameVerdict.HARD_STOP` → :class:`SynthesisAction.ABSTAIN`,
   regardless of how many other frames agreed. (Hard stops are
   categorical refusals; counting them against majority votes would
   defeat their purpose.)
2. Any :class:`FrameVerdict.EXIT` from a position-aware frame →
   :class:`SynthesisAction.EXIT`. ``EXIT`` overrides ``REDUCE``
   and ``HEDGE``.
3. Any :class:`FrameVerdict.REDUCE` (and no EXIT/HARD_STOP) →
   :class:`SynthesisAction.REDUCE`.
4. ``HEDGE`` (rare in v1) → :class:`SynthesisAction.HEDGE`.
5. If a configurable fraction of frames flag ``assumptions_stable=False``
   → :class:`SynthesisAction.ABSTAIN` (assumptions too unstable).
6. If a strict majority of *eligible* frames vote ``SUPPORT`` and no
   frame voted ``ABSTAIN`` with a hard reason → :class:`SynthesisAction.SUPPORT`
   (strong action — the caller decides whether to paper-trade or live).
7. Otherwise → :class:`SynthesisAction.WATCH` if any frame had a
   relevant signal, else :class:`SynthesisAction.ABSTAIN`.

The result records *which* frames agreed, *which* dissented, and the
synthesis path taken — so a reader can inspect the trace and see the
reasoning rather than just the verdict.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Any, Sequence

from noosphere.decisions.frames import FrameResult, FrameVerdict


SYNTHESIS_VERSION = "decision_synthesis@v1"


# SUPPORT requires *all* assumption-stable frames to vote SUPPORT.
# A single WATCH/REDUCE among the stable frames downgrades to WATCH;
# this is the synthesis-level enforcement of "strong action only when
# multiple frames agree and no frame dissents". Unstable frames are
# treated as "no signal" — they neither support nor block.
MIN_ELIGIBLE_FRAMES_FOR_SUPPORT = 3

# The set of verdicts that count as "this frame had a real signal".
# WATCH counts as a signal; ABSTAIN does not.
RELEVANT_SIGNAL_VERDICTS = frozenset(
    {
        FrameVerdict.SUPPORT,
        FrameVerdict.WATCH,
        FrameVerdict.REDUCE,
        FrameVerdict.EXIT,
        FrameVerdict.HEDGE,
        FrameVerdict.HARD_STOP,
    }
)


class SynthesisAction(str, Enum):
    """Final synthesized action.

    Aligned with :class:`noosphere.forecasts.decision_metrics.MarketDecisionAction`
    so the synthesis can be quoted in the market decision trace
    without re-mapping. ``SUPPORT`` is the synthesis-level analog of
    "the lenses agree the trade is warranted"; the *capital* layer
    (paper vs live) is decided downstream from the existing rule
    graph, not here.
    """

    SUPPORT = "SUPPORT"
    WATCH = "WATCH"
    ABSTAIN = "ABSTAIN"
    REDUCE = "REDUCE"
    EXIT = "EXIT"
    HEDGE = "HEDGE"


@dataclass(frozen=True)
class DecisionSynthesis:
    action: SynthesisAction
    side: str | None
    agreement: float
    supporting_frames: tuple[str, ...]
    blocking_frames: tuple[str, ...]
    abstaining_frames: tuple[str, ...]
    watch_frames: tuple[str, ...]
    hard_stop_frames: tuple[str, ...]
    unstable_frames: tuple[str, ...]
    reasons: tuple[str, ...]
    frame_results: tuple[FrameResult, ...]
    synthesis_version: str = SYNTHESIS_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "side": self.side,
            "agreement": round(float(self.agreement), 6),
            "supporting_frames": list(self.supporting_frames),
            "blocking_frames": list(self.blocking_frames),
            "abstaining_frames": list(self.abstaining_frames),
            "watch_frames": list(self.watch_frames),
            "hard_stop_frames": list(self.hard_stop_frames),
            "unstable_frames": list(self.unstable_frames),
            "reasons": list(self.reasons),
            "frames": [r.to_dict() for r in self.frame_results],
            "synthesis_version": self.synthesis_version,
        }


def _majority_side(frames: Sequence[FrameResult]) -> str | None:
    counts: Counter[str] = Counter()
    for frame in frames:
        if frame.side_preference is None:
            continue
        if frame.verdict in (FrameVerdict.ABSTAIN, FrameVerdict.HARD_STOP):
            continue
        counts[frame.side_preference] += 1
    if not counts:
        return None
    top, top_count = counts.most_common(1)[0]
    # require a strict plurality over the alternatives
    for side, count in counts.items():
        if side != top and count >= top_count:
            return None
    return top


def synthesize(
    frame_results: Sequence[FrameResult],
    *,
    default_side: str | None = None,
) -> DecisionSynthesis:
    """Combine frame results into a single action."""

    results = tuple(frame_results)
    hard_stops = tuple(r.name for r in results if r.verdict == FrameVerdict.HARD_STOP)
    exits = tuple(r.name for r in results if r.verdict == FrameVerdict.EXIT)
    reduces = tuple(r.name for r in results if r.verdict == FrameVerdict.REDUCE)
    hedges = tuple(r.name for r in results if r.verdict == FrameVerdict.HEDGE)
    supports = tuple(r.name for r in results if r.verdict == FrameVerdict.SUPPORT)
    watches = tuple(r.name for r in results if r.verdict == FrameVerdict.WATCH)
    abstains = tuple(r.name for r in results if r.verdict == FrameVerdict.ABSTAIN)
    unstable = tuple(r.name for r in results if not r.assumptions_stable)

    side = _majority_side(results) or default_side
    reasons: list[str] = []

    total = max(1, len(results))
    support_share = len(supports) / total
    eligible = [r for r in results if r.assumptions_stable]
    eligible_supports = [r for r in eligible if r.verdict == FrameVerdict.SUPPORT]
    eligible_dissent = [r for r in eligible if r.verdict not in (FrameVerdict.SUPPORT,)]

    # Priority 1: any HARD_STOP forces ABSTAIN.
    if hard_stops:
        reasons.append(
            "HARD_STOP from " + ", ".join(hard_stops) + " → abstain regardless of other frames"
        )
        return DecisionSynthesis(
            action=SynthesisAction.ABSTAIN,
            side=None,
            agreement=support_share,
            supporting_frames=supports,
            blocking_frames=hard_stops,
            abstaining_frames=abstains,
            watch_frames=watches,
            hard_stop_frames=hard_stops,
            unstable_frames=unstable,
            reasons=tuple(reasons),
            frame_results=results,
        )

    # Priority 2: EXIT trumps everything else short of HARD_STOP.
    if exits:
        reasons.append("EXIT signaled by " + ", ".join(exits))
        return DecisionSynthesis(
            action=SynthesisAction.EXIT,
            side=None,
            agreement=support_share,
            supporting_frames=supports,
            blocking_frames=(),
            abstaining_frames=abstains,
            watch_frames=watches,
            hard_stop_frames=(),
            unstable_frames=unstable,
            reasons=tuple(reasons),
            frame_results=results,
        )

    # Priority 3: REDUCE.
    if reduces:
        reasons.append("REDUCE signaled by " + ", ".join(reduces))
        return DecisionSynthesis(
            action=SynthesisAction.REDUCE,
            side=side,
            agreement=support_share,
            supporting_frames=supports,
            blocking_frames=(),
            abstaining_frames=abstains,
            watch_frames=watches,
            hard_stop_frames=(),
            unstable_frames=unstable,
            reasons=tuple(reasons),
            frame_results=results,
        )

    # Priority 4: HEDGE.
    if hedges:
        reasons.append("HEDGE signaled by " + ", ".join(hedges))
        return DecisionSynthesis(
            action=SynthesisAction.HEDGE,
            side=side,
            agreement=support_share,
            supporting_frames=supports,
            blocking_frames=(),
            abstaining_frames=abstains,
            watch_frames=watches,
            hard_stop_frames=(),
            unstable_frames=unstable,
            reasons=tuple(reasons),
            frame_results=results,
        )

    # Priority 5: too few assumption-stable frames to act.
    if len(eligible) < MIN_ELIGIBLE_FRAMES_FOR_SUPPORT:
        reasons.append(
            f"only {len(eligible)}/{total} frames have stable assumptions —"
            f" below floor {MIN_ELIGIBLE_FRAMES_FOR_SUPPORT}"
        )
        return DecisionSynthesis(
            action=SynthesisAction.ABSTAIN,
            side=None,
            agreement=support_share,
            supporting_frames=supports,
            blocking_frames=(),
            abstaining_frames=abstains,
            watch_frames=watches,
            hard_stop_frames=(),
            unstable_frames=unstable,
            reasons=tuple(reasons),
            frame_results=results,
        )

    # Priority 6: every stable-assumption frame supports the trade.
    # An unstable frame is treated as "no signal", not as dissent.
    if eligible_supports and not eligible_dissent:
        reasons.append(
            f"all {len(eligible)} assumption-stable frames SUPPORT → strong action"
        )
        return DecisionSynthesis(
            action=SynthesisAction.SUPPORT,
            side=side,
            agreement=support_share,
            supporting_frames=supports,
            blocking_frames=(),
            abstaining_frames=abstains,
            watch_frames=watches,
            hard_stop_frames=(),
            unstable_frames=unstable,
            reasons=tuple(reasons),
            frame_results=results,
        )

    # Priority 7: if anyone had a real signal, WATCH; else ABSTAIN.
    relevant = [r for r in results if r.verdict in RELEVANT_SIGNAL_VERDICTS]
    if relevant:
        reasons.append(
            f"frames split — supports={len(supports)} watches={len(watches)} abstains={len(abstains)}"
        )
        return DecisionSynthesis(
            action=SynthesisAction.WATCH,
            side=side,
            agreement=support_share,
            supporting_frames=supports,
            blocking_frames=(),
            abstaining_frames=abstains,
            watch_frames=watches,
            hard_stop_frames=(),
            unstable_frames=unstable,
            reasons=tuple(reasons),
            frame_results=results,
        )

    reasons.append("no frame produced an actionable signal")
    return DecisionSynthesis(
        action=SynthesisAction.ABSTAIN,
        side=None,
        agreement=support_share,
        supporting_frames=(),
        blocking_frames=(),
        abstaining_frames=abstains,
        watch_frames=(),
        hard_stop_frames=(),
        unstable_frames=unstable,
        reasons=tuple(reasons),
        frame_results=results,
    )


def synthesis_to_dict(synthesis: DecisionSynthesis) -> dict[str, Any]:
    return synthesis.to_dict()


__all__ = [
    "DecisionSynthesis",
    "MIN_ELIGIBLE_FRAMES_FOR_SUPPORT",
    "SYNTHESIS_VERSION",
    "SynthesisAction",
    "synthesis_to_dict",
    "synthesize",
]
