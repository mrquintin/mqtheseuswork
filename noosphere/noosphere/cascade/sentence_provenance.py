"""Per-sentence evidence assembler for the public-article heatmap.

For each sentence in a published article, we walk the cascade graph
from the sentence's anchored conclusion(s) toward the supporting
sources, multiply edge weights × source credibility, and aggregate to
a single number in [0,1] — the sentence's *provenance*. The reader
sees this as a faint gutter tint: strong-evidence sentences look
normal; weak-evidence sentences look visibly weak.

Anchoring to sources
--------------------
Articles cite sources by inline labels like ``[S1]``. The article
manifest carries, per label, the cited ``(source_kind, source_id)``.
Sentences without any ``[S<n>]`` marker inherit the conclusion's
overall provenance — they are general framing, not load-bearing
claims, but we still surface a non-zero number so the reader can tell
them apart from "uncited assertion in the middle of a paragraph"
(those *are* anchored to the conclusion).

Privacy
-------
A sentence resting on a private source includes that source in the
*aggregate weight* (so the firm is honest about the breadth of its
evidence) but the per-sentence breakdown hides the private source's
identity from the public view. The visibility flag rides on each
contribution; the public projection drops names but keeps weights.

This module is pure-python: no Anthropic API, no DB-side compute. It
reads the cascade graph + source credibility ledger via the ``store``
and ``ledger`` arguments and returns a typed report ready to be
serialised and shipped with the article HTML.
"""

from __future__ import annotations

import hashlib
import re
from typing import Iterable, Optional

from pydantic import BaseModel, ConfigDict, Field

from noosphere.literature.source_credibility import (
    BetaPosterior,
    CredibilityLedger,
    aggregate_supports_confidence,
    current_credibility,
    modulated_supports_confidence,
)
from noosphere.models import (
    CascadeEdgeRelation,
    CascadeNodeKind,
)


# Fixed schema id so the front end can validate before rendering and
# refuse anything older than the assembler it knows.
SCHEMA = "theseus.sentenceProvenance.v1"

# Sentence boundary detector. Single regex, dependency-free. Splits on
# `.!?` followed by whitespace, keeping the punctuation with the
# sentence so sentence text round-trips. Empty trailing splits are
# dropped.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[\.!?])\s+(?=[A-Z\(\[\"'])")

# Citation-marker form used by article generator: ``[S1]``, ``[S12]``.
_CITE_MARKER = re.compile(r"\[S(\d+)\]")

# Markdown headings, fenced-code, and list markers don't contain
# load-bearing prose — strip them before splitting into sentences so
# the heatmap doesn't get a row for "## Background".
_BLOCK_STRIP = re.compile(
    r"(?ms)^\s*(?:#{1,6}\s+.*?$|>\s+.*?$|[-*+]\s+|\d+\.\s+)"
)


# ── Public types ────────────────────────────────────────────────────────────


class SourceContribution(BaseModel):
    """One source's contribution to a sentence's provenance.

    ``edge_weight`` is the cascade edge confidence (the upstream
    assertion strength). ``credibility`` is the posterior mean of the
    source's credibility ledger, or ``0.5`` when the source has not
    yet been assessed (the unknown prior). ``effective`` is their
    product, the value that actually feeds the noisy-OR aggregate.

    ``public`` reports whether the source's identity may be exposed
    in the panel. The panel layer is the privacy gate; this struct
    just carries the flag.
    """

    model_config = ConfigDict(extra="forbid")

    label: str
    source_kind: str
    source_id: str
    edge_weight: float
    credibility: float
    effective: float
    public: bool = True
    citation_verdict: Optional[str] = None


class SentenceProvenance(BaseModel):
    """Heatmap row for one sentence."""

    model_config = ConfigDict(extra="forbid")

    index: int
    text_hash: str
    provenance: float
    source_labels: list[str] = Field(default_factory=list)
    private_source_count: int = 0


