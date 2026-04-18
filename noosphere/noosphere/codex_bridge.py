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
    dry_run: bool
    mode: str  # "naive" | "llm"


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
                dry_run=True,
                mode=mode,
            )

        # ── Insert conclusions ───────────────────────────────────────────
        now = datetime.now(timezone.utc)
        written = 0
        for idx, claim in enumerate(claims):
            claim_text = claim.text.strip()
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
                    f"Extracted from upload: {row['title'] or row['originalName']}",
                    json.dumps([]),
                    json.dumps([]),
                    json.dumps([]),
                    0.5,
                    claim.claim_type,
                    now,
                ),
            )
            written += cur.rowcount  # 1 on insert, 0 on conflict

        # ── Update upload row ────────────────────────────────────────────
        cur.execute(
            '''UPDATE "Upload"
               SET status = %s, "claimsCount" = %s, "errorMessage" = NULL
               WHERE id = %s''',
            ("ingested", written, upload_id),
        )

        # ── Audit event ──────────────────────────────────────────────────
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
                f"Noosphere {mode} extraction produced {written} conclusions",
                now,
            ),
        )

        conn.commit()
        return IngestFromCodexResult(
            upload_id=upload_id,
            title=row["title"] or row["originalName"] or upload_id,
            num_claims_extracted=len(claims),
            num_conclusions_written=written,
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
                    f"Local ingest-from-codex failed: {sys.exc_info()[1]}"[:400],
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
