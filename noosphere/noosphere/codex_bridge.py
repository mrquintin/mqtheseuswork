"""
Process Theseus Codex uploads locally.

Story
-----
The Codex web app (on Vercel) accepts file uploads into its Postgres
database but cannot run the Noosphere Python pipeline in that runtime —
Vercel's serverless Node has no Python interpreter. Uploads land as
``queued_offline`` with their ``textContent`` sitting in the DB until
someone runs this command on a machine that DOES have Noosphere.

What it does
------------
Given an Upload id, this module:

1. Connects to the Codex's Postgres (the shared Supabase instance — same
   DB, different tables than Noosphere would normally write to).
2. Reads the ``Upload`` row, pulls ``textContent``.
3. Extracts atomic claims from the text. Two extraction modes:
     - default / naive: rule-based sentence splitter that keeps only
       assertoric-looking sentences (filters questions, fragments, mere
       listings). Zero dependencies beyond the standard library, works
       without an LLM API key.
     - ``--with-llm``: delegates to the registered ``extract_claims``
       method (the Noosphere LLM pipeline). Higher quality, requires
       ``ANTHROPIC_API_KEY`` or ``OPENAI_API_KEY`` via noosphere.config.
4. Writes each extracted claim back into the Codex's ``Conclusion``
   table (tier=``open``, confidence=0.5) so it appears in the Codex web
   UI immediately.
5. Updates the Upload row to ``status='ingested'`` and sets
   ``claimsCount`` so the dashboard counters reflect the work.
6. Writes an ``AuditEvent`` row for traceability.

Why write to the Codex schema directly instead of Noosphere's own
-----------------------------------------------------------------
The goal of this command is "user uploaded a file, user sees something
in the Codex UI after running Noosphere locally". Writing to Noosphere's
separate tables would require the Codex UI to also query those tables
(the existing Python-spawn bridges do this, but they don't work on
Vercel either). Writing directly to the Codex's ``Conclusion`` table
gives the end-to-end "I uploaded, I can see analysis" flow without any
additional infrastructure. Full Noosphere-side artifact/chunk/claim
storage can be added later via ``--also-write-noosphere``.
"""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

try:
    import psycopg2
    import psycopg2.extras
except ImportError as e:  # pragma: no cover
    raise RuntimeError(
        "psycopg2 is required for the Codex bridge. "
        "Install with: pip install psycopg2-binary"
    ) from e


# ─────────────────────────────────────────────────────────────────────────────
# Postgres-safe sanitization.
#
# Postgres's UTF-8 enforcement rejects strings containing the NUL
# byte (``\u0000``) with "invalid byte sequence for encoding "UTF8":
# 0x00". PDF extraction, DOCX extraction, and even LLM output
# occasionally produce them. Every string that's about to be inserted
# into the Codex DB flows through ``_db_safe`` first so one bad
# byte doesn't nuke the whole ingest.
#
# We also strip other C0 control chars (except tab/newline/CR) and
# lone UTF-16 surrogate halves, which behave the same way on some
# server collations.
# ─────────────────────────────────────────────────────────────────────────────

# C0 controls minus \t (\x09), \n (\x0a), \r (\x0d). Also nuke BOM.
_DB_UNSAFE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufeff]")
_DB_SURROGATE = re.compile(r"[\ud800-\udfff]")


def _db_safe(s: Optional[str], *, cap: Optional[int] = None) -> str:
    """Scrub for Postgres and optionally cap length.

    ``None`` / non-string inputs return ``""`` so callers can unconditionally
    pass field values without null-checking first.
    """
    if s is None:
        return ""
    text = str(s)
    text = _DB_UNSAFE.sub("", text)
    text = _DB_SURROGATE.sub("", text)
    if cap is not None and len(text) > cap:
        text = text[:cap]
    return text


# ─────────────────────────────────────────────────────────────────────────────
# Naive claim extraction — works without an LLM. Conservative: keeps only
# sentences that look like first-person / declarative assertions, filters
# questions and fragments. Good enough for a first-pass Codex display.
# ─────────────────────────────────────────────────────────────────────────────


