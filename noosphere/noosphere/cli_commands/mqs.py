"""CLI commands for the Methodology Quality Score (MQS) subsystem.

Mirrors the structure of the existing methodology backfill: open a Codex DB
connection, scan conclusions that are missing an MQS, score each idempotently
(using a deterministic stub judge unless an LLM has been configured by the
caller), and persist `MethodologyQualityScore` rows.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

import click

from noosphere.evaluation.mqs import (
    MethodologyProfileSummary,
    MqsInput,
    MqsJudge,
    StubMqsJudge,
    evidence_payload_json,
    score_conclusion,
)


@click.group("mqs")
def cli() -> None:
    """Methodology Quality Score: score conclusions against the five
    working criteria from THE_META_METHOD.md."""


def _open_codex():
    from noosphere.codex_bridge import (
        REAL_DICT_CURSOR,
        _open_codex_connection,
        _resolve_codex_db_url,
    )

    url = _resolve_codex_db_url(None)
    conn = _open_codex_connection(url)
    return conn, REAL_DICT_CURSOR


def _conclusions_missing_mqs(cur, *, organization_id: Optional[str], limit: int):
    cur.execute(
        '''SELECT c.id, c."organizationId", c.text, c.rationale, c."topicHint",
                  c."dissentClaimIds"
             FROM "Conclusion" c
             LEFT JOIN "MethodologyQualityScore" m
                    ON m."conclusionId" = c.id
            WHERE m."conclusionId" IS NULL
              AND (%s IS NULL OR c."organizationId" = %s)
            ORDER BY c."createdAt" ASC
            LIMIT %s''',
        (organization_id, organization_id, int(limit)),
    )
    return list(cur.fetchall())


def _profiles_for_conclusion(cur, *, organization_id: str, conclusion_id: str):
    cur.execute(
        '''SELECT mp."patternType", mp.title, mp.summary,
                  mp."reasoningMoves", mp."transferTargets",
                  mp.assumptions, mp."failureModes", mp.confidence
             FROM "MethodologyProfile" mp
             LEFT JOIN "ConclusionSource" cs ON cs."uploadId" = mp."uploadId"
            WHERE mp."organizationId" = %s
              AND (mp."conclusionId" = %s OR cs."conclusionId" = %s)
            ORDER BY mp.confidence DESC
            LIMIT 8''',
        (organization_id, conclusion_id, conclusion_id),
    )
    profiles: list[MethodologyProfileSummary] = []
    for row in cur.fetchall():
        profiles.append(
            MethodologyProfileSummary(
                pattern_type=row.get("patternType") or "",
                title=row.get("title") or "",
                summary=row.get("summary") or "",
                reasoning_moves=_as_list(row.get("reasoningMoves")),
                transfer_targets=_as_list(row.get("transferTargets")),
                assumptions=_as_list(row.get("assumptions")),
                failure_modes=_as_list(row.get("failureModes")),
                confidence=float(row.get("confidence") or 0.5),
            )
        )
    return profiles


def _forecast_count_for_conclusion(cur, *, conclusion_id: str) -> int:
    try:
        cur.execute(
            '''SELECT COUNT(*) AS n FROM "ForecastPrediction"
                WHERE "conclusionId" = %s''',
            (conclusion_id,),
        )
        row = cur.fetchone()
        return int(row.get("n", 0) if isinstance(row, dict) else (row[0] if row else 0))
    except Exception:
        # Older databases may not expose conclusionId on ForecastPrediction.
        return 0


def _as_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw if x is not None]
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except Exception:
            return []
        if isinstance(value, list):
            return [str(x) for x in value if x is not None]
    return []


def _dissent_count(raw: Any) -> int:
    return len(_as_list(raw))


def _upsert_mqs_row(
    cur,
    *,
    organization_id: str,
    conclusion_id: str,
    score,
    now: datetime,
) -> None:
    cur.execute(
        '''INSERT INTO "MethodologyQualityScore"
            (id, "organizationId", "conclusionId",
             progressivity, severity, "aimMethodFit",
             compressibility, "domainSensitivity", composite,
             evidence, "modelName", "promptVersion",
             "scoredAt", "createdAt", "updatedAt")
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
           ON CONFLICT ("conclusionId") DO UPDATE SET
             progressivity = EXCLUDED.progressivity,
             severity = EXCLUDED.severity,
             "aimMethodFit" = EXCLUDED."aimMethodFit",
             compressibility = EXCLUDED.compressibility,
             "domainSensitivity" = EXCLUDED."domainSensitivity",
             composite = EXCLUDED.composite,
             evidence = EXCLUDED.evidence,
             "modelName" = EXCLUDED."modelName",
             "promptVersion" = EXCLUDED."promptVersion",
             "scoredAt" = EXCLUDED."scoredAt",
             "updatedAt" = EXCLUDED."updatedAt"''',
        (
            "mqs_" + uuid.uuid4().hex[:24],
            organization_id,
            conclusion_id,
            float(score.progressivity.score),
            float(score.severity.score),
            float(score.aim_method_fit.score),
            float(score.compressibility.score),
            float(score.domain_sensitivity.score),
            float(score.composite),
            evidence_payload_json(score),
            score.model_name,
            score.prompt_version,
            now,
            now,
            now,
        ),
    )


@cli.command("backfill")
@click.option(
    "--organization-slug",
    type=str,
    default=None,
    help="Restrict to a single organization (default: all orgs).",
)
@click.option(
    "--limit",
    type=int,
    default=500,
    help="Maximum conclusions to scan in this run.",
)
@click.option(
    "--dry-run/--write",
    default=True,
    help="Default is dry-run. Pass --write to persist MQS rows.",
)
@click.option(
    "--judge",
    "judge_name",
    type=click.Choice(["stub"]),
    default="stub",
    help="LLM judge to use. The 'stub' judge is deterministic and is the only "
    "judge available from the CLI; production code should pass an LLM-backed "
    "MqsJudge to score_conclusion().",
)
def backfill(
    organization_slug: Optional[str],
    limit: int,
    dry_run: bool,
    judge_name: str,
) -> None:
    """Score every Conclusion that does not yet have an MQS, idempotently.

    Re-running this command on the same DB is safe: rows are upserted on the
    conclusionId unique constraint."""
    conn, real_dict_cursor = _open_codex()
    try:
        cur = conn.cursor(cursor_factory=real_dict_cursor)
        organization_id: Optional[str] = None
        if organization_slug:
            cur.execute(
                'SELECT id FROM "Organization" WHERE slug = %s',
                (organization_slug,),
            )
            row = cur.fetchone()
            if not row:
                raise click.ClickException(
                    f"Organization slug not found: {organization_slug}"
                )
            organization_id = row["id"] if isinstance(row, dict) else row[0]

        rows = _conclusions_missing_mqs(
            cur, organization_id=organization_id, limit=limit
        )
        judge: MqsJudge = StubMqsJudge()
        now = datetime.now(timezone.utc)

        scored = 0
        for c in rows:
            cid = c["id"]
            org_id = c["organizationId"]
            profiles = _profiles_for_conclusion(
                cur, organization_id=org_id, conclusion_id=cid
            )
            if not profiles:
                # No methodology profile attached → nothing to score.
                continue
            forecast_count = _forecast_count_for_conclusion(cur, conclusion_id=cid)
            score = score_conclusion(
                MqsInput(
                    conclusion_id=cid,
                    conclusion_text=c.get("text") or "",
                    rationale=c.get("rationale") or "",
                    topic_hint=c.get("topicHint") or "",
                    profiles=profiles,
                    forecast_count=forecast_count,
                    has_check_back_date=False,
                    dissent_claim_count=_dissent_count(c.get("dissentClaimIds")),
                ),
                judge=judge,
                model_name=judge_name,
            )
            scored += 1
            if not dry_run:
                _upsert_mqs_row(
                    cur,
                    organization_id=org_id,
                    conclusion_id=cid,
                    score=score,
                    now=now,
                )

        if dry_run:
            conn.rollback()
        else:
            conn.commit()

        click.echo(
            json.dumps(
                {
                    "dry_run": dry_run,
                    "judge": judge_name,
                    "scanned": len(rows),
                    "scored": scored,
                },
                indent=2,
            )
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@cli.command("show")
@click.argument("conclusion_id")
def show(conclusion_id: str) -> None:
    """Print the MQS row for one conclusion."""
    conn, real_dict_cursor = _open_codex()
    try:
        cur = conn.cursor(cursor_factory=real_dict_cursor)
        cur.execute(
            '''SELECT * FROM "MethodologyQualityScore" WHERE "conclusionId" = %s''',
            (conclusion_id,),
        )
        row = cur.fetchone()
        if not row:
            raise click.ClickException(f"No MQS for conclusion {conclusion_id}")
        click.echo(json.dumps(dict(row), indent=2, default=str))
    finally:
        conn.close()
