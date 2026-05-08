"""CLI commands for the Method Registry subsystem."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

console = Console()


def _get_store():
    from noosphere.cli import get_orchestrator
    return get_orchestrator(None).store


def _render(obj, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(obj, indent=2, default=str))


@click.group("methods")
def cli() -> None:
    """Method registry: list, inspect, run, and diff registered methods."""


@cli.command("list")
@click.option("--status", "status_filter", type=str, default=None,
              help="Filter by status (experimental, active, deprecated, retired)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_methods(status_filter: Optional[str], as_json: bool) -> None:
    """List all registered methods."""
    from noosphere.methods import REGISTRY

    methods = REGISTRY.list(status_filter=status_filter)
    if as_json:
        _render([{"name": m.name, "version": m.version, "status": m.status,
                  "type": m.method_type.value, "description": m.description}
                 for m in methods], True)
        return
    if not methods:
        console.print("[yellow]No methods registered.[/yellow]")
        return
    table = Table(title="Registered Methods", show_header=True)
    table.add_column("Name", style="cyan")
    table.add_column("Version")
    table.add_column("Status")
    table.add_column("Type")
    table.add_column("Description", max_width=50)
    for m in methods:
        table.add_row(m.name, m.version, m.status, m.method_type.value,
                      m.description[:50])
    console.print(table)


@cli.command("show")
@click.argument("ref")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def show_method(ref: str, as_json: bool) -> None:
    """Show details of a method. REF is name or name@version."""
    from noosphere.methods import REGISTRY

    name, version = (ref.split("@", 1) + ["latest"])[:2]
    method, _fn = REGISTRY.get(name, version=version)
    if as_json:
        _render(method.model_dump(), True)
        return
    table = Table(title=f"Method: {method.name}@{method.version}", show_header=False)
    for field in ("method_id", "name", "version", "method_type", "status",
                  "owner", "description", "rationale"):
        val = getattr(method, field)
        table.add_row(field, str(val) if not hasattr(val, "value") else val.value)
    table.add_row("preconditions", ", ".join(method.preconditions) or "—")
    table.add_row("postconditions", ", ".join(method.postconditions) or "—")
    console.print(table)


@cli.command("run")
@click.argument("ref")
@click.option("--input", "input_json", required=True, help="JSON input for the method")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def run_method(ref: str, input_json: str, as_json: bool) -> None:
    """Run a method. REF is name or name@version."""
    from noosphere.methods import REGISTRY

    name, version = (ref.split("@", 1) + ["latest"])[:2]
    _method, fn = REGISTRY.get(name, version=version)
    payload = json.loads(input_json)
    result = fn(payload)
    if as_json:
        _render(result if isinstance(result, (dict, list)) else str(result), True)
        return
    console.print(result)


@cli.command("diff")
@click.argument("method")
@click.argument("v_a")
@click.argument("v_b")
@click.option(
    "--public/--private",
    "public_view",
    default=False,
    help="Render the public-visible diff (private failure modes hidden). "
    "Default is the private (founder) diff.",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def diff_methods(
    method: str, v_a: str, v_b: str, public_view: bool, as_json: bool
) -> None:
    """Side-by-side diff of two versions of a method.

    Compares source, RATIONALE, FAILURES.yaml (adds/removes/changes),
    and the registered DomainBound. The hash is content-addressed and
    stable across machines, so the same checkout always produces the
    same diff.
    """
    from noosphere.methods import REGISTRY
    from noosphere.methods.version_diff import render_diff
    from noosphere.methods.version_snapshot import capture_snapshot

    # Validate that both versions are in the registry. We could also
    # diff arbitrary unregistered versions (e.g. a checkout snapshot
    # vs. a published one) but the standard CLI flow stays grounded
    # in registered versions to make accidental hash drift loud.
    REGISTRY.get(method, version=v_a, include_retired=True)
    REGISTRY.get(method, version=v_b, include_retired=True)

    snap_a = capture_snapshot(method, v_a)
    snap_b = capture_snapshot(method, v_b)
    visibility = "public" if public_view else "private"
    diff = render_diff(snap_a, snap_b, visibility=visibility)

    if as_json:
        _render(
            {
                "method": diff.name,
                "a": {"version": v_a, "hash": diff.a_hash},
                "b": {"version": v_b, "hash": diff.b_hash},
                "code_diff": diff.code_diff,
                "rationale_diff": diff.rationale_diff,
                "failures": {
                    "added": list(diff.failures_delta.added),
                    "removed": list(diff.failures_delta.removed),
                    "changed": list(diff.failures_delta.changed),
                },
                "domain_bound_diff": diff.domain_bound_diff,
                "visibility": visibility,
            },
            True,
        )
        return

    if diff.is_empty():
        console.print("[green]Versions are identical.[/green]")
        return

    console.print(
        f"[bold]{diff.name}[/bold] · {v_a} ({snap_a.short_hash()}) "
        f"→ {v_b} ({snap_b.short_hash()}) · {visibility} view"
    )
    if diff.code_diff:
        console.print("\n[cyan]── Code ──[/cyan]")
        console.print(diff.code_diff)
    if diff.rationale_diff:
        console.print("\n[cyan]── Rationale ──[/cyan]")
        console.print(diff.rationale_diff)
    if diff.failures_diff:
        console.print("\n[cyan]── Failures ──[/cyan]")
        console.print(diff.failures_diff)
    if diff.domain_bound_diff:
        console.print("\n[cyan]── Domain bound ──[/cyan]")
        console.print(diff.domain_bound_diff)


@cli.group("failures")
def failures_cli() -> None:
    """Curate and validate per-method failure-mode catalogs."""


@failures_cli.command("init")
@click.argument("method_name")
def failures_init(method_name: str) -> None:
    """Scaffold a `<method>.FAILURES.yaml` next to the method source."""
    from noosphere.methods.failure_modes import (
        FailureCatalogError,
        scaffold_catalog,
    )

    try:
        path = scaffold_catalog(method_name)
    except FailureCatalogError as exc:
        raise click.ClickException(str(exc))
    console.print(
        f"[green]Scaffolded[/green] {path} — edit it to add real entries."
    )


@failures_cli.command("lint")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def failures_lint(as_json: bool) -> None:
    """Validate every failure-mode catalog. Non-zero exit on any error."""
    from noosphere.methods.failure_modes import (
        FailureCatalogError,
        lint_all,
    )

    try:
        catalogs = lint_all()
    except FailureCatalogError as exc:
        raise click.ClickException(str(exc))

    summary = [
        {
            "method": method,
            "modes": (
                "deliberately-empty"
                if catalog.failures == "deliberately-empty"
                else len(catalog.modes)
            ),
            "high_severity": sum(
                1 for m in catalog.modes if m.severity == "high"
            ),
            "public_entries": sum(1 for m in catalog.modes if m.public),
        }
        for method, catalog in catalogs.items()
    ]
    if as_json:
        _render(summary, True)
        return

    if not summary:
        console.print("[yellow]No failure-mode catalogs found.[/yellow]")
        return
    table = Table(title="Failure-mode catalogs", show_header=True)
    table.add_column("Method", style="cyan")
    table.add_column("Modes")
    table.add_column("High-severity")
    table.add_column("Public entries")
    for row in summary:
        table.add_row(
            row["method"],
            str(row["modes"]),
            str(row["high_severity"]),
            str(row["public_entries"]),
        )
    console.print(table)


@cli.group("anchors")
def anchors_cli() -> None:
    """Curate domain-bound anchor centroids for a method."""


@anchors_cli.command("propose")
@click.argument("method_name")
@click.option(
    "--from-file",
    "from_file",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help=(
        "Path to a JSON file with `[{\"conclusion_id\": str, "
        "\"embedding\": [float...]}, ...]` and `embedding_model`. "
        "When omitted, the curator reads in-domain conclusions from "
        "the Codex DB using ConclusionMethod links."
    ),
)
@click.option(
    "--embedding-model",
    "embedding_model",
    type=str,
    default=None,
    help="Embedding model identifier. Required for cross-model safety. "
    "When --from-file is set, defaults to the file's `embedding_model`.",
)
@click.option(
    "-k",
    "k",
    type=int,
    default=4,
    show_default=True,
    help="Number of anchor centroids to propose.",
)
@click.option(
    "--seed",
    type=int,
    default=0,
    show_default=True,
    help="Deterministic seeding for k-medoids.",
)
@click.option(
    "--in-quantile",
    type=float,
    default=0.90,
    show_default=True,
    help="Quantile of within-cluster distances used as suggested in_radius.",
)
@click.option(
    "--edge-quantile",
    type=float,
    default=0.98,
    show_default=True,
    help="Quantile used as suggested edge_radius (>= in_quantile).",
)
@click.option(
    "--limit",
    type=int,
    default=500,
    show_default=True,
    help="Maximum number of in-domain conclusions to read from the DB.",
)
@click.option(
    "--organization-slug",
    "organization_slug",
    type=str,
    default=None,
    help="Restrict DB read to a single organization.",
)
def anchors_propose(
    method_name: str,
    from_file: Optional[str],
    embedding_model: Optional[str],
    k: int,
    seed: int,
    in_quantile: float,
    edge_quantile: float,
    limit: int,
    organization_slug: Optional[str],
) -> None:
    """Propose anchor centroids for METHOD_NAME using k-medoids on the
    historically in-domain conclusions for that method.

    The output is a draft revision blob — nothing auto-commits. The
    human inspects the medoid IDs (so they can read each prototype's
    text), edits the radii if needed, and writes the resulting
    AnchorBound into the method's declaration.
    """
    from noosphere.methods.anchor_curator import (
        CandidateConclusion,
        propose_anchors,
    )

    candidates: list[CandidateConclusion] = []
    resolved_model = embedding_model

    if from_file:
        with open(from_file, "r", encoding="utf-8") as f:
            blob = json.load(f)
        if isinstance(blob, dict):
            if not resolved_model:
                resolved_model = blob.get("embedding_model")
            rows = blob.get("candidates") or blob.get("conclusions") or []
        else:
            rows = blob
        for row in rows:
            cid = str(row["conclusion_id"])
            emb = tuple(float(x) for x in row["embedding"])
            candidates.append(CandidateConclusion(conclusion_id=cid, embedding=emb))
    else:
        if not resolved_model:
            raise click.ClickException(
                "--embedding-model is required when reading from the DB"
            )
        candidates = _load_in_domain_candidates_from_codex(
            method_name=method_name,
            organization_slug=organization_slug,
            embedding_model=resolved_model,
            limit=limit,
        )

    if not resolved_model:
        raise click.ClickException(
            "Cannot determine embedding model. Pass --embedding-model or "
            "include `embedding_model` in the input file."
        )
    if not candidates:
        raise click.ClickException(
            f"No in-domain candidates found for method {method_name!r}. "
            "Either point to an input file with --from-file or first link "
            "conclusions to this method via `noosphere methods track-record "
            "--rebuild`."
        )

    proposal = propose_anchors(
        method_name=method_name,
        embedding_model=resolved_model,
        candidates=candidates,
        k=k,
        seed=seed,
        in_quantile=in_quantile,
        edge_quantile=edge_quantile,
    )

    click.echo(json.dumps(proposal.to_dict(), indent=2))
    console.print(
        f"\n[yellow]Draft only.[/yellow] To wire this into "
        f"{method_name}, copy the `medoid_vectors`, `embedding_model`, "
        f"`suggested_in_radius`, `suggested_edge_radius`, and "
        f"`revision_id` into the method's `domain=` declaration. "
        f"Re-curating later produces a new revision_id rather than "
        f"mutating this one.",
        highlight=False,
    )


def _load_in_domain_candidates_from_codex(
    *,
    method_name: str,
    organization_slug: Optional[str],
    embedding_model: str,
    limit: int,
) -> list:
    """Read embeddings of conclusions linked to ``method_name`` via
    ``ConclusionMethod``. The embedding source is the canonical
    Conclusion.embedding column; rows whose stored ``embeddingModel``
    does not match ``embedding_model`` are skipped (no cross-model
    comparisons).

    The query is intentionally tolerant of schemas that do not yet have
    an ``embeddingModel`` column — callers running against an older DB
    will get the rows back filtered only by method name."""
    from noosphere.methods.anchor_curator import CandidateConclusion

    conn, real_dict_cursor = _open_codex()
    try:
        cur = conn.cursor(cursor_factory=real_dict_cursor)
        organization_id = _resolve_org_id(cur, organization_slug)

        # We tolerate either a JSON array column on Conclusion or a
        # sidecar embedding store; the firm's canonical layout stores
        # the vector on Conclusion.embedding as JSON. Older schemas
        # that don't have it will produce no rows and the caller will
        # see the friendly "no candidates" error above.
        cur.execute(
            '''SELECT c.id AS id,
                      c.embedding AS embedding
                 FROM "ConclusionMethod" cm
                 JOIN "Conclusion" c ON c.id = cm."conclusionId"
                WHERE cm."methodName" = %s
                  AND (%s IS NULL OR cm."organizationId" = %s)
                  AND c.embedding IS NOT NULL
                ORDER BY c.id
                LIMIT %s''',
            (method_name, organization_id, organization_id, int(limit)),
        )
        rows = list(cur.fetchall())
    finally:
        conn.close()

    out: list[CandidateConclusion] = []
    for r in rows:
        cid = r["id"] if isinstance(r, dict) else r[0]
        raw = r["embedding"] if isinstance(r, dict) else r[1]
        if raw is None:
            continue
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                continue
        if not isinstance(raw, list):
            continue
        try:
            vec = tuple(float(x) for x in raw)
        except Exception:
            continue
        out.append(CandidateConclusion(conclusion_id=str(cid), embedding=vec))
    return out


@cli.command("extract-candidates")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def extract_candidates(as_json: bool) -> None:
    """Scan the registry for candidate methods needing review."""
    from noosphere.methods import REGISTRY

    candidates = [m for m in REGISTRY.list() if m.status == "experimental"]
    if as_json:
        _render([{"name": m.name, "version": m.version, "owner": m.owner}
                 for m in candidates], True)
        return
    if not candidates:
        console.print("[green]No experimental candidates.[/green]")
        return
    table = Table(title="Method Candidates", show_header=True)
    table.add_column("Name", style="cyan")
    table.add_column("Version")
    table.add_column("Owner")
    for m in candidates:
        table.add_row(m.name, m.version, m.owner)
    console.print(table)


# ── Track record (method ↔ resolved forecasts) ─────────────────────────────


def _open_codex():
    from noosphere.codex_bridge import (
        REAL_DICT_CURSOR,
        _open_codex_connection,
        _resolve_codex_db_url,
    )

    url = _resolve_codex_db_url(None)
    conn = _open_codex_connection(url)
    return conn, REAL_DICT_CURSOR


def _resolve_org_id(cur, organization_slug: Optional[str]) -> Optional[str]:
    if not organization_slug:
        return None
    cur.execute(
        'SELECT id FROM "Organization" WHERE slug = %s',
        (organization_slug,),
    )
    row = cur.fetchone()
    if not row:
        raise click.ClickException(
            f"Organization slug not found: {organization_slug}"
        )
    return row["id"] if isinstance(row, dict) else row[0]


def _conclusions_with_profiles(cur, *, organization_id: Optional[str], limit: int):
    """Conclusions that have at least one MethodologyProfile attached, either
    directly or via the upload bridge."""
    cur.execute(
        '''SELECT DISTINCT c.id AS id,
                  c."organizationId" AS org_id,
                  c.text             AS text,
                  c."topicHint"      AS topic_hint
             FROM "Conclusion" c
             JOIN "MethodologyProfile" mp
                  ON mp."conclusionId" = c.id
                  OR mp."uploadId" IN (
                       SELECT cs."uploadId" FROM "ConclusionSource" cs
                        WHERE cs."conclusionId" = c.id
                  )
            WHERE (%s IS NULL OR c."organizationId" = %s)
            ORDER BY c.id
            LIMIT %s''',
        (organization_id, organization_id, int(limit)),
    )
    return list(cur.fetchall())


def _profiles_for(cur, *, organization_id: str, conclusion_id: str):
    from noosphere.evaluation.mqs import MethodologyProfileSummary

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

    def _aslist(raw):
        if raw is None:
            return []
        if isinstance(raw, list):
            return [str(x) for x in raw if x is not None]
        if isinstance(raw, str):
            try:
                v = json.loads(raw)
                return [str(x) for x in v if x is not None] if isinstance(v, list) else []
            except Exception:
                return []
        return []

    out = []
    for row in cur.fetchall():
        out.append(
            MethodologyProfileSummary(
                pattern_type=(row.get("patternType") if isinstance(row, dict) else row[0]) or "",
                title=(row.get("title") if isinstance(row, dict) else row[1]) or "",
                summary=(row.get("summary") if isinstance(row, dict) else row[2]) or "",
                reasoning_moves=_aslist(
                    row.get("reasoningMoves") if isinstance(row, dict) else row[3]
                ),
                transfer_targets=_aslist(
                    row.get("transferTargets") if isinstance(row, dict) else row[4]
                ),
                assumptions=_aslist(
                    row.get("assumptions") if isinstance(row, dict) else row[5]
                ),
                failure_modes=_aslist(
                    row.get("failureModes") if isinstance(row, dict) else row[6]
                ),
                confidence=float(
                    (row.get("confidence") if isinstance(row, dict) else row[7]) or 0.5
                ),
            )
        )
    return out


@cli.command("track-record")
@click.option(
    "--organization-slug",
    type=str,
    default=None,
    help="Restrict to a single organization (default: all orgs).",
)
@click.option(
    "--rebuild/--no-rebuild",
    default=False,
    help="Run the linker + aggregator pipeline before printing. Idempotent.",
)
@click.option(
    "--judge",
    "judge_name",
    type=click.Choice(["stub"]),
    default="stub",
    help="Linker judge to use. Only the deterministic stub is exposed via "
    "the CLI; production callers may construct their own MethodLinkerJudge.",
)
@click.option(
    "--limit",
    type=int,
    default=500,
    help="Maximum conclusions to (re)link in this run.",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def track_record(
    organization_slug: Optional[str],
    rebuild: bool,
    judge_name: str,
    limit: int,
    as_json: bool,
) -> None:
    """Show per-method track record. With --rebuild, first re-link every
    conclusion to its methods and re-aggregate every (method, domain) cell.
    Both passes are idempotent: re-running on a quiet DB is a no-op modulo
    `updatedAt`."""
    from noosphere.evaluation.method_outcome_linker import (
        StubMethodLinkerJudge,
        infer_links,
        registry_view,
        upsert_links,
    )
    from noosphere.evaluation.method_track_record import (
        aggregate,
        fetch_method_keys,
        fetch_resolved_rows,
        upsert_track_record,
    )

    conn, real_dict_cursor = _open_codex()
    try:
        cur = conn.cursor(cursor_factory=real_dict_cursor)
        organization_id = _resolve_org_id(cur, organization_slug)

        if rebuild:
            registry = registry_view()
            judge = StubMethodLinkerJudge()
            now = datetime.now(timezone.utc)

            conclusions = _conclusions_with_profiles(
                cur, organization_id=organization_id, limit=limit
            )
            linked = 0
            for c in conclusions:
                cid = c["id"] if isinstance(c, dict) else c[0]
                org = c["org_id"] if isinstance(c, dict) else c[1]
                text = (c.get("text") if isinstance(c, dict) else c[2]) or ""
                topic = (c.get("topic_hint") if isinstance(c, dict) else c[3]) or ""
                profiles = _profiles_for(cur, organization_id=org, conclusion_id=cid)
                if not profiles:
                    continue
                links = infer_links(
                    conclusion_id=cid,
                    conclusion_text=text,
                    topic_hint=topic,
                    profiles=profiles,
                    registry_methods=registry,
                    judge=judge,
                )
                if not links:
                    continue
                linked += upsert_links(
                    cur,
                    organization_id=org,
                    conclusion_id=cid,
                    links=links,
                    now=now,
                )

            # Aggregate per (org, method, version). Walk every distinct
            # method seen in ConclusionMethod so we don't miss methods
            # that no longer match a registered name.
            cur.execute(
                'SELECT id FROM "Organization"'
                + (' WHERE id = %s' if organization_id else ''),
                (organization_id,) if organization_id else (),
            )
            org_ids = [
                (row.get("id") if isinstance(row, dict) else row[0])
                for row in cur.fetchall()
            ]
            aggregated = 0
            for org_id in org_ids:
                for (m_name, m_version) in fetch_method_keys(
                    cur, organization_id=org_id
                ):
                    rows = fetch_resolved_rows(
                        cur,
                        organization_id=org_id,
                        method_name=m_name,
                        method_version=m_version,
                    )
                    records = aggregate(
                        organization_id=org_id,
                        method_name=m_name,
                        method_version=m_version,
                        rows=rows,
                        now=now,
                    )
                    # Even when rows is empty, emit a sample_size=0 row
                    # for every (method, domain="") so downstream UI sees
                    # the method exists but has no record yet.
                    if not records:
                        records = aggregate(
                            organization_id=org_id,
                            method_name=m_name,
                            method_version=m_version,
                            rows=[],
                            now=now,
                        )
                        if not records:
                            from noosphere.evaluation.method_track_record import (
                                TrackRecord,
                                TRACK_RECORD_SCHEMA,
                            )

                            records = [
                                TrackRecord(
                                    organization_id=org_id,
                                    method_name=m_name,
                                    method_version=m_version,
                                    domain="",
                                    sample_size=0,
                                    weighted_brier=None,
                                    calibration_slope=None,
                                    calibration_slope_ci_low=None,
                                    calibration_slope_ci_high=None,
                                    severity_pass_rate=None,
                                    evidence={
                                        "schema": TRACK_RECORD_SCHEMA,
                                        "prediction_ids": [],
                                        "conclusion_ids": [],
                                    },
                                    computed_at=now,
                                )
                            ]
                    for record in records:
                        upsert_track_record(cur, record)
                        aggregated += 1
            conn.commit()
            click.echo(
                json.dumps(
                    {"linked": linked, "aggregated": aggregated, "judge": judge_name},
                    indent=2,
                )
            )

        # Print whatever is in MethodTrackRecord (post-rebuild or cached).
        cur.execute(
            '''SELECT "organizationId", "methodName", "methodVersion", domain,
                      "sampleSize", "weightedBrier",
                      "calibrationSlope", "calibrationSlopeCiLow",
                      "calibrationSlopeCiHigh", "severityPassRate",
                      "computedAt"
                 FROM "MethodTrackRecord"
                WHERE (%s IS NULL OR "organizationId" = %s)
                ORDER BY "methodName", "methodVersion", domain''',
            (organization_id, organization_id),
        )
        rows = list(cur.fetchall())

        if as_json:
            click.echo(
                json.dumps(
                    [
                        {
                            "organization_id": r["organizationId"]
                            if isinstance(r, dict) else r[0],
                            "method_name": r["methodName"]
                            if isinstance(r, dict) else r[1],
                            "method_version": r["methodVersion"]
                            if isinstance(r, dict) else r[2],
                            "domain": r["domain"] if isinstance(r, dict) else r[3],
                            "sample_size": r["sampleSize"]
                            if isinstance(r, dict) else r[4],
                            "weighted_brier": r["weightedBrier"]
                            if isinstance(r, dict) else r[5],
                            "calibration_slope": r["calibrationSlope"]
                            if isinstance(r, dict) else r[6],
                            "calibration_slope_ci_low": r["calibrationSlopeCiLow"]
                            if isinstance(r, dict) else r[7],
                            "calibration_slope_ci_high": r["calibrationSlopeCiHigh"]
                            if isinstance(r, dict) else r[8],
                            "severity_pass_rate": r["severityPassRate"]
                            if isinstance(r, dict) else r[9],
                            "computed_at": str(
                                r["computedAt"] if isinstance(r, dict) else r[10]
                            ),
                        }
                        for r in rows
                    ],
                    indent=2,
                    default=str,
                )
            )
            return

        if not rows:
            console.print(
                "[yellow]No track records yet. Run with --rebuild.[/yellow]"
            )
            return

        table = Table(title="Method Track Records", show_header=True)
        table.add_column("Method", style="cyan")
        table.add_column("v")
        table.add_column("Domain")
        table.add_column("n")
        table.add_column("Brier")
        table.add_column("Slope")
        table.add_column("CI")
        table.add_column("Sev pass")
        for r in rows:
            def _g(key, idx):
                return r[key] if isinstance(r, dict) else r[idx]

            slope = _g("calibrationSlope", 6)
            lo = _g("calibrationSlopeCiLow", 7)
            hi = _g("calibrationSlopeCiHigh", 8)
            ci = (
                f"[{lo:.2f}, {hi:.2f}]"
                if (lo is not None and hi is not None)
                else "—"
            )
            brier = _g("weightedBrier", 5)
            sev = _g("severityPassRate", 9)
            table.add_row(
                str(_g("methodName", 1)),
                str(_g("methodVersion", 2)),
                str(_g("domain", 3) or "—"),
                str(_g("sampleSize", 4)),
                f"{brier:.3f}" if brier is not None else "—",
                f"{slope:.2f}" if slope is not None else "—",
                ci,
                f"{sev:.0%}" if sev is not None else "—",
            )
        console.print(table)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
