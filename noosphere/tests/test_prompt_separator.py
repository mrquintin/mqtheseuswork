"""Tests for the prompt/question pre-processor."""

from __future__ import annotations

from noosphere.mitigations.prompt_separator import PromptSeparator, SeparatedContent


def test_simple_qa_format() -> None:
    text = (
        "Q: What do you think about X?\n\n"
        "A: I think X is important because it grounds everything else.\n\n"
        "Q: And Y?\n\n"
        "A: Y follows from X in a straightforward way."
    )
    result = PromptSeparator().separate(text, source_type="written")
    # Two prompts, two founder responses.
    assert len(result.prompt_sections) == 2, result.prompt_sections
    assert len(result.founder_sections) == 2, result.founder_sections
    assert "I think X is important" in result.founder_text
    assert "follows from X" in result.founder_text
    # Prompts should not bleed into founder sections.
    assert "What do you think" not in result.founder_text


def test_interview_transcript_with_speaker_labels() -> None:
    text = (
        "Interviewer: Isn't your position wrong because of Z?\n"
        "Jane Smith: No — my position explicitly addresses Z. The argument is A → B → C.\n"
        "Interviewer: Can you say more about C?\n"
        "Jane Smith: C is the operational consequence of the A-B move."
    )
    result = PromptSeparator(founder_names=["Jane Smith"]).separate(
        text, source_type="transcript"
    )
    assert "A → B → C" in result.founder_text
    assert "operational consequence" in result.founder_text
    assert "Isn't your position wrong" in result.prompt_text
    assert result.confidence >= 0.9


def test_essay_without_prompts_stays_all_founder() -> None:
    text = (
        "Strategy is the allocation of scarce attention to compounding loops. "
        "Most firms fail because they misidentify their compounding loop.\n\n"
        "Identifying the loop requires examining outputs that grow as a "
        "nonlinear function of inputs."
    )
    result = PromptSeparator().separate(text, source_type="written")
    assert result.prompt_sections == []
    assert len(result.founder_sections) == 2
    assert "compounding loops" in result.founder_text


def test_blockquote_paragraph_is_prompt() -> None:
    text = (
        "> Isn't the whole premise of your framework begging the question?\n\n"
        "The apparent circularity dissolves once you distinguish the "
        "descriptive claim from the normative one. The framework asserts the "
        "former and implies the latter — not the reverse."
    )
    result = PromptSeparator().separate(text, source_type="written")
    assert any("begging the question" in p for p in result.prompt_sections)
    assert "apparent circularity" in result.founder_text


def test_empty_input_returns_empty_confident_result() -> None:
    result = PromptSeparator().separate("", source_type="written")
    assert result.founder_sections == []
    assert result.prompt_sections == []
    assert result.confidence == 1.0


def test_response_after_prompt_is_tagged_founder_even_without_prefix() -> None:
    text = (
        "Q: Why does your model of time treat uncertainty as primary?\n\n"
        "Because every other primitive in the system depends on it — if "
        "uncertainty weren't primary, the calibration steps would have "
        "nothing to anchor to."
    )
    result = PromptSeparator().separate(text, source_type="written")
    assert len(result.prompt_sections) == 1
    assert len(result.founder_sections) == 1
    assert "every other primitive" in result.founder_text
