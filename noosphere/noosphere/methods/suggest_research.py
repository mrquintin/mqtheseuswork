"""
Registered method: Generate research topic and reading suggestions.

Wraps the legacy ResearchAdvisor as a registered method that produces
topic proposals with empirical anchors and curated readings.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from noosphere.models import MethodType
from noosphere.methods._decorator import register_method


class SuggestResearchInput(BaseModel):
    episode_number: int
    episode_title: str
    claim_texts: list[str] = Field(default_factory=list)
    new_principle_texts: list[str] = Field(default_factory=list)
    contradiction_pairs: list[list[str]] = Field(default_factory=list)


class AnchorItem(BaseModel):
    title: str
    period: str = ""
    summary: str = ""
    relevance: str = ""


class ReadingItem(BaseModel):
    title: str
    author: str
    year: str = ""
    type: str = "book"
    reason: str = ""


class TopicItem(BaseModel):
    title: str
    philosophical_question: str
    connection_to_discussion: str = ""
    ramifications: str = ""
    priority: str = "medium"
    empirical_anchors: list[AnchorItem] = Field(default_factory=list)
    readings: list[ReadingItem] = Field(default_factory=list)


class SuggestResearchOutput(BaseModel):
    topics: list[TopicItem] = Field(default_factory=list)
    cross_cutting_themes: list[str] = Field(default_factory=list)


@register_method(
    name="suggest_research",
    version="1.0.0",
    method_type=MethodType.AGGREGATION,
    input_schema=SuggestResearchInput,
    output_schema=SuggestResearchOutput,
    description="Generates research topics, empirical anchors, and reading lists after a discussion.",
    rationale=(
        "Wraps legacy ResearchAdvisor — analyses discussion output to identify "
        "productive inquiry lines, research historical parallels, and curate readings "
        "that ground philosophical questions in empirical reality."
    ),
    owner="founder",
    status="active",
    nondeterministic=True,
    emits_edges=[],
    dependencies=[],
)
def suggest_research(
    input_data: SuggestResearchInput,
) -> SuggestResearchOutput:
    from noosphere.methods._legacy.research_advisor import _call_llm

    principle_block = "\n".join(
        f"- {t}" for t in input_data.new_principle_texts[:15]
    )
    claim_block = "\n".join(f"- {t}" for t in input_data.claim_texts[:25])
    contradiction_block = "\n".join(
        f"- \"{pair[0]}\" vs \"{pair[1]}\"" for pair in input_data.contradiction_pairs[:8]
        if len(pair) >= 2
    )

    prompt = (
        f"Episode {input_data.episode_number}: {input_data.episode_title}\n\n"
        f"NEW PRINCIPLES:\n{principle_block or 'None'}\n\n"
        f"CONTRADICTIONS:\n{contradiction_block or 'None'}\n\n"
        f"SAMPLE CLAIMS:\n{claim_block or 'None'}\n\n"
        "Identify 3-5 research topics for the next discussion. For each provide: "
        "title, philosophical_question, connection, ramifications, priority, "
        "2 empirical_anchors (title, period, summary, relevance), "
        "3 readings (title, author, year, type, reason). "
        "Format as JSON array."
    )

    import json
    import re

    raw = _call_llm(prompt, system="You are a philosophical research advisor.", max_tokens=3500)

    topics: list[TopicItem] = []
    try:
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            for item in data:
                anchors = [
                    AnchorItem(**a) for a in item.get("empirical_anchors", [])
                ]
                readings = [
                    ReadingItem(**r) for r in item.get("readings", [])
                ]
                topics.append(TopicItem(
                    title=item.get("title", ""),
                    philosophical_question=item.get("philosophical_question", ""),
                    connection_to_discussion=item.get("connection", ""),
                    ramifications=item.get("ramifications", ""),
                    priority=item.get("priority", "medium"),
                    empirical_anchors=anchors,
                    readings=readings,
                ))
    except (json.JSONDecodeError, TypeError, KeyError):
        pass

    return SuggestResearchOutput(topics=topics, cross_cutting_themes=[])
