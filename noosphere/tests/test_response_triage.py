"""Tests for the public-response triage classifier.

Covers the F-test list in the prompt:

- triage labels are stable across small phrasing changes (heuristic
  determinism + label-stability across paraphrases),
- spam path reaches archive (label SPAM_NOISE + spam_reason recorded,
  picked up by the in-memory writer),
- the promote-to-revision path produces a payload the cascade
  ``RevisionInput`` can consume.

Also pins the heuristic boundary (so we notice if it shifts), the
LLM cap (the model can shift between buckets but cannot invent a
fifth), and the repeat-sender flag.
"""

from __future__ import annotations

import pytest

from noosphere.cascade.revision import RevisionInput
from noosphere.literature.response_triage import (
    InMemorySpamHistory,
    InMemoryTriageWriter,
    REPEAT_SPAM_FLAG_AT,
    ResponseToTriage,
    TriageResult,
    classify_heuristic,
    hash_sender,
    severity_inputs_from_triage,
    triage_response,
)
from noosphere.llm import MockLLMClient


def _resp(
    *,
    body: str,
    kind: str = "counter_argument",
    citation_url: str = "",
    response_id: str = "r1",
    submitter_email: str = "alice@example.com",
    pseudonymous: bool = False,
    conclusion_text: str = "Claim under test.",
) -> ResponseToTriage:
    return ResponseToTriage(
        response_id=response_id,
        published_conclusion_id="pc1",
        kind=kind,
        body=body,
        citation_url=citation_url,
        submitter_email=submitter_email,
        pseudonymous=pseudonymous,
        conclusion_text=conclusion_text,
    )


# ── heuristic determinism ────────────────────────────────────────────


class TestHeuristicLabels:
    def test_too_short_body_is_spam(self):
        v = classify_heuristic(_resp(body="ok"))
        assert v.label == "SPAM_NOISE"
        assert v.spam_reason == "too_short"

    def test_low_information_thanks_is_spam_noise(self):
        v = classify_heuristic(
            _resp(body="thanks for posting this!", kind="agreement_extension")
        )
        assert v.label == "SPAM_NOISE"
        assert v.spam_reason == "low_information"

    def test_promotional_link_is_spam(self):
        v = classify_heuristic(
            _resp(
                body="Great article. Click here for our crypto giveaway and free trial!",
                kind="agreement_extension",
            )
        )
        assert v.label == "SPAM_NOISE"
        assert v.spam_reason == "promotional_link"

    def test_clarification_question_routes_to_clarification(self):
        v = classify_heuristic(
            _resp(
                body=(
                    "I want to make sure I follow the argument. Could you "
                    "clarify what time horizon the claim is meant to apply to?"
                ),
                kind="clarification",
            )
        )
        assert v.label == "CLARIFICATION_REQUEST"

    def test_substantive_objection_with_citation(self):
        v = classify_heuristic(
            _resp(
                body=(
                    "I disagree — the data shows the opposite trend; the study "
                    "by Marcus et al. controls for selection and finds a "
                    "negative effect. The piece overlooks that finding entirely."
                ),
                kind="counter_evidence",
                citation_url="https://example.org/marcus-2024",
            )
        )
        assert v.label == "SUBSTANTIVE_OBJECTION"
        assert v.confidence > 0.5

    def test_general_engagement_default(self):
        v = classify_heuristic(
            _resp(
                body=(
                    "Interesting take. I have been thinking about something "
                    "similar in my own field for a while now."
                ),
                kind="agreement_extension",
            )
        )
        assert v.label == "GENERAL_ENGAGEMENT"


# ── label stability across paraphrases ───────────────────────────────


class TestLabelStability:
    """Small phrasing changes should not flip the bucket."""

    paraphrases_objection = [
        (
            "I disagree — the data shows the opposite trend; the study by "
            "Marcus et al. controls for selection and finds a negative effect."
        ),
        (
            "Actually the evidence shows the opposite: Marcus et al. (2024) "
            "control for selection and report a negative effect."
        ),
        (
            "However, this overlooks Marcus et al.'s study, which contradicts "
            "the headline finding once selection is controlled for."
        ),
    ]

    paraphrases_clarification = [
        "Could you clarify what time horizon you mean here?",
        "Can you explain what time horizon the claim applies to?",
        "What time window does this claim cover, exactly?",
    ]

    def test_substantive_paraphrases_stay_substantive(self):
        for p in self.paraphrases_objection:
            v = classify_heuristic(
                _resp(body=p, kind="counter_evidence", citation_url="https://x.example")
            )
            assert v.label == "SUBSTANTIVE_OBJECTION", (p, v)

    def test_clarification_paraphrases_stay_clarifications(self):
        for p in self.paraphrases_clarification:
            v = classify_heuristic(_resp(body=p, kind="clarification"))
            assert v.label == "CLARIFICATION_REQUEST", (p, v)


# ── pipeline integration ─────────────────────────────────────────────


