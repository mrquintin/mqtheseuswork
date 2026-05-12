"""Multi-frame decision engine.

The engine evaluates a candidate trade decision through several explicit,
deterministic decision frames (incentive alignment, coordination
equilibrium, principal-agent, reflexivity, option value, contradiction
pressure, empirical transfer) and synthesizes the frame verdicts into a
single recommended action. The synthesis rule is explicit: strong
action only when multiple frames agree and no hard-stop frame fails;
WATCH when frames split but evidence is relevant; ABSTAIN when
assumptions are unstable or a hard-stop contradiction is present;
REDUCE/EXIT when downside frames dominate.

No LLM calls, no randomness. Same inputs → same verdict.
"""

from noosphere.decisions.frames import (
    Frame,
    FrameContext,
    FrameResult,
    FrameVerdict,
    contradiction_frame,
    coordination_equilibrium_frame,
    empirical_transfer_frame,
    incentive_alignment_frame,
    option_value_frame,
    principal_agent_frame,
    reflexivity_frame,
    run_frames,
)
from noosphere.decisions.synthesis import (
    DecisionSynthesis,
    SynthesisAction,
    synthesize,
)


__all__ = [
    "DecisionSynthesis",
    "Frame",
    "FrameContext",
    "FrameResult",
    "FrameVerdict",
    "SynthesisAction",
    "contradiction_frame",
    "coordination_equilibrium_frame",
    "empirical_transfer_frame",
    "incentive_alignment_frame",
    "option_value_frame",
    "principal_agent_frame",
    "reflexivity_frame",
    "run_frames",
    "synthesize",
]
