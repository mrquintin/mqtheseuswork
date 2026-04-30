"""
Typer-based CLI (Phase 4) — structured logging, orchestrator-backed commands.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from noosphere.backup_restore import create_backup_archive, restore_backup_archive
from noosphere.config import get_settings
from noosphere.observability import configure_logging, get_logger

app = typer.Typer(no_args_is_help=True, help="Noosphere — Brain of the Firm")
console = Console()
log = get_logger(__name__)


def _orch():
    from noosphere.orchestrator import NoosphereOrchestrator

    return NoosphereOrchestrator()


@app.command("ingest")
def ingest_cmd(
    path: Path = typer.Argument(..., exists=True, readable=True, help="Artifact or transcript path"),
    episode: Optional[int] = typer.Option(None, help="Episode number (transcript ingest)"),
    episode_date: Optional[str] = typer.Option(None, "--date", help="YYYY-MM-DD"),
    title: str = typer.Option("", help="Episode title"),
    speakers: str = typer.Option("", help="Comma-separated speaker names"),
) -> None:
    """Ingest transcript (with --episode and --date) or markdown/text artifact."""
    configure_logging(json_format=True)
    orch = _orch()
    if episode is not None and episode_date:
        from datetime import datetime

        d = datetime.strptime(episode_date, "%Y-%m-%d").date()
        sp = [s.strip() for s in speakers.split(",") if s.strip()] if speakers else None
        log.info("typer_ingest_start", path=str(path), episode=episode)
        ep = orch.ingest_episode(
            str(path), episode_number=episode, episode_date=d, title=title, speakers=sp
        )
        log.info("typer_ingest_done", episode_id=ep.id)
        typer.echo(json.dumps({"ok": True, "episode_id": ep.id}, default=str))
    else:
        from noosphere.ingester import ingest_markdown, ingest_text, ingest_transcript

        # `ingest_markdown / ingest_text / ingest_transcript` only persist
        # when `store=` is non-None (see ingest_artifacts.py). Previously
        # this branch called them without `store`, so the CLI reported
        # success + an artifact_id while nothing was actually written to
        # the DB. Passing the orchestrator's store fixes the silent no-op.
        suf = path.suffix.lower()
        if suf in {".md", ".markdown"}:
            art = ingest_markdown(path, store=orch.store)
            log.info("typer_ingest_artifact", artifact_id=art.id, path=str(path))
            typer.echo(json.dumps({"ok": True, "artifact_id": art.id}, default=str))
            return
        if suf in {".vtt", ".txt", ".jsonl"}:
            art, _chunks, _claims = ingest_transcript(path, store=orch.store)
        else:
            art = ingest_text(path, store=orch.store)
        log.info("typer_ingest_artifact", artifact_id=art.id, path=str(path))
        typer.echo(json.dumps({"ok": True, "artifact_id": art.id}, default=str))


@app.command("synthesize")
def synthesize_cmd() -> None:
    """Run synthesis assembly (firm / founder conclusions + open questions)."""
    configure_logging(json_format=True)
    orch = _orch()
    from noosphere.synthesis import run_synthesis_pipeline

    n = run_synthesis_pipeline(orch).persisted_count
    log.info("typer_synthesize_done", items=n)
    typer.echo(json.dumps({"ok": True, "items_written": n}))


# ─────────────────────────────────────────────────────────────────────────────
# Theseus Codex bridge — process uploads that landed in the Codex's Postgres
# from the web UI but couldn't be ingested there (Vercel has no Python).
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# Codex authentication (login / logout / whoami)
#
# These are thin shells around `noosphere.auth` that make the CLI
# self-contained: a fresh clone can run `noosphere login` and
# immediately use `ingest-from-codex` without having to set any env
# vars. The stored key lives at ~/.noosphere/credentials.json with
# 0600 permissions.
# ─────────────────────────────────────────────────────────────────────────────


@app.command("login")
def login_cmd(
    codex_url: Optional[str] = typer.Option(
        None,
        "--codex-url",
        help="Override the Codex base URL (defaults to the bundled production URL).",
    ),
    organization_slug: Optional[str] = typer.Option(
        None,
        "--org",
        help="Organization slug (defaults to 'theseus-local').",
    ),
    email: Optional[str] = typer.Option(
        None,
        "--email",
        help="Email to sign in with. Prompted if omitted.",
    ),
) -> None:
    """Sign in to the Codex and save a device API key.

    Prompts for a passphrase on the terminal (via getpass). On success
    writes ~/.noosphere/credentials.json — destructive Codex commands
    (``ingest-from-codex``, ``codex-queued``) require this file.
    """
    configure_logging(json_format=False)
    from noosphere.auth import AuthError, login_interactive

    try:
        creds = login_interactive(
            codex_url=codex_url,
            organization_slug=organization_slug,
            email=email,
        )
    except AuthError as e:
        typer.echo(f"Sign-in failed: {e}", err=True)
        raise typer.Exit(code=2)
    except KeyboardInterrupt:
        typer.echo("\nSign-in cancelled.", err=True)
        raise typer.Exit(code=130)

    typer.echo(
        f"Signed in as {creds.founder_name} ({creds.founder_email}) · "
        f"{creds.codex_url} · key ›{creds.api_key[:14]}…‹"
    )


@app.command("logout")
def logout_cmd() -> None:
    """Clear the locally-stored Codex credentials."""
    configure_logging(json_format=False)
    from noosphere.auth import active, clear

    existing = active()
    clear()
    if existing:
        typer.echo(
            f"Signed out · credentials for {existing.founder_email or existing.founder_name} removed."
        )
    else:
        typer.echo("No credentials were stored.")


@app.command("whoami")
def whoami_cmd() -> None:
    """Validate the current API key against /api/auth/whoami."""
    configure_logging(json_format=True)
    from noosphere.auth import AuthError, active, whoami

    c = active()
    if c is None:
        typer.echo(
            json.dumps(
                {"ok": False, "error": "Not signed in. Run `noosphere login`."},
                default=str,
            ),
            err=True,
        )
        raise typer.Exit(code=2)

    try:
        body = whoami(c)
    except AuthError as e:
        typer.echo(
            json.dumps({"ok": False, "error": str(e)}, default=str),
            err=True,
        )
        raise typer.Exit(code=2)

    typer.echo(
        json.dumps(
            {
                "ok": True,
                "codex_url": c.codex_url,
                "auth_method": body.get("authMethod", "api_key"),
                "founder": body.get("founder", {}),
                "organization_id": body.get("organizationId"),
                "key_label": c.key_label,
                "key_prefix": c.api_key[:14] + "…",
            },
            default=str,
        )
    )


@app.command("ingest-from-codex")
def ingest_from_codex_cmd(
    upload_id: str = typer.Option(
        ..., "--upload-id", help="The Upload.id from the Codex DB"
    ),
    codex_db_url: Optional[str] = typer.Option(
        None,
        "--codex-db-url",
        help=(
            "Codex Postgres URL. If omitted, reads "
            "THESEUS_CODEX_DATABASE_URL / CODEX_DATABASE_URL / "
            "DIRECT_URL / DATABASE_URL in that order."
        ),
    ),
    with_llm: bool = typer.Option(
        False,
        "--with-llm/--no-llm",
        help=(
            "Use Noosphere's LLM claim extractor instead of the naive "
            "sentence-splitter. Requires an ANTHROPIC_API_KEY or "
            "OPENAI_API_KEY in the environment."
        ),
    ),
    max_claims: int = typer.Option(
        40,
        help="Cap on claims extracted per upload. Prevents a long transcript from producing thousands of Conclusion rows.",
    ),
    dry_run: bool = typer.Option(
        False, help="Print what would be written; don't commit anything."
    ),
    organization_slug: Optional[str] = typer.Option(
        None,
        "--organization-slug",
        help="Abort if the upload doesn't belong to this tenant (safety for shared DBs).",
    ),
) -> None:
    """Process a queued-offline Codex upload locally.

    Reads the Codex Upload.textContent, extracts claims (naive splitter
    by default; LLM via --with-llm), and writes Conclusion rows + an
    AuditEvent back into the same Codex Postgres so the web UI shows
    the extracted claims immediately.

    Example:
        noosphere login  # one-time — prompts for your Codex credentials
        export DIRECT_URL='postgresql://postgres.<ref>:<pw>@aws-1-<region>.pooler.supabase.com:5432/postgres'
        python -m noosphere ingest-from-codex --upload-id cxxx123...
    """
    configure_logging(json_format=True)
    # Gate on Codex auth: this command writes Conclusion / Contradiction
    # rows into the shared database. We require a valid signed-in
    # session so every mutation can be attributed to a real founder.
    # Offline / transient whoami failures are tolerated so a flaky
    # network can't stall an ingest mid-flight.
    from noosphere.auth import require_auth
    require_auth(action="ingest-from-codex")

    from noosphere.codex_bridge import ingest_from_codex

    try:
        result = ingest_from_codex(
            upload_id,
            codex_db_url=codex_db_url,
            use_llm=with_llm,
            max_claims=max_claims,
            dry_run=dry_run,
            organization_slug_filter=organization_slug,
        )
    except Exception as exc:
        typer.echo(
            json.dumps(
                {"ok": False, "error": str(exc), "upload_id": upload_id},
                default=str,
            ),
            err=True,
        )
        raise typer.Exit(1) from exc

    typer.echo(
        json.dumps(
            {
                "ok": True,
                "mode": result.mode,
                "dry_run": result.dry_run,
                "upload_id": result.upload_id,
                "title": result.title,
                "claims_extracted": result.num_claims_extracted,
                "conclusions_written": result.num_conclusions_written,
                "contradictions_written": result.num_contradictions_written,
                "open_questions_written": result.num_open_questions_written,
                "research_suggestions_written": result.num_research_suggestions_written,
            },
            default=str,
        )
    )


@app.command("codex-queued")
def codex_queued_cmd(
    codex_db_url: Optional[str] = typer.Option(
        None,
        "--codex-db-url",
        help="Codex Postgres URL (see ingest-from-codex for fallback env vars).",
    ),
    limit: int = typer.Option(25, help="Max rows to list."),
) -> None:
    """List Codex uploads currently pending / queued-offline / processing.

    Quick "what do I need to ingest?" view. Use the printed IDs with
    ``ingest-from-codex --upload-id <id>``.
    """
    configure_logging(json_format=True)
    # Same auth gate as ingest-from-codex — even a read surfaces the
    # founder names / upload titles of the whole firm, so we want a
    # real identity behind the query (and an AuditEvent trail via
    # the Codex).
    from noosphere.auth import require_auth
    require_auth(action="codex-queued")

    from noosphere.codex_bridge import list_queued_uploads

    try:
        rows = list_queued_uploads(codex_db_url=codex_db_url, limit=limit)
    except Exception as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}, default=str), err=True)
        raise typer.Exit(1) from exc

    typer.echo(json.dumps({"ok": True, "count": len(rows), "rows": rows}, default=str))


@app.command("as-of")
def as_of_cmd(
    when: str = typer.Argument(..., metavar="YYYY-MM-DD"),
    action: str = typer.Argument(
        "synthesize",
        help="synthesize (dry-run preview) | conclusions | claims-count",
    ),
) -> None:
    """Replay helper: inspect claims/conclusions or dry-run synthesis as of a cutoff date."""
    configure_logging(json_format=True)
    orch = _orch()
    from noosphere.temporal_replay import (
        filter_claims_as_of,
        list_conclusions_replay_consistent,
        parse_cutoff_date,
        run_synthesis_as_of_preview,
    )

    d = parse_cutoff_date(when)
    if action == "claims-count":
        n = len(filter_claims_as_of(orch.store, dict(orch.graph.claims), d))
        typer.echo(json.dumps({"ok": True, "as_of": when, "claims": n}, indent=2))
        return
    if action == "conclusions":
        cons = list_conclusions_replay_consistent(orch.store, d)
        typer.echo(
            json.dumps(
                {
                    "ok": True,
                    "as_of": when,
                    "count": len(cons),
                    "conclusions": [c.model_dump(mode="json") for c in cons],
                },
                indent=2,
                default=str,
            )
        )
        return
    if action == "synthesize":
        previews, warns = run_synthesis_as_of_preview(orch, d)
        typer.echo(
            json.dumps(
                {
                    "ok": True,
                    "as_of": when,
                    "dry_run": True,
                    "warnings": warns,
                    "preview_count": len(previews),
                    "previews": [c.model_dump(mode="json") for c in previews],
                },
                indent=2,
                default=str,
            )
        )
        return
    typer.echo(json.dumps({"error": f"unknown action {action!r}"}, indent=2))
    raise typer.Exit(code=1)


@app.command("diff")
def diff_cmd(
    date_a: str = typer.Argument(..., metavar="YYYY-MM-DD"),
    date_b: str = typer.Argument(..., metavar="YYYY-MM-DD"),
    narrative: bool = typer.Option(False, "--narrative", help="Append grounded narrative (LLM if configured)"),
) -> None:
    """Structured diff of replay-consistent conclusions and newly-visible claims between two dates."""
    configure_logging(json_format=True)
    orch = _orch()
    from noosphere.temporal_replay import diff_structured_json, narrative_from_diff, parse_cutoff_date
    from noosphere.llm import llm_client_from_settings
    from noosphere.config import get_settings

    da, db = parse_cutoff_date(date_a), parse_cutoff_date(date_b)
    payload = diff_structured_json(orch.store, da, db)
    out: dict = {"ok": True, "diff": payload}
    if narrative:
        llm = llm_client_from_settings() if get_settings().effective_llm_api_key() else None
        out["narrative"] = narrative_from_diff(orch.store, da, db, llm=llm)
    typer.echo(json.dumps(out, indent=2, default=str))


@app.command("counterfactual")
def counterfactual_cmd(
    artifact_id: str = typer.Option(..., "--without-artifact", help="Artifact id whose sourced claims are removed"),
    when: Optional[str] = typer.Option(
        None,
        "--as-of",
        help="YYYY-MM-DD cutoff for visibility (default: today UTC)",
    ),
) -> None:
    """Dry-run synthesis excluding claims tied to one artifact (counterfactual)."""
    configure_logging(json_format=True)
    from datetime import datetime, timezone

    orch = _orch()
    from noosphere.temporal_replay import parse_cutoff_date, run_counterfactual_preview

    d = parse_cutoff_date(when) if when else datetime.now(timezone.utc).date()
    previews, warns = run_counterfactual_preview(orch, exclude_artifact_ids={artifact_id}, as_of=d)
    typer.echo(
        json.dumps(
            {
                "ok": True,
                "without_artifact": artifact_id,
                "as_of": d.isoformat(),
                "warnings": warns,
                "preview_count": len(previews),
                "previews": [c.model_dump(mode="json") for c in previews],
            },
            indent=2,
            default=str,
        )
    )


@app.command("research")
def research_cmd(
    session: str = typer.Option(..., "--session", help="Session / episode id label"),
    generate: bool = typer.Option(False, "--generate", help="Call LLM to produce brief"),
    list_only: bool = typer.Option(False, "--list", help="List cached suggestions for session"),
) -> None:
    """Topic and reading suggestions for a session."""
    configure_logging(json_format=True)
    orch = _orch()
    from noosphere.research_advisor import session_research

    out = session_research(
        orch, session_id=session, generate=generate, list_only=list_only
    )
    log.info("typer_research_done", session=session, generate=generate)
    typer.echo(out)


@app.command("status")
def status_cmd() -> None:
    """System status (data dir, graph size, registry paths)."""
    configure_logging(json_format=True)
    s = get_settings()
    orch = _orch()
    n_principles = len(orch.graph.principles)
    n_claims = len(orch.graph.claims)
    log.info(
        "typer_status",
        data_dir=str(orch.data_dir),
        principles=n_principles,
        claims_graph=n_claims,
    )
    typer.echo(
        json.dumps(
            {
                "data_dir": str(orch.data_dir),
                "database_url": s.database_url,
                "principles": n_principles,
                "claims_in_graph": n_claims,
            },
            indent=2,
        )
    )


@app.command("rebuild-embeddings")
def rebuild_embeddings_cmd() -> None:
    """Drop and recompute claim embeddings for configured model."""
    configure_logging(json_format=True)
    orch = _orch()
    from noosphere.embed_pass import rebuild_embeddings_main

    n = rebuild_embeddings_main(orch)
    log.info("typer_rebuild_embeddings_done", embedded=n)
    typer.echo(json.dumps({"ok": True, "embedded": n}))


@app.command("adversarial")
def adversarial_cmd(
    conclusion: Optional[str] = typer.Option(None, "--conclusion", help="Noosphere conclusion id"),
    all_firm: bool = typer.Option(False, "--all", help="Run for every firm-tier conclusion in the store"),
    depth: int = typer.Option(3, "--depth", help="Number of distinct traditions / objections"),
) -> None:
    """Generate strongest objections, formalize claims, run six-layer coherence, persist verdicts."""
    configure_logging(json_format=True)
    from noosphere.config import get_settings
    from noosphere.llm import llm_client_from_settings
    from noosphere.store import Store

    from noosphere.adversarial import run_adversarial_cycle_for_conclusion

    st = Store.from_database_url(get_settings().database_url)
    llm = llm_client_from_settings()
    targets: list[str] = []
    if conclusion:
        targets.append(conclusion)
    elif all_firm:
        for c in st.list_conclusions():
            if str(c.confidence_tier.value) == "firm":
                targets.append(c.id)
    else:
        typer.echo(
            json.dumps(
                {"error": "Specify --conclusion ID or --all for firm-tier conclusions."},
                indent=2,
            )
        )
        raise typer.Exit(code=1)

    done = 0
    for cid in targets:
        run_adversarial_cycle_for_conclusion(st, cid, llm=llm, depth=depth)
        done += 1
        log.info("typer_adversarial_done", conclusion_id=cid)
    typer.echo(json.dumps({"ok": True, "processed": done}, indent=2))


@app.command("ingest-voice")
def ingest_voice_cmd(
    path: Path = typer.Argument(..., exists=True, readable=True, help="Plain text or markdown corpus file"),
    name: str = typer.Option(..., "--name", help="Canonical display name for the Voice (e.g. Wittgenstein)"),
    copyright_note: str = typer.Option("", "--copyright", help="Permitted use / provenance note"),
    use_llm: bool = typer.Option(False, "--llm", help="Use LLM-backed claim extraction (requires API keys)"),
) -> None:
    """Ingest a text/markdown file as a tracked Voice corpus (claims tagged ``voice``)."""
    configure_logging(json_format=True)
    orch = _orch()
    from noosphere.llm import llm_client_from_settings
    from noosphere.voices import ingest_path_as_voice

    llm = llm_client_from_settings() if use_llm else None
    aid, n = ingest_path_as_voice(
        orch.store,
        path,
        name,
        copyright_status=copyright_note,
        use_llm_extractor=use_llm,
        llm=llm,
    )
    log.info("typer_ingest_voice_done", artifact_id=aid, claims=n)
    typer.echo(json.dumps({"ok": True, "artifact_id": aid, "claims_written": n}, indent=2))


voices_app = typer.Typer(no_args_is_help=True, help="Tracked Voices (non-founder thinkers)")
app.add_typer(voices_app, name="voices")

literature_app = typer.Typer(no_args_is_help=True, help="External literature ingestion and retrieval index")
app.add_typer(literature_app, name="literature")

predictive_app = typer.Typer(
    no_args_is_help=True,
    help="Predictive claims (falsifiable), resolutions, calibration exports",
)
app.add_typer(predictive_app, name="predictive")

forecasts_app = typer.Typer(
    no_args_is_help=True,
    help="Forecast markets, ingestion, and predictions",
)
app.add_typer(forecasts_app, name="forecasts")
forecasts_ingest_app = typer.Typer(no_args_is_help=True, help="Forecast ingestors")
forecasts_app.add_typer(forecasts_ingest_app, name="ingest")


@forecasts_ingest_app.command("polymarket")
def forecasts_ingest_polymarket_cmd(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Run against an in-memory store; no durable rows are written.",
    ),
) -> None:
    """Ingest active open markets from Polymarket Gamma."""
    from dataclasses import asdict

    from noosphere.forecasts.config import PolymarketConfig
    from noosphere.forecasts.polymarket_ingestor import ingest_once
    from noosphere.store import Store

    cfg = PolymarketConfig.from_env()
    if not cfg.organization_id:
        typer.echo(
            json.dumps(
                {
                    "ok": False,
                    "error": (
                        "No token is required for Polymarket Gamma, but "
                        "FORECASTS_INGEST_ORG_ID is not set."
                    ),
                },
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=2)

    store = (
        Store.from_database_url("sqlite:///:memory:")
        if dry_run
        else Store.from_database_url(get_settings().database_url)
    )
    result = asyncio.run(ingest_once(store, config=cfg))
    typer.echo(
        json.dumps(
            {
                "ok": not result.errors,
                "dry_run": dry_run,
                "accepted_categories": cfg.accepted_categories or ["*"],
                "result": asdict(result),
            },
            indent=2,
            default=str,
        )
    )


@forecasts_app.command("resolve")
def forecasts_resolve_cmd(
    market_id: Optional[str] = typer.Option(None, "--market", help="ForecastMarket id to poll."),
    resolve_all: bool = typer.Option(False, "--all", help="Poll all OPEN forecast markets."),
) -> None:
    """Poll external settlement metadata and append ForecastResolution rows."""
    configure_logging(json_format=True)
    from dataclasses import asdict

    from noosphere.forecasts.resolution_tracker import poll_all_open, poll_market
    from noosphere.store import Store

    if bool(market_id) == bool(resolve_all):
        typer.echo(
            json.dumps(
                {"ok": False, "error": "Specify exactly one of --market or --all."},
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=2)

    store = Store.from_database_url(get_settings().database_url)
    if resolve_all:
        results = asyncio.run(poll_all_open(store))
    else:
        assert market_id is not None
        results = [asyncio.run(poll_market(store, market_id))]

    errors = [error for result in results for error in result.errors]
    typer.echo(
        json.dumps(
            {
                "ok": not errors,
                "results": [asdict(result) for result in results],
            },
            indent=2,
            default=str,
        )
    )


@forecasts_app.command("run")
def forecasts_run_cmd(
    once: bool = typer.Option(
        False,
        "--once",
        help="Run one tick per Forecasts scheduler sub-loop and exit.",
    ),
) -> None:
    """Run the standing Forecasts scheduler loop."""
    from noosphere.forecasts.scheduler import main as scheduler_main

    raise typer.Exit(code=scheduler_main(["--once"] if once else ["run"]))


@literature_app.command("index")
def literature_index_cmd() -> None:
    """Rebuild hybrid FTS index over stored claims (dense path uses embeddings when present)."""
    configure_logging(json_format=True)
    orch = _orch()
    from noosphere.retrieval import HybridRetriever

    n = HybridRetriever().rebuild(orch.store)
    log.info("typer_literature_index_done", rows=n)
    typer.echo(json.dumps({"ok": True, "fts_rows": n}, indent=2))


@literature_app.command("local-pdf")
def literature_local_pdf_cmd(
    path: Path = typer.Argument(..., exists=True, readable=True),
    license_status: str = typer.Option("firm_licensed", "--license"),
) -> None:
    """Ingest a local PDF (optional sidecar .json with title, author, date)."""
    configure_logging(json_format=True)
    orch = _orch()
    from noosphere.literature import LocalPDFConnector

    ids = LocalPDFConnector().ingest(orch.store, path=path, license_status=license_status)
    typer.echo(json.dumps({"ok": True, "artifact_ids": ids}, indent=2))


@predictive_app.command("extract")
def predictive_extract_cmd(
    claim_id: str = typer.Option(..., "--claim-id", help="Source claim UUID"),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Write draft rows to the store"),
) -> None:
    """LLM second pass: extract draft PredictiveClaim rows from one claim."""
    configure_logging(json_format=True)
    orch = _orch()
    c = orch.store.get_claim(claim_id)
    if c is None:
        typer.echo(json.dumps({"ok": False, "error": "claim not found"}, indent=2))
        raise typer.Exit(code=1)
    from noosphere.predictive_extractor import extract_predictive_claims_for_claim, persist_drafts

    pcs = extract_predictive_claims_for_claim(c, artifact_id=c.source_id or "")
    if persist and pcs:
        persist_drafts(orch.store, pcs)
    typer.echo(
        json.dumps(
            {"ok": True, "count": len(pcs), "predictive_claims": [p.model_dump(mode="json") for p in pcs]},
            indent=2,
            default=str,
        )
    )


@predictive_app.command("confirm")
def predictive_confirm_cmd(
    pred_id: str = typer.Option(..., "--id", help="PredictiveClaim id"),
) -> None:
    """Founder audit: move a draft prediction into the scoring pool."""
    configure_logging(json_format=True)
    orch = _orch()
    from noosphere.resolution import confirm_predictive_for_scoring

    pc = confirm_predictive_for_scoring(orch.store, pred_id)
    typer.echo(json.dumps({"ok": True, "predictive_claim": pc.model_dump(mode="json")}, indent=2, default=str))


@predictive_app.command("resolve")
def predictive_resolve_cmd(
    pred_id: str = typer.Option(..., "--id"),
    outcome: int = typer.Option(..., "--outcome", help="0 or 1"),
    justification: str = typer.Option(..., "--justification"),
    evidence_artifacts: str = typer.Option("", "--evidence-artifacts", help="Comma-separated artifact ids"),
    resolver: str = typer.Option("", "--resolver", help="Founder id or handle"),
) -> None:
    """Manual resolution with justification and optional evidence artifact pointers."""
    configure_logging(json_format=True)
    if outcome not in (0, 1):
        typer.echo(json.dumps({"ok": False, "error": "outcome must be 0 or 1"}, indent=2))
        raise typer.Exit(code=1)
    orch = _orch()
    from noosphere.resolution import submit_manual_resolution

    ids = [x.strip() for x in evidence_artifacts.split(",") if x.strip()]
    pc, res = submit_manual_resolution(
        orch.store,
        pred_id,
        int(outcome),  # type: ignore[arg-type]
        justification=justification,
        evidence_artifact_ids=ids,
        resolver_founder_id=resolver,
    )
    typer.echo(
        json.dumps(
            {
                "ok": True,
                "predictive_claim": pc.model_dump(mode="json"),
                "resolution": res.model_dump(mode="json"),
            },
            indent=2,
            default=str,
        )
    )


@predictive_app.command("flag-unclear")
def predictive_flag_unclear_cmd(
    pred_id: str = typer.Option(..., "--id"),
    note: str = typer.Option("", "--note"),
) -> None:
    """Mark criteria as insufficiently crisp (does not enter score aggregates)."""
    configure_logging(json_format=True)
    orch = _orch()
    from noosphere.resolution import mark_open_unclear

    pc = mark_open_unclear(orch.store, pred_id, note=note)
    typer.echo(json.dumps({"ok": True, "predictive_claim": pc.model_dump(mode="json")}, indent=2, default=str))


@predictive_app.command("list")
def predictive_list_cmd(
    author: Optional[str] = typer.Option(None, "--author"),
    status: Optional[str] = typer.Option(None, "--status"),
    limit: int = typer.Option(200, "--limit"),
) -> None:
    """List predictive claims (filters optional)."""
    configure_logging(json_format=True)
    orch = _orch()
    rows = orch.store.list_predictive_claims(limit=limit)
    if author:
        rows = [r for r in rows if (r.author_key or "") == author]
    if status:
        rows = [r for r in rows if r.status.value == status]
    typer.echo(json.dumps({"ok": True, "count": len(rows), "items": [r.model_dump(mode="json") for r in rows]}, indent=2, default=str))


@app.command("scoreboard")
def scoreboard_cmd() -> None:
    """Emit JSON aggregates for Brier, log-loss, calibration bins, weak domains."""
    configure_logging(json_format=True)
    from noosphere.scoring import scoreboard_payload
    from noosphere.store import Store

    st = Store.from_database_url(get_settings().database_url)
    typer.echo(json.dumps(scoreboard_payload(st), indent=2, default=str))


@literature_app.command("arxiv")
def literature_arxiv_cmd(
    query: str = typer.Option("cat:physics.soc-ph", "--query"),
    max_results: int = typer.Option(3, "--max"),
    full_pdf: bool = typer.Option(False, "--pdf", help="Download PDF text (slow; open access only)"),
) -> None:
    """Fetch recent arXiv metadata/abstracts into the literature corpus."""
    configure_logging(json_format=True)
    orch = _orch()
    from noosphere.literature import ArxivConnector

    ids = ArxivConnector().ingest(orch.store, search_query=query, max_results=max_results, full_text=full_pdf)
    typer.echo(json.dumps({"ok": True, "artifact_ids": ids}, indent=2))


@voices_app.command("list")
def voices_list_cmd() -> None:
    """List tracked Voices and corpus sizes."""
    configure_logging(json_format=True)
    orch = _orch()
    rows = orch.store.list_voice_profiles(limit=500)
    out = [
        {
            "id": v.id,
            "name": v.canonical_name,
            "artifacts": len(v.corpus_artifact_ids),
            "citations": v.citation_count,
            "copyright": v.copyright_status,
        }
        for v in rows
    ]
    typer.echo(json.dumps({"voices": out}, indent=2))


@voices_app.command("map")
def voices_map_cmd(
    conclusion: str = typer.Option(..., "--conclusion", help="Conclusion id to map against Voices"),
) -> None:
    """Compute and persist a cross-Voice relative position map for one conclusion."""
    configure_logging(json_format=True)
    orch = _orch()
    from noosphere.coherence.aggregator import CoherenceAggregator
    from noosphere.coherence.nli import StubNLIScorer
    from noosphere.models import CoherenceVerdict
    from noosphere.voices import compute_relative_position_map

    s = get_settings()
    has_llm = bool(s.effective_llm_api_key())
    agg = CoherenceAggregator(
        skip_llm_judge=not has_llm,
        skip_probabilistic_llm=not has_llm,
        nli=StubNLIScorer(verdict=CoherenceVerdict.UNRESOLVED),
    )
    m = compute_relative_position_map(orch.store, conclusion, agg)
    typer.echo(m.model_dump_json(indent=2))


@app.command("backup")
def backup_cmd(
    output_dir: Optional[Path] = typer.Option(
        None,
        "--output-dir",
        help="Directory for the tarball (default: ~/.theseus/archives)",
    ),
) -> None:
    """Dump SQLite store, data directory, and manifest into a timestamped .tar.gz."""
    configure_logging(json_format=True)
    path = create_backup_archive(output_dir=output_dir)
    log.info("typer_backup_done", path=str(path))
    typer.echo(json.dumps({"ok": True, "archive": str(path)}, indent=2))


@app.command("restore")
def restore_cmd(
    archive: Path = typer.Argument(..., exists=True, readable=True, help="Backup .tar.gz from noosphere backup"),
    force: bool = typer.Option(False, "--force", help="Allow restore into a non-empty data directory"),
) -> None:
    """Restore from ``noosphere backup`` archive (SQLite + data_dir)."""
    configure_logging(json_format=True)
    restore_backup_archive(archive, force=force)
    log.info("typer_restore_done", archive=str(archive))
    typer.echo(json.dumps({"ok": True, "restored_from": str(archive)}, indent=2))


@app.command("evaluate")
def evaluate_cmd(
    limit: int = typer.Option(50, help="Max coherence pairs from scheduler"),
) -> None:
    """Run coherence evaluation on scheduled pairs (store-backed when available)."""
    configure_logging(json_format=True)
    orch = _orch()
    from noosphere.store import Store

    store = Store.from_database_url(get_settings().database_url)
    from noosphere.coherence.aggregator import CoherenceAggregator
    from noosphere.coherence.nli import StubNLIScorer
    from noosphere.models import CoherenceVerdict

    agg = CoherenceAggregator(
        skip_llm_judge=True,
        skip_probabilistic_llm=True,
        nli=StubNLIScorer(verdict=CoherenceVerdict.UNRESOLVED),
    )
    n = 0
    seen: set[tuple[str, str]] = set()
    for cid in store.list_claim_ids()[:20]:
        if len(seen) >= limit:
            break
        c = store.get_claim(cid)
        if c is None:
            continue
        from noosphere.coherence.scheduler import schedule_pairs_for_new_claim

        for a_id, b_id in schedule_pairs_for_new_claim(store, c, k_neighbors=5):
            if len(seen) >= limit:
                break
            key = (a_id, b_id) if a_id < b_id else (b_id, a_id)
            if key in seen:
                continue
            seen.add(key)
            ca, cb = store.get_claim(a_id), store.get_claim(b_id)
            if not ca or not cb:
                continue
            agg.evaluate_pair(ca, cb, store=store)
            n += 1
    log.info("typer_evaluate_done", pairs=n)
    typer.echo(json.dumps({"ok": True, "pairs_evaluated": n}))


redteam_typer = typer.Typer(
    no_args_is_help=True,
    help="Internal red-team: synthetic attacks + mitigated regression checks (SP08).",
)
app.add_typer(redteam_typer, name="redteam")


@redteam_typer.command("run")
def redteam_run_cmd(
    attack_class: Optional[str] = typer.Option(
        None,
        "--attack-class",
        help="Mitigated regression id (default: run all)",
    ),
    target: Optional[str] = typer.Option(
        None,
        "--target",
        help="Reserved for future targeted engine runs",
    ),
) -> None:
    """Execute the versioned mitigated attack suite (raises exit 1 on regression)."""
    _ = target
    from noosphere.redteam import run_attack_suite

    try:
        out = run_attack_suite(attack_class=attack_class)
    except ValueError as e:
        typer.echo(json.dumps({"ok": False, "error": str(e)}, indent=2))
        raise typer.Exit(code=2)
    except AssertionError as e:
        typer.echo(json.dumps({"ok": False, "error": str(e)}, indent=2))
        raise typer.Exit(code=1)
    typer.echo(json.dumps({"ok": True, **out}, indent=2))


@redteam_typer.command("taxonomy")
def redteam_taxonomy_cmd() -> None:
    """Print the attack class registry (status + mitigation pointers)."""
    from noosphere.redteam import ATTACK_SUITE_VERSION, list_attack_classes

    rows = [
        {
            "id": r.id,
            "title": r.title,
            "threat_model": r.threat_model,
            "impact": r.impact,
            "mitigation_status": r.mitigation_status,
            "mitigation_location": r.mitigation_location,
        }
        for r in list_attack_classes()
    ]
    typer.echo(
        json.dumps(
            {"attack_suite_version": ATTACK_SUITE_VERSION, "classes": rows},
            indent=2,
        )
    )


def main() -> None:
    try:
        app()
    except Exception as e:
        log.exception("typer_cli_fatal", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