# Sentence-level tokens ending with a period / exclamation / line break.
# Non-greedy so we don't over-fuse sentences across paragraph breaks.
_SENT_RE = re.compile(r"[^.!?\n]+[.!?]+|[^.!?\n]+(?=\n|$)", re.MULTILINE)

# Heuristic filters for sentences we SHOULDN'T promote to claims.
_QUESTION_RE = re.compile(r"\?\s*$")
_LIST_BULLET_RE = re.compile(r"^\s*[-*•\d]+[\.\)]?\s+")
_URL_RE = re.compile(r"https?://|www\.")
_HEADER_RE = re.compile(r"^#+\s|^={3,}\s*$|^-{3,}\s*$")


@dataclass
class NaiveClaim:
    text: str
    claim_type: str = "empirical"  # conservative default


def naive_extract_claims(text: str, *, max_claims: int = 40) -> list[NaiveClaim]:
    """
    Sentence-split a blob of text and keep only sentences that look like
    substantive claims:
      * length ≥ 40 chars (filters "Yes.", "Ok.", lone bullets)
      * length ≤ 400 chars (filters run-on paragraphs that aren't atomic)
      * not a question (``?`` at end)
      * not a list bullet / markdown header
      * contains at least one verb-like word (``is|are|was|were|should|must|can|may|will``)
        OR a contextual connector (``because|therefore|given|since``)

    Returns at most ``max_claims`` so a 50-page transcript doesn't blow
    up the Codex with thousands of rows.
    """
    out: list[NaiveClaim] = []
    cleaned = _HEADER_RE.sub("", text)
    # Normalise whitespace so sentence splitting doesn't fragment on line
    # wraps inside a paragraph. We preserve paragraph breaks (double-newline)
    # because they are a useful signal for separating assertions; we just
    # rejoin line wraps WITHIN a paragraph into spaces.
    cleaned = re.sub(r"(?<!\n)\n(?!\n)", " ", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    # Walk sentences.
    for match in _SENT_RE.finditer(cleaned):
        raw = match.group(0).strip()
        if not raw:
            continue
        if len(raw) < 40 or len(raw) > 400:
            continue
        if _QUESTION_RE.search(raw):
            continue
        if _LIST_BULLET_RE.match(raw):
            # Strip the bullet and re-check length.
            stripped = _LIST_BULLET_RE.sub("", raw).strip()
            if len(stripped) < 40 or len(stripped) > 400:
                continue
            raw = stripped
        if _URL_RE.search(raw):
            # Drop sentences that are mostly URLs — they're rarely claims.
            continue
        lower = raw.lower()
        has_verb = bool(
            re.search(
                r"\b(is|are|was|were|should|must|can|may|will|would|do|does|did|have|has|had|seems|appears|means|implies|suggests|shows|proves|causes|requires|matters)\b",
                lower,
            )
        )
        has_connector = bool(
            re.search(r"\b(because|therefore|thus|hence|since|given that)\b", lower)
        )
        if not (has_verb or has_connector):
            continue
        # Classify: rough taxonomy based on vocabulary.
        claim_type = "empirical"
        if re.search(r"\b(should|must|ought|right|wrong|better|worse|good|bad)\b", lower):
            claim_type = "normative"
        elif re.search(
            r"\b(method|framework|approach|process|procedure|methodology)\b", lower
        ):
            claim_type = "methodological"
        elif re.search(r"\b(will|won't|shall|going to|expect|predict)\b", lower):
            claim_type = "predictive"
        out.append(NaiveClaim(text=raw, claim_type=claim_type))
        if len(out) >= max_claims:
            break
    return out


# ─────────────────────────────────────────────────────────────────────────────
# LLM-backed extraction — uses Noosphere's registered ``extract_claims`` method.
# ─────────────────────────────────────────────────────────────────────────────


def llm_extract_claims(
    text: str,
    *,
    chunk_char_size: int = 3500,
    max_chunks: int = 10,
    upload_id: str = "upload",
) -> list[NaiveClaim]:
    """LLM-backed extraction via Noosphere's ``extract_claims`` method.

    Raises if the LLM is unconfigured — the caller is expected to have
    passed --with-llm deliberately.
    """
    from noosphere.methods.extract_claims import (
        ExtractClaimsInput,
        extract_claims,
    )

    # Chunk the text so no single LLM call blows past the context budget.
    # Paragraph splits preferred; fall back to hard-cut if a paragraph is
    # itself huge.
    raw_paras = re.split(r"\n\s*\n+", text)
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for p in raw_paras:
        if size + len(p) > chunk_char_size and buf:
            chunks.append("\n\n".join(buf))
            buf = []
            size = 0
        if len(p) > chunk_char_size:
            # Hard-split the monster paragraph.
            for i in range(0, len(p), chunk_char_size):
                chunks.append(p[i : i + chunk_char_size])
        else:
            buf.append(p)
            size += len(p) + 2
    if buf:
        chunks.append("\n\n".join(buf))

    chunks = chunks[:max_chunks]

    out: list[NaiveClaim] = []
    for i, chunk in enumerate(chunks):
        result = extract_claims(
            ExtractClaimsInput(
                chunk_text=chunk,
                chunk_id=f"{upload_id}_chunk_{i}",
                episode_id=upload_id,
                speaker_name="founder",
                speaker_role="founder",
            )
        )
        for c in result.claims:
            if c.text.strip():
                out.append(NaiveClaim(text=c.text.strip(), claim_type=c.claim_type))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Core pipeline — connects to Codex Postgres, reads upload, writes results.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class IngestFromCodexResult:
    upload_id: str
    title: str
    num_claims_extracted: int
    num_conclusions_written: int
    num_contradictions_written: int
    num_open_questions_written: int
    num_research_suggestions_written: int
    dry_run: bool
    mode: str  # "naive" | "llm"


# ─────────────────────────────────────────────────────────────────────────────
# Contradiction detection — naive (always runs) + LLM-augmented (optional).
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class DetectedContradiction:
    """A contradicting claim pair. `a_idx` / `b_idx` refer to indices in
    the claim list we just extracted; if one side is an existing firm
    Conclusion (cross-upload contradiction) we use `b_existing_id` instead
    of `b_idx`."""
    a_idx: int
    b_idx: int | None  # None when b is an existing firm Conclusion
    b_existing_id: str | None  # Conclusion.id when b is from the firm corpus
    severity: float   # 0..1
    narrative: str
    source: str       # "heuristic" | "llm"


_NEGATION_TOKENS = re.compile(
    r"\b(not|never|no|none|nothing|nobody|nowhere|n'?t|cannot|can'?t|won'?t|"
    r"shouldn'?t|wouldn'?t|couldn'?t|isn'?t|aren'?t|wasn'?t|weren'?t|"
    r"doesn'?t|didn'?t|don'?t|haven'?t|hasn'?t|hadn'?t)\b",
    flags=re.IGNORECASE,
)
_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "and", "or", "but", "if", "then", "of", "in", "on", "at", "to", "for",
    "by", "with", "from", "as", "that", "this", "these", "those", "it",
    "its", "we", "our", "you", "they", "them", "their", "i", "me", "my",
    "he", "she", "his", "her", "has", "have", "had", "do", "does", "did",
    "will", "would", "should", "could", "can", "may", "must", "ought",
    "so", "than", "such", "some", "any", "all", "every", "each", "both",
    "more", "most", "much", "many", "few",
}


