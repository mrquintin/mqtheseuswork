from __future__ import annotations

import json

from noosphere.llm import MockLLMClient
from noosphere.social.substack_formatter import format_for_substack


TRANSCRIPT = """[00:00:12] Michael: The question is whether conviction can survive inspection.
[00:01:44] Ada: The ledger matters because memory changes incentives.
[00:03:02] Michael: We should publish the parts that can bear pressure."""


def test_substack_formatter_builds_session_markdown_with_highlights() -> None:
    blurb = " ".join(["This transcript turns a private exchange into an inspectable public artifact."] * 7)
    why = " ".join(["The firm publishes this because durable reasoning must survive later inspection."] * 4)
    llm = MockLLMClient(
        responses=[
            json.dumps(
                {
                    "subtitle": "A founder conversation about turning reasoning into public capital.",
                    "blurb": blurb,
                    "highlights": [
                        {
                            "timestamp": "00:00:12",
                            "line": "The question is whether conviction can survive inspection.",
                        },
                        {
                            "timestamp": "00:01:44",
                            "line": "The ledger matters because memory changes incentives.",
                        },
                        {
                            "timestamp": "00:03:02",
                            "line": "Publish the parts that can bear pressure.",
                        },
                    ],
                    "why_this_matters": why,
                }
            )
        ],
        prompt_must_contain=("timestamped_lines",),
    )

    payload = format_for_substack(
        title="recorded reasoning as capital",
        source_text=TRANSCRIPT,
        source_kind="session",
        llm_client=llm,
    )

    assert payload["subject"] == "Recorded Reasoning as Capital"
    assert len(payload["subject"]) <= 100
    assert len(payload["body"]) <= 240
    assert payload["markdownBody"].startswith(blurb)
    assert "## Highlights" in payload["markdownBody"]
    assert "- 00:00:12 - The question is whether conviction can survive inspection." in payload["markdownBody"]
    assert TRANSCRIPT in payload["markdownBody"]


def test_substack_formatter_skips_highlights_for_essay() -> None:
    essay = "Theseus begins with recorded judgment. " * 30
    payload = format_for_substack(
        title="a thesis on intellectual capital",
        source_text=essay,
        source_kind="essay",
        llm_client=MockLLMClient(responses=[]),
    )

    assert "## Highlights" not in payload["markdownBody"]
    assert "## Essay" in payload["markdownBody"]
    assert essay.strip() in payload["markdownBody"]