class TestTriageResponse:
    def test_writes_to_writer(self):
        w = InMemoryTriageWriter()
        r = _resp(body="ok x")  # too-short -> spam
        result = triage_response(r, writer=w)
        assert isinstance(result, TriageResult)
        assert result.label == "SPAM_NOISE"
        assert w.latest_for("r1") is result

    def test_substantive_path_emits_implied_objection(self):
        result = triage_response(
            _resp(
                body=(
                    "I disagree. The data shows the opposite trend in the "
                    "Marcus et al. study; the conclusion overlooks that finding."
                ),
                kind="counter_evidence",
                citation_url="https://example.org/m",
            )
        )
        assert result.label == "SUBSTANTIVE_OBJECTION"
        assert result.implied_objection
        assert result.implied_objection.endswith(".") or len(result.implied_objection) > 0

    def test_pseudonymous_email_blank_no_sender_hash(self):
        result = triage_response(
            _resp(body="ok x", submitter_email=""),
        )
        assert result.sender_hash == ""

    def test_repeat_sender_flag_promotes_to_repeat_spam_reason(self):
        history = InMemorySpamHistory()
        h = hash_sender("spammer@example.com")
        history.counts[h] = REPEAT_SPAM_FLAG_AT  # already over threshold

        # A short low-information message that would otherwise be
        # "low_information" is upgraded to "repeat_sender" because the
        # sender has been judged spam before.
        result = triage_response(
            _resp(
                body="thanks much for the post!!",
                submitter_email="spammer@example.com",
            ),
            history=history,
        )
        assert result.elevated_sender_flag is True
        assert result.label == "SPAM_NOISE"
        assert result.spam_reason == "repeat_sender"

    def test_first_offence_keeps_specific_spam_reason(self):
        history = InMemorySpamHistory()
        result = triage_response(
            _resp(
                body="Buy now! Free trial! Click here!",
                submitter_email="new@example.com",
            ),
            history=history,
        )
        assert result.elevated_sender_flag is False
        assert result.label == "SPAM_NOISE"
        assert result.spam_reason == "promotional_link"


# ── LLM refinement: cap to 4 buckets ─────────────────────────────────


class TestLLMRefinement:
    def test_llm_can_shift_label_within_schema(self):
        # Body has a question mark; heuristic might pick CLARIFICATION,
        # but the LLM judges it as a substantive objection. We accept
        # the shift because both labels are valid members.
        llm = MockLLMClient(
            responses=[
                '{"label":"SUBSTANTIVE_OBJECTION",'
                '"spam_reason":"",'
                '"implied_objection":"The trend reverses once selection is controlled for.",'
                '"rationale":"reader cites Marcus et al."}'
            ]
        )
        # Use a deliberately ambiguous body so heuristic confidence is
        # below LLM_CONSULT_BELOW, triggering the LLM call.
        result = triage_response(
            _resp(
                body="Marcus et al. found the opposite. Wouldn't that contradict the claim?",
                kind="clarification",
            ),
            llm=llm,
        )
        assert result.used_llm is True
        assert result.label == "SUBSTANTIVE_OBJECTION"
        assert "selection" in result.implied_objection

    def test_llm_invalid_label_falls_back_to_heuristic(self):
        # Model returns a bogus 5th label — we ignore the LLM and keep
        # the heuristic verdict.
        llm = MockLLMClient(
            responses=['{"label":"NUKE_FROM_ORBIT","spam_reason":"","implied_objection":"","rationale":""}']
        )
        before = classify_heuristic(
            _resp(
                body="Hmm, I have a partial reservation about the framing.",
                kind="counter_argument",
            )
        )
        result = triage_response(
            _resp(
                body="Hmm, I have a partial reservation about the framing.",
                kind="counter_argument",
            ),
            llm=llm,
        )
        assert result.used_llm is False
        assert result.label == before.label

    def test_llm_malformed_json_falls_back(self):
        llm = MockLLMClient(responses=["this is not JSON"])
        result = triage_response(
            _resp(body="Hmm, I have a partial reservation."),
            llm=llm,
        )
        assert result.used_llm is False


# ── archive path: spam-rows still get persisted with reason ──────────


class TestSpamArchive:
    def test_spam_row_carries_reason_to_writer(self):
        w = InMemoryTriageWriter()
        triage_response(
            _resp(body="ok"),
            writer=w,
        )
        assert len(w.rows) == 1
        row = w.rows[0]
        assert row.label == "SPAM_NOISE"
        assert row.spam_reason == "too_short"

    def test_spam_reason_audit_overrideable(self):
        # The classifier itself doesn't override; that's the founder's
        # job. But the writer should expose enough state for the queue
        # UI to render an "override" button. We assert the to_dict
        # contract here so the API surface stays stable.
        result = triage_response(_resp(body="ok"))
        d = result.to_dict()
        assert d["label"] == "SPAM_NOISE"
        assert d["spam_reason"] == "too_short"
        assert "rationale" in d


# ── promote to revision engine ───────────────────────────────────────


class TestPromoteToRevision:
    def test_severity_inputs_routes_to_revision_input_payload(self):
        triage = triage_response(
            _resp(
                body=(
                    "I disagree — the data show the opposite trend in Marcus "
                    "et al. (2024); the piece overlooks that finding entirely."
                ),
                kind="counter_evidence",
                citation_url="https://example.org/marcus-2024",
            )
        )
        assert triage.label == "SUBSTANTIVE_OBJECTION"

        sev_input = severity_inputs_from_triage(
            triage,
            cascade_weight=0.85,
            claim_centrality=0.7,
            failure_mode_severity=0.0,
            source_credibility=0.8,
        )
        assert sev_input["objection_text"] == triage.implied_objection
        assert sev_input["cascade_weight"] == pytest.approx(0.85)

        # The promote-to-revision path: the founder takes the
        # implied objection and constructs a RevisionInput targeting
        # the claim the response attacks. We assert the payload shape
        # rather than a full revision run (covered in test_revision.py).
        ri = RevisionInput(
            claim_id="claim-target",
            new_evidence=triage.implied_objection,
            weight=-0.6,  # the response contradicts the claim
        )
        assert ri.claim_id == "claim-target"
        assert ri.clamped_weight() == pytest.approx(-0.6)
        assert ri.new_evidence == triage.implied_objection