def _content_tokens(text: str) -> set[str]:
    toks = re.findall(r"\b[a-z][a-z']+\b", text.lower())
    return {t for t in toks if t not in _STOPWORDS and len(t) >= 4}


def _has_negation(text: str) -> bool:
    return bool(_NEGATION_TOKENS.search(text))


def naive_detect_contradictions(
    claims: list[NaiveClaim],
) -> list[DetectedContradiction]:
    """
    Heuristic pairwise contradiction scan on the new claims. Flags pairs
    where:
      (1) their content vocabulary overlaps significantly (same subject), AND
      (2) exactly one contains a negation marker (opposite polarity).

    This catches the obvious "X should always …" vs "X should not …" case
    without needing an NLI model. Recall is modest; precision is decent
    enough that the flagged pairs are usually worth a human's attention.
    """
    out: list[DetectedContradiction] = []
    tok_sets = [_content_tokens(c.text) for c in claims]
    neg_flags = [_has_negation(c.text) for c in claims]
    for i in range(len(claims)):
        for j in range(i + 1, len(claims)):
            if neg_flags[i] == neg_flags[j]:
                continue  # both affirmative or both negative — no polarity flip
            if not tok_sets[i] or not tok_sets[j]:
                continue
            shared = tok_sets[i] & tok_sets[j]
            # Require meaningful overlap — otherwise it's just two unrelated
            # sentences that happen to have different polarity. A Jaccard
            # of 0.35 on content tokens is a useful middle ground.
            smaller = min(len(tok_sets[i]), len(tok_sets[j]))
            if smaller == 0 or (len(shared) / smaller) < 0.35:
                continue
            # Severity proxy: how much do they overlap? More overlap = more
            # directly contradictory.
            overlap_ratio = len(shared) / smaller
            severity = min(0.9, 0.4 + overlap_ratio * 0.5)
            out.append(
                DetectedContradiction(
                    a_idx=i,
                    b_idx=j,
                    b_existing_id=None,
                    severity=severity,
                    narrative=(
                        f"Heuristic: shared vocabulary {sorted(shared)[:6]} "
                        f"but opposite polarity."
                    ),
                    source="heuristic",
                )
            )
    return out