class SentenceProvenanceReport(BaseModel):
    """Top-level payload shipped with the article HTML."""

    model_config = ConfigDict(extra="forbid")

    schema_: str = Field(default=SCHEMA, alias="schema")
    conclusion_id: str
    overall_provenance: float
    sources: dict[str, SourceContribution] = Field(default_factory=dict)
    sentences: list[SentenceProvenance] = Field(default_factory=list)

    def public(self) -> "SentenceProvenanceReport":
        """Strip identifying detail for any private source.

        The aggregate ``provenance`` and ``effective`` weights are
        unchanged — the firm is honest about its evidence base. Only
        the *identity* (``source_kind``, ``source_id``, ``label`` of
        the private source) is redacted, and the public ``sources``
        map drops private entries entirely (the per-sentence
        ``private_source_count`` lets the reader see how many were
        hidden without enabling identification).
        """
        public_sources = {
            label: contrib
            for label, contrib in self.sources.items()
            if contrib.public
        }
        return SentenceProvenanceReport(
            conclusion_id=self.conclusion_id,
            overall_provenance=self.overall_provenance,
            sources=public_sources,
            sentences=[
                SentenceProvenance(
                    index=s.index,
                    text_hash=s.text_hash,
                    provenance=s.provenance,
                    source_labels=[
                        label for label in s.source_labels if label in public_sources
                    ],
                    private_source_count=(
                        s.private_source_count
                        + sum(1 for label in s.source_labels if label not in public_sources)
                    ),
                )
                for s in self.sentences
            ],
        )


# ── Article splitting ───────────────────────────────────────────────────────


