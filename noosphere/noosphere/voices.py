"""
Voice decomposition — track non-founder thinkers as first-class corpora and positions.

Positions are always scoped to ingested artifacts; never presented as historical ground truth.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from noosphere.claim_extractor import ClaimExtractor
from noosphere.coherence.aggregator import CoherenceAggregator
from noosphere.config import get_settings
from noosphere.ingest_artifacts import ingest_markdown, ingest_text
from noosphere.models import (
    Claim,
    ClaimOrigin,
    ClaimType,
    CoherenceVerdict,
    Conclusion,
    InputSourceType,
    RelativePositionEntry,
    RelativePositionMap,
    Speaker,
    VoiceProfile,
    voice_canonical_key,
)
from noosphere.observability import get_logger
from noosphere.store import Store

logger = get_logger(__name__)


def ensure_voice_profile(
    store: Store,
    display_name: str,
    *,
    traditions: list[str] | None = None,
    copyright_status: str = "",
) -> VoiceProfile:
    key = voice_canonical_key(display_name)
    existing = store.get_voice_by_key(key)
    if existing:
        return existing
    v = VoiceProfile(
        id=str(uuid.uuid4()),
        canonical_name=display_name.strip(),
        aliases=[],
        traditions=list(traditions or []),
        copyright_status=copyright_status or "unknown",
    )
    store.put_voice_profile(v)
    logger.info("voice_created", voice_id=v.id, key=key)
    return v


def register_voice_corpus_artifact(store: Store, voice: VoiceProfile, artifact_id: str) -> VoiceProfile:
    """Attach an artifact id to a Voice profile and persist (e.g. literature ingestion)."""
    v = _append_corpus(store, voice, artifact_id)
    store.put_voice_profile(v)
    return v


def _append_corpus(store: Store, voice: VoiceProfile, artifact_id: str) -> VoiceProfile:
    ids = list(voice.corpus_artifact_ids)
    if artifact_id not in ids:
        ids.append(artifact_id)
    return voice.model_copy(
        update={
            "corpus_artifact_ids": ids,
            "updated_at": datetime.now(timezone.utc),
        }
    )


def _stub_claims_from_chunk(
    chunk,
    *,
    voice: VoiceProfile,
    artifact_id: str,
) -> list[Claim]:
    """Deterministic fallback when LLM extraction is unavailable (tests / offline)."""
    parts = re.split(r"(?<=[.!?])\s+", chunk.text.strip())
    out: list[Claim] = []
    spk = Speaker(name=voice.canonical_name, role="voice")
    when = date.today()
    cursor_local = 0
    for p in parts:
        t = p.strip()
        if len(t) < 40:
            cursor_local += len(p) + 1
            continue
        cid = f"vc_{voice.id[:8]}_{chunk.id}_{cursor_local}_{uuid.uuid4().hex[:6]}"
        start = chunk.start_offset + cursor_local
        end = start + len(t)
        out.append(
            Claim(
                id=cid,
                text=t,
                speaker=spk,
                episode_id=f"voice:{voice.id}",
                episode_date=when,
                claim_type=ClaimType.METHODOLOGICAL,
                chunk_id=chunk.id,
                segment_context=chunk.text[:400],
                claim_origin=ClaimOrigin.VOICE,
                voice_id=voice.id,
                source_type=InputSourceType.EXTERNAL,
                source_id=artifact_id,
                source_span_start=start,
                source_span_end=end,
            )
        )
        cursor_local += len(p) + 1
    return out


def ingest_path_as_voice(
    store: Store,
    path: str | Path,
    voice_display_name: str,
    *,
    copyright_status: str = "",
    use_llm_extractor: bool = False,
    llm: Any | None = None,
) -> tuple[str, int]:
    """
    Ingest a text/markdown file as corpus for a Voice; persist claims with ``claim_origin=voice``.

    Returns ``(artifact_id, num_claims_written)``.
    """
    p = Path(path)
    voice = ensure_voice_profile(store, voice_display_name, copyright_status=copyright_status)
    if p.suffix.lower() in {".md", ".markdown"}:
        art = ingest_markdown(p, store)
    else:
        art = ingest_text(p, store)
    voice = _append_corpus(store, voice, art.id)
    store.put_voice_profile(voice)

    chunks = store.list_chunks_for_artifact(art.id)
    extractor: ClaimExtractor | None = None
    if use_llm_extractor and llm is not None:
        extractor = ClaimExtractor(llm=llm, store=store)
    n = 0
    for ch in chunks:
        claims: list[Claim]
        if extractor is not None:
            claims = extractor.extract(
                ch,
                speaker=Speaker(name=voice.canonical_name, role="voice"),
                episode_id=f"voice:{voice.id}",
                episode_date=date.today(),
                claim_origin=ClaimOrigin.VOICE,
            )
            patched: list[Claim] = []
            for c in claims:
                patched.append(
                    c.model_copy(
                        update={
                            "voice_id": voice.id,
                            "source_id": art.id,
                            "source_span_start": ch.start_offset,
                            "source_span_end": ch.end_offset,
                        }
                    )
                )
            claims = patched
        else:
            claims = _stub_claims_from_chunk(ch, voice=voice, artifact_id=art.id)
        for c in claims:
            store.put_claim(c)
            n += 1
    logger.info("voice_ingest_done", voice_id=voice.id, artifact_id=art.id, claims=n)
    return art.id, n


def compute_relative_position_map(
    store: Store,
    conclusion_id: str,
    aggregator: CoherenceAggregator,
) -> RelativePositionMap:
    """Cross-Voice coherence: firm conclusion anchor vs sample Voice claims."""
    con = store.get_conclusion(conclusion_id)
    if con is None:
        raise ValueError(f"Unknown conclusion {conclusion_id}")
    anchor = Claim(
        id=f"_firm_anchor_{conclusion_id}",
        text=con.text,
        speaker=Speaker(name="firm_conclusion", role="system"),
        episode_id=f"conclusion:{conclusion_id}",
        episode_date=date.today(),
        claim_type=ClaimType.METHODOLOGICAL,
        claim_origin=ClaimOrigin.SYSTEM,
    )
    entries: list[RelativePositionEntry] = []
    best_agree: tuple[float, str, str] = (0.0, "", "")
    best_opp: tuple[float, str, str] = (0.0, "", "")

    for voice in store.list_voice_profiles(limit=40):
        vclaims = store.list_claims_for_voice(voice.id, limit=6)
        if not vclaims:
            continue
        rep_ids: list[str] = []
        summary_bits: list[str] = []
        has_contra = False
        has_cohere = False
        contra_conf = 0.0
        cohere_conf = 0.0
        for vc in vclaims[:4]:
            res = aggregator.evaluate_pair(anchor, vc, store=store)
            fv = res.payload.final_verdict
            conf = float(res.payload.confidence)
            rep_ids.append(vc.id)
            summary_bits.append(f"{vc.text[:80]}… → {fv.value} ({conf:.2f})")
            if fv == CoherenceVerdict.CONTRADICT:
                has_contra = True
                contra_conf = max(contra_conf, conf)
            elif fv == CoherenceVerdict.COHERE:
                has_cohere = True
                cohere_conf = max(cohere_conf, conf)
        if has_contra:
            verdict, worst_conf = CoherenceVerdict.CONTRADICT.value, contra_conf
        elif has_cohere:
            verdict, worst_conf = CoherenceVerdict.COHERE.value, cohere_conf
        else:
            verdict, worst_conf = CoherenceVerdict.UNRESOLVED.value, 0.0
        entry = RelativePositionEntry(
            voice_id=voice.id,
            voice_name=voice.canonical_name,
            verdict_vs_firm=verdict,
            confidence=worst_conf,
            representative_voice_claim_ids=rep_ids[:6],
            summary=" | ".join(summary_bits[:3]),
        )
        entries.append(entry)
        if verdict == CoherenceVerdict.COHERE.value and worst_conf >= best_agree[0]:
            best_agree = (worst_conf, voice.id, voice.canonical_name)
        if verdict == CoherenceVerdict.CONTRADICT.value and worst_conf >= best_opp[0]:
            best_opp = (worst_conf, voice.id, voice.canonical_name)

    m = RelativePositionMap(
        conclusion_id=conclusion_id,
        closest_agreeing_voice_id=best_agree[1],
        closest_opposing_voice_id=best_opp[1],
        entries=entries,
    )
    store.put_relative_position_map(m)
    return m


def build_voice_context_for_adversarial(store: Store, _conclusion_text: str = "") -> str:
    """Prefer tracked Voice positions when generating synthetic objections (Prompt 01 hook)."""
    lines: list[str] = []
    for voice in store.list_voice_profiles(limit=20):
        claims = store.list_claims_for_voice(voice.id, limit=2)
        if not claims:
            continue
        snippets = "; ".join(c.text[:160].replace("\n", " ") for c in claims)
        lines.append(
            f"- {voice.canonical_name} (corpus n={len(voice.corpus_artifact_ids)}): {snippets}"
        )
        if len(lines) >= 8:
            break
    if not lines:
        return ""
    return "Tracked Voice positions (ingested corpus only):\n" + "\n".join(lines)


def voice_reading_gaps(store: Store) -> list[dict[str, str]]:
    """Voices with corpus but no firm citations — suggested reading targets."""
    gaps: list[dict[str, str]] = []
    for v in store.list_voice_profiles(limit=100):
        if not v.corpus_artifact_ids:
            continue
        cites = store.list_citations_for_voice(v.id)
        if not cites:
            gaps.append(
                {
                    "voice": v.canonical_name,
                    "voice_id": v.id,
                    "note": "Ingested corpus exists; firm artifacts do not yet cite this Voice.",
                }
            )
    return gaps[:40]