def llm_detect_contradictions_and_questions(
    claims: list[NaiveClaim],
    firm_conclusions: list[tuple[str, str]],  # (id, text) of existing firm claims
    *,
    upload_title: str,
) -> dict:
    """
    Single LLM call that does all three analysis tasks at once —
    contradictions, open questions, research suggestions. Putting them in
    one prompt is:
      (a) cheaper (single context load);
      (b) more coherent — the questions are generated in light of the
          contradictions the LLM just identified, instead of being
          independently invented.

    Returns a dict shaped like:
      {
        "contradictions": [{"a": int, "b": int, "severity": float, "narrative": str}],
        "cross_contradictions": [{"a": int, "existing_id": str, "severity": float, "narrative": str}],
        "open_questions": [{"summary": str, "unresolved_reason": str, "a": int, "b": int|None}],
        "research_suggestions": [{"title": str, "summary": str, "rationale": str}],
      }
    Missing keys are backfilled to empty lists so the caller never
    explodes on a partial response.

    Raises on LLM failure so the caller can decide whether to fall back
    to heuristic-only mode.
    """
    from noosphere.llm import llm_client_from_settings

    llm = llm_client_from_settings()

    new_lines = "\n".join(
        f"  [{i}] {c.text}" for i, c in enumerate(claims)
    )
    firm_lines = (
        "\n".join(f"  <{fid[:10]}> {txt[:240]}" for fid, txt in firm_conclusions[:40])
        if firm_conclusions
        else "  (none yet — this is the first upload for this firm.)"
    )

    system = (
        "You are an analyst helping a firm surface contradictions, open "
        "questions, and research directions from a newly uploaded document. "
        "Answer ONLY in JSON matching the schema below. Be conservative — "
        "only flag genuine contradictions, not mere topical overlap. Only "
        "propose questions a founder could actually research. Never "
        "fabricate evidence."
    )
    user = f"""New document: "{upload_title}"

CLAIMS extracted from this document (indices in brackets):
{new_lines}

FIRM'S EXISTING CONCLUSIONS (for cross-upload contradiction detection):
{firm_lines}

Return a single JSON object with these keys:
{{
  "contradictions": [
    {{"a": <idx>, "b": <idx>, "severity": <0..1>, "narrative": "<≤200 chars, why they conflict>"}}
  ],
  "cross_contradictions": [
    {{"a": <idx>, "existing_id": "<existing firm claim id prefix>", "severity": <0..1>, "narrative": "<≤200 chars>"}}
  ],
  "open_questions": [
    {{"summary": "<≤180 chars, a concrete question>", "unresolved_reason": "<why unresolved>", "a": <idx or null>, "b": <idx or null>}}
  ],
  "research_suggestions": [
    {{"title": "<short title>", "summary": "<one sentence>", "rationale": "<why this matters>"}}
  ]
}}

Rules:
- 0-5 contradictions, 0-3 cross_contradictions, 3-6 open_questions, 2-4 research_suggestions.
- If no real contradictions exist, return [] for that list. Do not pad.
- `a` and `b` must be valid indices into the CLAIMS list above.
- Output ONLY the JSON object, no prose."""

    raw = llm.complete(system=system, user=user, max_tokens=2500)
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise RuntimeError(f"LLM returned non-JSON: {raw[:200]}")
    payload = json.loads(m.group(0))
    return {
        "contradictions": payload.get("contradictions", []) or [],
        "cross_contradictions": payload.get("cross_contradictions", []) or [],
        "open_questions": payload.get("open_questions", []) or [],
        "research_suggestions": payload.get("research_suggestions", []) or [],
    }