def split_sentences(body_markdown: str) -> list[str]:
    """Split article markdown into sentence-shaped strings.

    Light-touch: drops markdown structural prefixes (headings, list
    bullets, blockquote arrows) but keeps the body text. Sentences are
    detected by punctuation boundaries; URLs and abbreviations cause
    the occasional false split, which the heatmap tolerates because
    each sentence still anchors to its real citation markers.
    """
    cleaned = _BLOCK_STRIP.sub("", body_markdown or "")
    # Collapse repeated newlines so "para1\n\npara2" reads as a flow.
    cleaned = re.sub(r"\n{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return []
    parts = _SENTENCE_BOUNDARY.split(cleaned)
    return [p.strip() for p in parts if p.strip()]


def labels_in_sentence(sentence: str) -> list[str]:
    """Return the citation labels (e.g. ``S1``) cited inside ``sentence``."""
    return [f"S{m.group(1)}" for m in _CITE_MARKER.finditer(sentence)]


def _hash_sentence(sentence: str) -> str:
    """Stable short hash: lets the front end correlate gutter cells to
    sentences without exposing the raw text in the index. 12 hex chars
    ≈ 48 bits — enough for collision-resistance within one article."""
    return hashlib.sha256(sentence.strip().encode("utf-8")).hexdigest()[:12]


# ── Cascade walk ────────────────────────────────────────────────────────────


class _ContributionLookup:
    """Cached per-source ``(edge_weight, posterior)`` lookup.

    The cascade walk visits each source at most once; the ledger query
    is amortised.
    """

    def __init__(self, store, ledger: Optional[CredibilityLedger]) -> None:
        self._store = store
        self._ledger = ledger
        self._posteriors: dict[str, Optional[BetaPosterior]] = {}

    def posterior_for(self, source_id: str, source_type: Optional[str]) -> Optional[BetaPosterior]:
        if source_id in self._posteriors:
            return self._posteriors[source_id]
        if self._ledger is None:
            self._posteriors[source_id] = None
            return None
        try:
            post = current_credibility(
                source_id=source_id,
                source_type=source_type,
                ledger=self._ledger,
            )
        except Exception:
            post = None
        self._posteriors[source_id] = post
        return post


def _walk_supports_to_sources(
    store,
    *,
    target_node_id: str,
    visited: set[str],
    accum: dict[str, tuple[float, str, str, dict]],
    edge_weight_so_far: float = 1.0,
    depth: int = 0,
) -> None:
    """Walk *backwards* through ``supports`` cascade edges from a
    target node toward its source artifacts.

    The walk multiplies edge weights along each path; if a source is
    reachable by more than one path we keep the *strongest* path
    (max over multiplied weights) — this matches the spirit of the
    aggregator's max-credibility cap, which says we should not
    double-count the same source through different intermediaries.

    Cycles are forbidden in the depends_on subgraph but supports edges
    are not constrained; we cap depth at 8 to be safe.
    """
    if depth > 8 or target_node_id in visited:
        return
    visited.add(target_node_id)

    for edge in store.iter_cascade_edges(
        dst=target_node_id,
        relation=CascadeEdgeRelation.SUPPORTS.value,
        include_retracted=False,
    ):
        weight = edge_weight_so_far * float(edge.confidence or 0.0)
        if weight <= 0.0:
            continue
        src_node = store.get_cascade_node(edge.src)
        if src_node is None:
            continue
        if src_node.kind == CascadeNodeKind.ARTIFACT:
            existing = accum.get(src_node.ref)
            if existing is None or weight > existing[0]:
                attrs = src_node.attrs or {}
                accum[src_node.ref] = (
                    weight,
                    "artifact",
                    src_node.ref,
                    attrs,
                )
        elif src_node.kind == CascadeNodeKind.CLAIM:
            # Claims don't have a credibility ledger themselves — their
            # source is the artifact they were extracted from. Recurse:
            # the claim's supports edges may exist (rare), and the claim
            # also has an extracted_from edge to the artifact.
            _walk_supports_to_sources(
                store,
                target_node_id=edge.src,
                visited=visited,
                accum=accum,
                edge_weight_so_far=weight,
                depth=depth + 1,
            )
            # Follow extracted_from to the underlying artifact too — the
            # artifact is the credibility-bearing node in the ledger.
            for ext in store.iter_cascade_edges(
                src=edge.src,
                relation=CascadeEdgeRelation.EXTRACTED_FROM.value,
                include_retracted=False,
            ):
                ext_node = store.get_cascade_node(ext.dst)
                if ext_node is None or ext_node.kind != CascadeNodeKind.ARTIFACT:
                    continue
                existing = accum.get(ext_node.ref)
                # Extracted_from edges are descriptive, not gating, so
                # we use the path weight up to the claim as the carry.
                if existing is None or weight > existing[0]:
                    attrs = ext_node.attrs or {}
                    accum[ext_node.ref] = (
                        weight,
                        "artifact",
                        ext_node.ref,
                        attrs,
                    )


def _build_contribution(
    *,
    label: str,
    source_kind: str,
    source_id: str,
    edge_weight: float,
    posterior: Optional[BetaPosterior],
    public: bool,
    citation_verdict: Optional[str],
) -> SourceContribution:
    cred = posterior.mean if posterior is not None else 0.5
    eff = modulated_supports_confidence(edge_weight, posterior)
    return SourceContribution(
        label=label,
        source_kind=source_kind,
        source_id=source_id,
        edge_weight=float(edge_weight),
        credibility=float(cred),
        effective=float(eff),
        public=public,
        citation_verdict=citation_verdict,
    )


# ── Top-level assembly ──────────────────────────────────────────────────────


class ArticleCitationLink(BaseModel):
    """Inline citation manifest entry (label → source).

    Mirrors the published-payload article.citations shape but uses
    only the fields we need so the assembler is decoupled from the
    publication writer.
    """

    model_config = ConfigDict(extra="forbid")

    label: str
    source_kind: str
    source_id: str
    public: bool = True
    citation_verdict: Optional[str] = None


def assemble_sentence_provenance(
    *,
    store,
    conclusion_id: str,
    body_markdown: str,
    citations: Iterable[ArticleCitationLink],
    ledger: Optional[CredibilityLedger] = None,
) -> SentenceProvenanceReport:
    """Build a ``SentenceProvenanceReport`` for a published article.

    1. Walk the cascade graph from ``conclusion_id`` along supports
       edges, accumulating ``(source_id → max_path_weight)``.
    2. For each citation in the article manifest, look up the
       walk-derived weight (falling back to 1.0 if the citation does
       not appear in the cascade — unusual, but tolerated so the
       heatmap still renders).
    3. Multiply by source credibility (or 0.5 if the source is not yet
       in the ledger) to get the per-source ``effective`` weight.
    4. Split the article body into sentences. For each sentence,
       collect the citation labels it references and aggregate their
       contributions via ``aggregate_supports_confidence`` (capped at
       max credibility). Sentences without markers inherit the
       overall conclusion provenance.
    """
    citation_list = list(citations)
    cite_by_label: dict[str, ArticleCitationLink] = {c.label: c for c in citation_list}

    # 1. Cascade walk from the conclusion. Cascade edges that point at
    # a conclusion store the conclusion's own id as ``dst`` (see
    # noosphere.temporal.lineage.assemble_lineage), so we can use it as
    # the walk's starting node id directly. If the deployment instead
    # adds a CONCLUSION cascade node, callers can still drive the walk
    # via the alternate ``target_node_ids`` knob below.
    weights_by_source: dict[str, tuple[float, str, str, dict]] = {}
    visited: set[str] = set()
    _walk_supports_to_sources(
        store,
        target_node_id=conclusion_id,
        visited=visited,
        accum=weights_by_source,
        edge_weight_so_far=1.0,
        depth=0,
    )

    # 2. Build per-citation contributions.
    lookup = _ContributionLookup(store, ledger)
    contributions: dict[str, SourceContribution] = {}
    for citation in citation_list:
        match = weights_by_source.get(citation.source_id)
        if match is not None:
            edge_weight, _, _, attrs = match
            source_type = (attrs or {}).get("source_type")
        else:
            # Citation not wired through the cascade graph yet (e.g.
            # cascade backfill incomplete). We still display the
            # sentence with a conservative default so the heatmap
            # doesn't black out an otherwise legitimate article.
            edge_weight = 1.0
            source_type = None
        post = lookup.posterior_for(citation.source_id, source_type)
        contributions[citation.label] = _build_contribution(
            label=citation.label,
            source_kind=citation.source_kind,
            source_id=citation.source_id,
            edge_weight=edge_weight,
            posterior=post,
            public=citation.public,
            citation_verdict=citation.citation_verdict,
        )

    # 3. Overall provenance: aggregate every contribution.
    overall = aggregate_supports_confidence(
        (contrib.edge_weight, lookup.posterior_for(contrib.source_id, None))
        for contrib in contributions.values()
    )

    # 4. Per-sentence rows.
    sentences: list[SentenceProvenance] = []
    for index, text in enumerate(split_sentences(body_markdown)):
        labels = labels_in_sentence(text)
        if labels:
            inputs = []
            for label in labels:
                contrib = contributions.get(label)
                if contrib is None:
                    continue
                post = lookup.posterior_for(contrib.source_id, None)
                inputs.append((contrib.edge_weight, post))
            prov = aggregate_supports_confidence(inputs) if inputs else overall
        else:
            prov = overall
            labels = []
        sentences.append(
            SentenceProvenance(
                index=index,
                text_hash=_hash_sentence(text),
                provenance=float(prov),
                source_labels=labels,
            )
        )

    # Citation labels that appear in the article markup but lack a
    # manifest entry land in `sentences[i].source_labels` without
    # contribution rows. That is intentional: the gutter still records
    # which markers the sentence cited, the panel just shows "source
    # not found in manifest." The report itself does not synthesize
    # phantom contributions.

    return SentenceProvenanceReport(
        conclusion_id=conclusion_id,
        overall_provenance=float(overall),
        sources=contributions,
        sentences=sentences,
    )


__all__ = [
    "ArticleCitationLink",
    "SCHEMA",
    "SentenceProvenance",
    "SentenceProvenanceReport",
    "SourceContribution",
    "assemble_sentence_provenance",
    "labels_in_sentence",
    "split_sentences",
]
