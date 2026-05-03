from noosphere.relevant_text import select_pertinent_text


def test_written_upload_prompt_is_removed_from_analysis_text() -> None:
    raw = "\n\n".join(
        [
            "Prompt: Write an essay about whether schools should rank students.",
            (
                "Schools should treat ranking as a design choice rather than a moral "
                "default because incentives shape the kind of inquiry students learn "
                "to value."
            ),
        ]
    )

    pertinent = select_pertinent_text(raw, source_type="written", mime_type="application/pdf")

    assert pertinent.changed is True
    assert "Prompt:" not in pertinent.text
    assert "Schools should treat ranking" in pertinent.text


def test_transcript_upload_preserves_multiple_speakers() -> None:
    raw = "\n".join(
        [
            "Host: Why does this matter?",
            "Michael: The important thing is how the reasoning changes.",
            "Ada: The handoff between speakers is part of the source.",
        ]
    )

    pertinent = select_pertinent_text(raw, source_type="transcript", mime_type="text/plain")

    assert pertinent.changed is False
    assert "Host:" in pertinent.text
    assert "Ada:" in pertinent.text