def _resolve_codex_db_url(explicit: Optional[str]) -> str:
    if explicit:
        return explicit
    for env in (
        "THESEUS_CODEX_DATABASE_URL",
        "CODEX_DATABASE_URL",
        "DIRECT_URL",
        "DATABASE_URL",
    ):
        val = os.environ.get(env, "").strip()
        if val:
            return val
    raise RuntimeError(
        "No Codex Postgres URL found. Pass --codex-db-url, or export "
        "THESEUS_CODEX_DATABASE_URL / CODEX_DATABASE_URL / DIRECT_URL / "
        "DATABASE_URL. The Supabase DIRECT_URL (port 5432, not the 6543 "
        "pooler) is preferred — the pooler can strip advisory locks some "
        "ORMs rely on."
    )


def _short_cuid_like() -> str:
    """Simple unique id for Conclusion / AuditEvent rows. Prisma normally
    uses cuid() but the DB only enforces uniqueness, so a uuid4-derived
    id works fine and keeps this file Python-only (no cuid dep)."""
    return "c_" + uuid.uuid4().hex[:24]


def ingest_from_codex(
    upload_id: str,
    *,
    codex_db_url: Optional[str] = None,
    use_llm: bool = False,
    max_claims: int = 40,
    dry_run: bool = False,
    organization_slug_filter: Optional[str] = None,
) -> IngestFromCodexResult:
    """
    Read a Codex Upload, extract claims, write Conclusions back into the
    same DB. Returns a small result object so the CLI can print a summary.
    """
    url = _resolve_codex_db_url(codex_db_url)
    conn = psycopg2.connect(url)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # ── Fetch the upload ─────────────────────────────────────────────
        cur.execute(
            '''SELECT id, "organizationId", "founderId", title, "textContent",
                      status, "mimeType", "originalName"
               FROM "Upload" WHERE id = %s''',
            (upload_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(f"Upload {upload_id} not found in the Codex DB.")
        text = row["textContent"]
        if not text or not text.strip():
            raise RuntimeError(
                f"Upload {upload_id} has no textContent. "
                "Binary (audio/PDF) uploads aren't supported by this command yet "
                "— use the Codex's Supabase Storage flow + a separate transcript "
                "command when that's wired up."
            )

        # Optional sanity check on tenant if the caller passed a slug — protects
        # against running this against the wrong Codex tenant by mistake.
        if organization_slug_filter:
            cur.execute(
                'SELECT slug FROM "Organization" WHERE id = %s',
                (row["organizationId"],),
            )
            org = cur.fetchone()
            if not org or org["slug"] != organization_slug_filter:
                raise RuntimeError(
                    f"Upload {upload_id} belongs to org {org['slug'] if org else '?'}, "
                    f"not the expected slug '{organization_slug_filter}'."
                )

        # ── Mark processing (non-dry only) ───────────────────────────────
        if not dry_run:
            cur.execute(
                'UPDATE "Upload" SET status = %s WHERE id = %s',
                ("processing", upload_id),
            )
            conn.commit()

        # ── Extract claims ───────────────────────────────────────────────
        if use_llm:
            claims = llm_extract_claims(text, upload_id=upload_id, max_chunks=10)
            mode = "llm"
        else:
            claims = naive_extract_claims(text, max_claims=max_claims)
            mode = "naive"

        if dry_run:
            return IngestFromCodexResult(
                upload_id=upload_id,
                title=row["title"] or row["originalName"] or upload_id,
                num_claims_extracted=len(claims),
                num_conclusions_written=0,
                num_contradictions_written=0,
                num_open_questions_written=0,
                num_research_suggestions_written=0,
                dry_run=True,
                mode=mode,
            )

        # ── Insert conclusions ───────────────────────────────────────────
        # We also track a parallel list of (claim_index → conclusion_id)
        # so we can cite the right Conclusion rows from contradictions
        # and open questions below. Claims that are too short to insert
        # won't appear in this map (their index maps to None).
        now = datetime.now(timezone.utc)
        written = 0
        claim_idx_to_conclusion_id: list[str | None] = [None] * len(claims)
        # Pre-compute a sanitized source label we'll reuse in every row's
        # rationale/sessionLabel. Cap at 300 so a giant filename can't blow
        # the text column.
        source_label = _db_safe(
            row["title"] or row["originalName"] or upload_id,
            cap=300,
        )
        for idx, claim in enumerate(claims):
            claim_text = _db_safe(claim.text, cap=4_000).strip()
            if len(claim_text) < 20:
                continue
            cid = _short_cuid_like()
            noosphere_id = f"ing_{upload_id}_{idx}"
            cur.execute(
                '''INSERT INTO "Conclusion"
                   (id, "organizationId", "noosphereId", text, "confidenceTier",
                    rationale, "supportingPrincipleIds", "evidenceChainClaimIds",
                    "dissentClaimIds", confidence, "topicHint", "createdAt")
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT ("noosphereId") DO NOTHING''',
                (
                    cid,
                    row["organizationId"],
                    noosphere_id,
                    claim_text,
                    "open",
                    _db_safe(f"Extracted from upload: {source_label}", cap=500),
                    json.dumps([]),
                    json.dumps([]),
                    json.dumps([]),
                    0.5,
                    _db_safe(claim.claim_type, cap=64),
                    now,
                ),
            )
            if cur.rowcount == 1:
                written += 1
                claim_idx_to_conclusion_id[idx] = cid

        # ── Contradiction detection ─────────────────────────────────────
        # Always run the heuristic pass (cheap, no deps). If LLM is
        # available AND use_llm=True, do the combined contradictions +
        # questions + research pass for higher quality.
        contradictions_written = 0
        open_questions_written = 0
        research_suggestions_written = 0

        heuristic_pairs = naive_detect_contradictions(claims)

        llm_payload: dict | None = None
        llm_error: str | None = None
        if use_llm:
            try:
                # Pull up to 40 recent firm conclusions for cross-upload checking.
                cur.execute(
                    '''SELECT id, text FROM "Conclusion"
                       WHERE "organizationId" = %s
                         AND "noosphereId" NOT LIKE %s
                       ORDER BY "createdAt" DESC LIMIT 40''',
                    (row["organizationId"], f"ing_{upload_id}_%"),
                )
                firm_conclusions = [(r["id"], r["text"]) for r in cur.fetchall()]
                llm_payload = llm_detect_contradictions_and_questions(
                    claims,
                    firm_conclusions,
                    upload_title=row["title"] or row["originalName"] or upload_id,
                )
            except Exception as exc:
                # LLM failure is non-fatal — we still have the heuristic
                # contradictions and the inserted Conclusions. Record the
                # reason so the caller can surface it in the process log.
                llm_error = f"{type(exc).__name__}: {exc}"

        # ── Write contradictions (both sources merged) ──────────────────
        # Heuristic pairs first.
        for pair in heuristic_pairs:
            a_cid = claim_idx_to_conclusion_id[pair.a_idx]
            b_cid = (
                claim_idx_to_conclusion_id[pair.b_idx]
                if pair.b_idx is not None
                else pair.b_existing_id
            )
            if not a_cid or not b_cid:
                continue
            cur.execute(
                '''INSERT INTO "Contradiction"
                   (id, "organizationId", "claimAId", "claimBId", severity,
                    "sixLayerJson", narrative, "createdAt")
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''',
                (
                    "x_" + uuid.uuid4().hex[:24],
                    row["organizationId"],
                    a_cid,
                    b_cid,
                    float(pair.severity),
                    json.dumps({"source": "heuristic"}),
                    _db_safe(pair.narrative, cap=2_000),
                    now,
                ),
            )
            contradictions_written += cur.rowcount

        # LLM contradictions (within-upload).
        if llm_payload:
            for item in llm_payload.get("contradictions", []):
                try:
                    a = int(item["a"])
                    b = int(item["b"])
                    sev = float(item.get("severity", 0.6))
                    narrative = str(item.get("narrative", ""))[:500]
                except (KeyError, ValueError, TypeError):
                    continue
                a_cid = claim_idx_to_conclusion_id[a] if 0 <= a < len(claims) else None
                b_cid = claim_idx_to_conclusion_id[b] if 0 <= b < len(claims) else None
                if not a_cid or not b_cid or a_cid == b_cid:
                    continue
                cur.execute(
                    '''INSERT INTO "Contradiction"
                       (id, "organizationId", "claimAId", "claimBId", severity,
                        "sixLayerJson", narrative, "createdAt")
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''',
                    (
                        "x_" + uuid.uuid4().hex[:24],
                        row["organizationId"],
                        a_cid,
                        b_cid,
                        sev,
                        json.dumps({"source": "llm"}),
                        _db_safe(narrative or "LLM flagged as contradictory", cap=2_000),
                        now,
                    ),
                )
                contradictions_written += cur.rowcount

            # Cross-upload contradictions (new claim vs existing firm claim).
            # The LLM returns a prefix like "abc1234…"; we match by prefix
            # against firm_conclusions' full ids.
            firm_id_lookup = {fid[:10]: fid for fid, _ in firm_conclusions}
            for item in llm_payload.get("cross_contradictions", []):
                try:
                    a = int(item["a"])
                    existing_prefix = str(item.get("existing_id", ""))[:10]
                    sev = float(item.get("severity", 0.6))
                    narrative = str(item.get("narrative", ""))[:500]
                except (KeyError, ValueError, TypeError):
                    continue
                a_cid = claim_idx_to_conclusion_id[a] if 0 <= a < len(claims) else None
                existing_id = firm_id_lookup.get(existing_prefix)
                if not a_cid or not existing_id or a_cid == existing_id:
                    continue
                cur.execute(
                    '''INSERT INTO "Contradiction"
                       (id, "organizationId", "claimAId", "claimBId", severity,
                        "sixLayerJson", narrative, "createdAt")
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''',
                    (
                        "x_" + uuid.uuid4().hex[:24],
                        row["organizationId"],
                        a_cid,
                        existing_id,
                        sev,
                        json.dumps({"source": "llm", "cross_upload": True}),
                        _db_safe(narrative or "LLM cross-upload contradiction", cap=2_000),
                        now,
                    ),
                )
                contradictions_written += cur.rowcount

        # ── Write open questions (LLM only) ─────────────────────────────
        if llm_payload:
            for item in llm_payload.get("open_questions", []):
                try:
                    summary = str(item.get("summary", "")).strip()[:500]
                    reason = str(item.get("unresolved_reason", "")).strip()[:500]
                except (KeyError, TypeError):
                    continue
                if not summary:
                    continue
                a = item.get("a")
                b = item.get("b")
                a_cid = (
                    claim_idx_to_conclusion_id[int(a)]
                    if isinstance(a, int) and 0 <= a < len(claims)
                    else None
                )
                b_cid = (
                    claim_idx_to_conclusion_id[int(b)]
                    if isinstance(b, int) and 0 <= b < len(claims)
                    else None
                )
                # OpenQuestion requires claimAId + claimBId NOT NULL; if the
                # LLM didn't cite any, anchor both to the first inserted
                # conclusion as a minimal placeholder so the row is valid.
                # A future schema migration could make these nullable.
                fallback = next(
                    (cid for cid in claim_idx_to_conclusion_id if cid is not None),
                    None,
                )
                a_cid = a_cid or fallback
                b_cid = b_cid or fallback
                if not a_cid or not b_cid:
                    continue
                cur.execute(
                    '''INSERT INTO "OpenQuestion"
                       (id, "organizationId", "noosphereId", summary,
                        "claimAId", "claimBId", "unresolvedReason",
                        "layerDisagreementSummary", "createdAt")
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                    (
                        "q_" + uuid.uuid4().hex[:24],
                        row["organizationId"],
                        f"oq_{upload_id}_{open_questions_written}",
                        _db_safe(summary, cap=2_000),
                        a_cid,
                        b_cid,
                        _db_safe(reason or "Surfaced during ingest LLM pass", cap=2_000),
                        "LLM-flagged",
                        now,
                    ),
                )
                open_questions_written += cur.rowcount

        # ── Write research suggestions (LLM only) ───────────────────────
        if llm_payload:
            for item in llm_payload.get("research_suggestions", []):
                try:
                    title = str(item.get("title", "")).strip()[:300]
                    summary = str(item.get("summary", "")).strip()[:1000]
                    rationale = str(item.get("rationale", "")).strip()[:1000]
                except (KeyError, TypeError):
                    continue
                if not title or not summary:
                    continue
                cur.execute(
                    '''INSERT INTO "ResearchSuggestion"
                       (id, "organizationId", "noosphereId", title, summary,
                        rationale, "readingUris", "sessionLabel",
                        "suggestedForFounderId", "createdAt")
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                    (
                        "rs_" + uuid.uuid4().hex[:24],
                        row["organizationId"],
                        f"rs_{upload_id}_{research_suggestions_written}",
                        _db_safe(title, cap=300),
                        _db_safe(summary, cap=2_000),
                        _db_safe(rationale or "LLM-generated during ingest", cap=2_000),
                        json.dumps([]),
                        source_label,
                        row["founderId"],
                        now,
                    ),
                )
                research_suggestions_written += cur.rowcount

        # ── Update upload row ────────────────────────────────────────────
        cur.execute(
            '''UPDATE "Upload"
               SET status = %s, "claimsCount" = %s, "errorMessage" = NULL
               WHERE id = %s''',
            ("ingested", written, upload_id),
        )

        # ── Audit event ──────────────────────────────────────────────────
        audit_detail = (
            f"Noosphere {mode} ingest · "
            f"{written} conclusions · "
            f"{contradictions_written} contradictions · "
            f"{open_questions_written} open questions · "
            f"{research_suggestions_written} research suggestions"
        )
        if llm_error:
            audit_detail += f" · LLM pass failed: {llm_error[:80]}"
        cur.execute(
            '''INSERT INTO "AuditEvent"
               (id, "organizationId", "founderId", "uploadId", action, detail, "createdAt")
               VALUES (%s, %s, %s, %s, %s, %s, %s)''',
            (
                "ae_" + uuid.uuid4().hex[:24],
                row["organizationId"],
                row["founderId"],
                upload_id,
                "ingest",
                _db_safe(audit_detail, cap=500),
                now,
            ),
        )

        conn.commit()
        return IngestFromCodexResult(
            upload_id=upload_id,
            title=row["title"] or row["originalName"] or upload_id,
            num_claims_extracted=len(claims),
            num_conclusions_written=written,
            num_contradictions_written=contradictions_written,
            num_open_questions_written=open_questions_written,
            num_research_suggestions_written=research_suggestions_written,
            dry_run=False,
            mode=mode,
        )
    except Exception:
        conn.rollback()
        # On unexpected failure, mark the upload as failed so the Codex
        # UI shows a clear red state rather than a stuck "processing".
        try:
            err = psycopg2.connect(url)
            ec = err.cursor()
            ec.execute(
                '''UPDATE "Upload"
                   SET status = %s, "errorMessage" = %s
                   WHERE id = %s''',
                (
                    "failed",
                    _db_safe(
                        f"Local ingest-from-codex failed: {sys.exc_info()[1]}",
                        cap=400,
                    ),
                    upload_id,
                ),
            )
            err.commit()
            err.close()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def list_queued_uploads(
    *, codex_db_url: Optional[str] = None, limit: int = 25
) -> list[dict]:
    """List uploads currently stuck in ``queued_offline`` / ``pending`` so
    the user can pick which one to process."""
    url = _resolve_codex_db_url(codex_db_url)
    conn = psycopg2.connect(url)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            '''SELECT id, title, "originalName", status, "mimeType",
                      "fileSize", "createdAt"
               FROM "Upload"
               WHERE status IN ('pending', 'queued_offline', 'processing')
                  OR status IS NULL
               ORDER BY "createdAt" DESC
               LIMIT %s''',
            (limit,),
        )
        return list(cur.fetchall())
    finally:
        conn.close()
