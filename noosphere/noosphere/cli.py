"""
Click-based CLI for Noosphere — The Brain of the Firm (legacy).

Primary entrypoint is Typer + structured logs: ``python -m noosphere`` (see ``typer_cli.py``).

Provides command-line access to all orchestrator functionality with beautiful
terminal output via Rich library.

Commands:
  ingest          Ingest a transcript and update the knowledge graph
  ask             Query the inference engine
  graph           Export the knowledge graph
  coherence       Run coherence analysis
  evolution       Track principle evolution over time
  stats           Display system statistics
  search          Semantic search over principles
  contradictions  Find contradictions in the graph
  principles      List principles with filters
  calibration     Show methodological feedback from conclusion accuracy
  conclusions     List substantive conclusions tracked for calibration
  classify        Classify a single claim (methodology vs substance)
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, date
from pathlib import Path
from typing import Any, Optional, List

import click
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.text import Text
except ImportError:  # pragma: no cover - exercised in minimal local envs.
    class Console:
        def print(self, *args, **_kwargs) -> None:
            click.echo(" ".join(str(arg) for arg in args))

        def status(self, *_args, **_kwargs):
            class _Status:
                def __enter__(self):
                    return self

                def __exit__(self, *_exc):
                    return False

            return _Status()

    class Table:
        def __init__(self, title: str = "", show_header: bool = True, **_kwargs) -> None:
            self.title = title
            self.rows: list[tuple[str, ...]] = []

        def add_column(self, *_args, **_kwargs) -> None:
            return None

        def add_row(self, *args, **_kwargs) -> None:
            self.rows.append(tuple(str(arg) for arg in args))

        def __str__(self) -> str:
            lines = [self.title] if self.title else []
            lines.extend(" | ".join(row) for row in self.rows)
            return "\n".join(lines)

    class Panel:
        def __init__(self, renderable, title: str = "", **_kwargs) -> None:
            self.renderable = renderable
            self.title = title

        def __str__(self) -> str:
            return f"{self.title}\n{self.renderable}" if self.title else str(self.renderable)

    class SpinnerColumn:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

    class TextColumn:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

    class Progress:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def add_task(self, *_args, **_kwargs) -> int:
            return 0

    class Text(str):
        pass

# ── Setup ────────────────────────────────────────────────────────────────────

console = Console()

from noosphere.observability import configure_logging

configure_logging(level="WARNING", json_format=False)


# ── Utilities ────────────────────────────────────────────────────────────────

def parse_date(date_str: str) -> date:
    """Parse date string in YYYY-MM-DD format."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise click.BadParameter(
            f"Invalid date format: {date_str}. Use YYYY-MM-DD"
        )


def parse_disciplines(discipline_str: Optional[str]) -> List[Discipline]:
    """Parse comma-separated discipline names."""
    from noosphere.models import Discipline

    if not discipline_str:
        return []
    names = [d.strip() for d in discipline_str.split(",")]
    result = []
    for name in names:
        try:
            result.append(Discipline[name.upper().replace(" ", "_")])
        except KeyError:
            available = ", ".join(d.name for d in Discipline)
            raise click.BadParameter(
                f"Unknown discipline: {name}\nAvailable: {available}"
            )
    return result


def get_orchestrator(data_dir: Optional[str]) -> NoosphereOrchestrator:
    """Load orchestrator with optional data directory override."""
    from noosphere.orchestrator import NoosphereOrchestrator

    return NoosphereOrchestrator(data_dir or "./noosphere_data")


def _store_from_settings():
    from noosphere.config import get_settings
    from noosphere.store import Store

    return Store.from_database_url(get_settings().database_url)


# ── CLI Group ────────────────────────────────────────────────────────────────

@click.group(invoke_without_command=True)
@click.version_option(version="0.1.0", prog_name="noosphere")
@click.pass_context
def cli(ctx):
    """Noosphere CLI — The Brain of the Firm knowledge system."""
    if ctx.invoked_subcommand is None:
        # Show help if no subcommand
        click.echo(ctx.get_help())


# ── Command: forecasts ─────────────────────────────────────────────────────

@click.group("forecasts")
def forecasts_cli() -> None:
    """Forecast-market ingestion and prediction commands."""


@forecasts_cli.group("ingest")
def forecasts_ingest_cli() -> None:
    """Run forecast-market ingestors."""


@forecasts_ingest_cli.command("polymarket")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Run against an in-memory store; no durable rows are written.",
)
def forecasts_ingest_polymarket(dry_run: bool) -> None:
    """Ingest active open markets from Polymarket Gamma."""
    from dataclasses import asdict

    from noosphere.forecasts.config import PolymarketConfig
    from noosphere.forecasts.polymarket_ingestor import ingest_once
    from noosphere.store import Store

    cfg = PolymarketConfig.from_env()
    if not cfg.organization_id:
        click.echo(
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
        raise SystemExit(2)

    store = (
        Store.from_database_url("sqlite:///:memory:")
        if dry_run
        else _store_from_settings()
    )
    result = asyncio.run(ingest_once(store, config=cfg))
    click.echo(
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


@forecasts_ingest_cli.command("kalshi")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Run against an in-memory store; no durable rows are written.",
)
def forecasts_ingest_kalshi(dry_run: bool) -> None:
    """Ingest open markets from Kalshi's authenticated read-only API."""
    from dataclasses import asdict

    from noosphere.forecasts.config import KalshiConfig
    from noosphere.forecasts.kalshi_ingestor import ingest_once
    from noosphere.store import Store

    cfg = KalshiConfig.from_env()
    if cfg.is_configured and not cfg.organization_id:
        click.echo(
            json.dumps(
                {
                    "ok": False,
                    "error": (
                        "Kalshi credentials are configured, but "
                        "FORECASTS_INGEST_ORG_ID is not set."
                    ),
                },
                indent=2,
            ),
            err=True,
        )
        raise SystemExit(2)

    store = (
        Store.from_database_url("sqlite:///:memory:")
        if dry_run
        else _store_from_settings()
    )
    result = asyncio.run(ingest_once(store, config=cfg))
    click.echo(
        json.dumps(
            {
                "ok": _forecast_ingest_ok(result.errors),
                "dry_run": dry_run,
                "accepted_categories": cfg.accepted_categories or ["*"],
                "result": asdict(result),
            },
            indent=2,
            default=str,
        )
    )


@forecasts_ingest_cli.command("all")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Run against an in-memory store; no durable rows are written.",
)
def forecasts_ingest_all(dry_run: bool) -> None:
    """Operator entry point: run Polymarket, then Kalshi, sequentially."""
    from dataclasses import asdict

    from noosphere.forecasts.config import KalshiConfig, PolymarketConfig
    from noosphere.forecasts.kalshi_ingestor import ingest_once as ingest_kalshi_once
    from noosphere.forecasts.polymarket_ingestor import (
        ingest_once as ingest_polymarket_once,
    )
    from noosphere.store import Store

    polymarket_cfg = PolymarketConfig.from_env()
    kalshi_cfg = KalshiConfig.from_env()
    if not polymarket_cfg.organization_id:
        click.echo(
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
        raise SystemExit(2)

    store = (
        Store.from_database_url("sqlite:///:memory:")
        if dry_run
        else _store_from_settings()
    )

    async def _run_all():
        polymarket_result = await ingest_polymarket_once(
            store,
            config=polymarket_cfg,
        )
        kalshi_result = await ingest_kalshi_once(store, config=kalshi_cfg)
        return polymarket_result, kalshi_result

    polymarket_result, kalshi_result = asyncio.run(_run_all())
    aggregate = _aggregate_forecast_results(polymarket_result, kalshi_result)
    click.echo(
        json.dumps(
            {
                "ok": _forecast_ingest_ok(aggregate["errors"]),
                "dry_run": dry_run,
                "accepted_categories": {
                    "polymarket": polymarket_cfg.accepted_categories or ["*"],
                    "kalshi": kalshi_cfg.accepted_categories or ["*"],
                },
                "result": aggregate,
                "sources": {
                    "polymarket": asdict(polymarket_result),
                    "kalshi": asdict(kalshi_result),
                },
            },
            indent=2,
            default=str,
        )
    )


def _aggregate_forecast_results(*results) -> dict[str, object]:
    return {
        "fetched": sum(result.fetched for result in results),
        "inserted": sum(result.inserted for result in results),
        "updated": sum(result.updated for result in results),
        "skipped": sum(result.skipped for result in results),
        "errors": [error for result in results for error in result.errors],
    }


def _forecast_ingest_ok(errors: list[str]) -> bool:
    return all(error == "KALSHI_NOT_CONFIGURED" for error in errors)


@forecasts_cli.command("resolve")
@click.option("--market", "market_id", default=None, help="ForecastMarket id to poll.")
@click.option("--all", "resolve_all", is_flag=True, default=False, help="Poll all OPEN forecast markets.")
def forecasts_resolve(market_id: str | None, resolve_all: bool) -> None:
    """Poll external settlement metadata and append ForecastResolution rows."""
    from dataclasses import asdict

    from noosphere.forecasts.resolution_tracker import poll_all_open, poll_market

    if bool(market_id) == bool(resolve_all):
        click.echo(
            json.dumps(
                {"ok": False, "error": "Specify exactly one of --market or --all."},
                indent=2,
            ),
            err=True,
        )
        raise SystemExit(2)

    store = _store_from_settings()
    if resolve_all:
        results = asyncio.run(poll_all_open(store))
    else:
        assert market_id is not None
        results = [asyncio.run(poll_market(store, market_id))]

    errors = [error for result in results for error in result.errors]
    click.echo(
        json.dumps(
            {
                "ok": not errors,
                "results": [asdict(result) for result in results],
            },
            indent=2,
            default=str,
        )
    )


@forecasts_cli.command("run")
@click.option(
    "--once",
    is_flag=True,
    default=False,
    help="Run one tick per Forecasts scheduler sub-loop and exit.",
)
def forecasts_run(once: bool) -> None:
    """Run the standing Forecasts scheduler loop."""
    from noosphere.forecasts.scheduler import main as scheduler_main

    raise SystemExit(scheduler_main(["--once"] if once else ["run"]))


# ── Command: ingest ─────────────────────────────────────────────────────────

@cli.command()
@click.argument("transcript_path", type=click.Path(exists=True))
@click.option(
    "--source",
    "source_kind",
    type=click.Choice(["transcript", "dialectic"]),
    default="transcript",
    help="transcript: full episode pipeline; dialectic: JSONL session claims (Phase 5).",
)
@click.option("--episode", "episode_num", type=int, default=None,
              help="Episode number (required for transcript source)")
@click.option("--date", "episode_date", type=str, default=None,
              help="Episode date YYYY-MM-DD (required for transcript source)")
@click.option("--title", type=str, default="",
              help="Episode title")
@click.option("--speakers", type=str, default="",
              help="Comma-separated list of speaker names")
@click.option(
    "--as-voice",
    is_flag=True,
    default=False,
    help="Ingest a .md / .plain text file as corpus for a tracked Voice (not a podcast episode).",
)
@click.option(
    "--voice-name",
    type=str,
    default=None,
    help="Display name for the Voice (required with --as-voice).",
)
@click.option(
    "--voice-copyright",
    type=str,
    default="",
    help="Provenance / rights note stored on the Voice profile (optional).",
)
@click.option("--data-dir", type=click.Path(), default=None,
              help="Data directory override")
def ingest(
    transcript_path,
    source_kind,
    episode_num,
    episode_date,
    title,
    speakers,
    as_voice,
    voice_name,
    voice_copyright,
    data_dir,
):
    """Ingest a transcript episode into the knowledge graph.

    Full pipeline: parse → extract claims → embed → classify → distill
    principles → update graph → coherence check → save.

    Example:
        noosphere ingest transcript.txt --episode 42 --date 2026-04-11 \\
          --title "Building AI" --speakers "Alice,Bob"

    Dialectic JSONL (one claim per line):

        noosphere ingest session.jsonl --source dialectic \\
          --episode 0 --date 2026-04-14
    """
    try:
        if as_voice:
            if not voice_name or not str(voice_name).strip():
                console.print(
                    "[bold red]--voice-name is required when using --as-voice.[/bold red]"
                )
                raise SystemExit(2)
            from noosphere.voices import ingest_path_as_voice

            console.print(
                "\n[bold]Ingesting corpus as Voice[/bold]",
                style="cyan",
            )
            with console.status(
                "[bold green]Initializing orchestrator...",
                spinner="dots",
            ):
                orch = get_orchestrator(data_dir)
            with console.status(
                "[bold green]Parsing file and attributing claims to Voice...",
                spinner="dots",
            ):
                artifact_id, n = ingest_path_as_voice(
                    orch.store,
                    transcript_path,
                    voice_name.strip(),
                    copyright_status=voice_copyright or "unspecified",
                )
            summary = Table(title="Voice corpus ingest", show_header=False)
            summary.add_row("Voice", voice_name.strip())
            summary.add_row("Artifact id", artifact_id)
            summary.add_row("Claims written", str(n))
            console.print(summary)
            console.print(
                "\n[bold green]✓ Voice corpus ingest complete[/bold green]\n"
            )
            return

        if source_kind == "dialectic":
            from noosphere.ingest_artifacts import ingest_dialectic_session_jsonl

            if episode_num is None:
                episode_num = 0
            parsed_date = (
                parse_date(episode_date) if episode_date else None
            )
            console.print(
                "\n[bold]Ingesting Dialectic session (JSONL)[/bold]",
                style="cyan",
            )
            with console.status(
                "[bold green]Initializing orchestrator...",
                spinner="dots",
            ):
                orch = get_orchestrator(data_dir)
            with console.status(
                "[bold green]Loading claims...",
                spinner="dots",
            ):
                _art, n = ingest_dialectic_session_jsonl(
                    transcript_path,
                    orch.store,
                    episode_id=str(episode_num),
                    episode_date=parsed_date,
                )
            summary = Table(title="Dialectic ingest", show_header=False)
            summary.add_row("Claims loaded", str(n))
            summary.add_row("Episode id", str(episode_num))
            console.print(summary)
            console.print(
                "\n[bold green]✓ Dialectic session ingest complete[/bold green]\n"
            )
            return

        if episode_num is None or not episode_date:
            console.print(
                "[bold red]Transcript source requires --episode and --date.[/bold red]"
            )
            raise SystemExit(2)

        console.print(
            f"\n[bold]Ingesting Episode {episode_num}[/bold]",
            style="cyan"
        )

        # Parse inputs
        parsed_date = parse_date(episode_date)
        speaker_list = [s.strip() for s in speakers.split(",") if s.strip()]

        # Load orchestrator
        with console.status(
            "[bold green]Initializing orchestrator...",
            spinner="dots"
        ):
            orch = get_orchestrator(data_dir)

        # Ingest episode
        with console.status(
            "[bold green]Processing transcript...",
            spinner="dots"
        ):
            episode = orch.ingest_episode(
                transcript_path=transcript_path,
                episode_number=episode_num,
                episode_date=parsed_date,
                title=title,
                speakers=speaker_list
            )

        # Show summary
        summary = Table(title="Ingestion Summary", show_header=False)
        summary.add_row("Episode Number", str(episode.number))
        summary.add_row("Date", str(episode.date))
        summary.add_row("Title", episode.title or "(none)")
        summary.add_row("Claims Extracted", str(episode.claim_count))
        summary.add_row("New Principles", str(len(episode.new_principles)))
        summary.add_row("Reinforced Principles", str(len(episode.reinforced_principles)))

        console.print(summary)
        console.print(
            "\n[bold green]✓ Episode ingestion complete[/bold green]\n"
        )

    except FileNotFoundError as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        raise SystemExit(1)
    except Exception as e:
        console.print(f"[bold red]Ingestion failed: {e}[/bold red]")
        raise SystemExit(1)


# ── Command: ask ────────────────────────────────────────────────────────────

@cli.command()
@click.argument("question", type=str)
@click.option("--context", type=str, default="",
              help="Additional context for the question")
@click.option("--discipline", "disciplines", type=str, default="",
              help="Comma-separated disciplines to scope the query")
@click.option("--no-coherence", is_flag=True,
              help="Don't require coherence with existing principles")
@click.option("--data-dir", type=click.Path(), default=None,
              help="Data directory override")
def ask(question, context, disciplines, no_coherence, data_dir):
    """Query the inference engine against the principle graph.

    Example:
        noosphere ask "How do we think about product-market fit?" \\
          --discipline "Entrepreneurship,VC"
    """
    try:
        console.print(f"\n[bold]Question:[/bold] {question}\n")

        # Load orchestrator
        with console.status(
            "[bold green]Loading knowledge graph...",
            spinner="dots"
        ):
            orch = get_orchestrator(data_dir)

        if not orch.graph.principles:
            console.print(
                "[yellow]⚠ Knowledge graph is empty. "
                "Ingest episodes first.[/yellow]"
            )
            raise SystemExit(1)

        # Parse disciplines
        parsed_disciplines = parse_disciplines(disciplines)

        # Query
        with console.status(
            "[bold green]Searching principles and generating answer...",
            spinner="dots"
        ):
            result = orch.ask(
                question=question,
                context=context,
                disciplines=parsed_disciplines
            )

        # Display answer
        console.print(Panel(result.answer, title="Answer", expand=False))

        # Display reasoning chain
        if result.reasoning_chain:
            chain_text = "\n".join(f"  {i}. {step}"
                                   for i, step in enumerate(result.reasoning_chain, 1))
            console.print(Panel(chain_text, title="Reasoning", expand=False))

        # Display metadata
        meta = Table(title="Query Metadata", show_header=False)
        meta.add_row("Principles Used", str(len(result.principles_used)))
        meta.add_row("Confidence", f"{result.confidence:.1%}")
        meta.add_row("Coherence", f"{result.coherence_with_corpus:.1%}")

        console.print(meta)

        if result.caveats:
            caveats_text = "\n".join(f"  • {c}" for c in result.caveats)
            console.print(Panel(caveats_text, title="Caveats", expand=False))

        console.print()

    except Exception as e:
        console.print(f"[bold red]Query failed: {e}[/bold red]")
        raise SystemExit(1)


# ── Command: graph ──────────────────────────────────────────────────────────

@cli.command()
@click.option("--format", type=click.Choice(["json", "graphml", "adjacency"]),
              default="json",
              help="Export format")
@click.option("--output", "output_path", type=click.Path(),
              help="Save to file instead of printing")
@click.option("--data-dir", type=click.Path(), default=None,
              help="Data directory override")
def graph(format, output_path, data_dir):
    """Export the knowledge graph.

    Example:
        noosphere graph --format json --output graph.json
    """
    try:
        with console.status(
            f"[bold green]Exporting graph as {format}...",
            spinner="dots"
        ):
            orch = get_orchestrator(data_dir)
            result = orch.export_graph(format=format, path=output_path)

        if output_path:
            console.print(f"\n[bold green]✓ Graph exported to [cyan]{output_path}[/cyan][/bold green]\n")
        else:
            # Show preview of exported data
            lines = result.split('\n')
            preview = '\n'.join(lines[:20])
            if len(lines) > 20:
                preview += f"\n... ({len(lines) - 20} more lines)"
            console.print(f"\n[bold]Graph Export Preview:[/bold]\n{preview}\n")

    except Exception as e:
        console.print(f"[bold red]Export failed: {e}[/bold red]")
        raise SystemExit(1)


# ── Command: coherence ──────────────────────────────────────────────────────

@cli.group("coherence", invoke_without_command=True)
@click.option("--report", is_flag=True,
              help="Show detailed coherence report")
@click.option("--principle-id", type=str, default=None,
              help="Analyze specific principle by ID")
@click.option("--data-dir", type=click.Path(), default=None,
              help="Data directory override")
@click.pass_context
def coherence(ctx, report, principle_id, data_dir):
    """Run coherence analysis on the knowledge graph.

    Example:
        noosphere coherence --report
    """
    if ctx.invoked_subcommand is not None:
        return
    _run_global_coherence(report, principle_id, data_dir)


def _run_global_coherence(report, principle_id, data_dir):
    try:
        with console.status(
            "[bold green]Running 6-layer coherence analysis...",
            spinner="dots"
        ):
            orch = get_orchestrator(data_dir)

            if not orch.graph.principles:
                console.print(
                    "[yellow]⚠ Graph has no principles.[/yellow]"
                )
                raise SystemExit(1)

            coh_report = orch.coherence_report()

        # Display results
        if report:
            # Show detailed report
            layer_names = {
                "s1_consistency": "Formal Consistency",
                "s2_argumentation": "Argumentation Theory",
                "s3_probabilistic": "Probabilistic Coherence",
                "s4_geometric": "Embedding-Geometric",
                "s5_compression": "Information-Theoretic",
                "s6_llm_judge": "LLM Judge",
            }

            layer_table = Table(title="Layer Scores", show_header=True)
            layer_table.add_column("Layer", style="cyan")
            layer_table.add_column("Score", justify="right")

            for key, value in coh_report.layer_scores.items():
                name = layer_names.get(key, key)
                score = value if isinstance(value, float) else 0.5
                layer_table.add_row(name, f"{score:.3f}")

            console.print(layer_table)

            if coh_report.contradictions_found:
                contra_table = Table(title="Detected Contradictions")
                contra_table.add_column("Principle A", style="yellow")
                contra_table.add_column("Principle B", style="yellow")
                contra_table.add_column("Severity", justify="right")

                for row in coh_report.contradictions_found[:10]:
                    a_id, b_id, severity = row.id_a, row.id_b, row.severity
                    contra_table.add_row(a_id[:8], b_id[:8], f"{severity:.2f}")

                console.print(contra_table)

        else:
            # Show summary
            summary = Table(title="Coherence Summary", show_header=False)
            summary.add_row("Composite Score", f"{coh_report.composite_score:.3f}")
            summary.add_row("Principles Analyzed", str(len(coh_report.principle_ids)))
            summary.add_row("Contradictions Found", str(len(coh_report.contradictions_found)))
            summary.add_row("Weakest Links", str(len(coh_report.weakest_links)))

            console.print(summary)

        console.print()

    except Exception as e:
        console.print(f"[bold red]Coherence analysis failed: {e}[/bold red]")
        raise SystemExit(1)


@coherence.command("audit-local")
@click.option("--conclusion-id", required=True, type=str,
              help="Stored Conclusion id to audit through scaled coherence")
def coherence_audit_local(conclusion_id):
    """Run the scaled local coherence check for one stored conclusion."""
    try:
        from noosphere.coherence.scheduler import run_scaled_coherence_check

        store = _store_from_settings()
        conclusion = store.get_conclusion(conclusion_id)
        if conclusion is None:
            click.echo(
                json.dumps(
                    {"ok": False, "error": f"Unknown conclusion: {conclusion_id}"},
                    indent=2,
                ),
                err=True,
            )
            raise SystemExit(2)
        report = run_scaled_coherence_check(conclusion, store)
        click.echo(report.model_dump_json(indent=2))
    except SystemExit:
        raise
    except Exception as e:
        console.print(f"[bold red]Local coherence audit failed: {e}[/bold red]")
        raise SystemExit(1)


# ── Command: evolution ──────────────────────────────────────────────────────

@cli.command()
@click.option("--principle", "principle_id", type=str, default=None,
              help="Filter by specific principle ID")
@click.option("--start", "start_date", type=str, default=None,
              help="Start date (YYYY-MM-DD)")
@click.option("--end", "end_date", type=str, default=None,
              help="End date (YYYY-MM-DD)")
@click.option("--data-dir", type=click.Path(), default=None,
              help="Data directory override")
def evolution(principle_id, start_date, end_date, data_dir):
    """Track temporal evolution of principles.

    Example:
        noosphere evolution --start 2026-01-01 --end 2026-04-11
    """
    try:
        # Parse dates
        parsed_start = parse_date(start_date) if start_date else None
        parsed_end = parse_date(end_date) if end_date else None

        with console.status(
            "[bold green]Analyzing temporal evolution...",
            spinner="dots"
        ):
            orch = get_orchestrator(data_dir)
            evo = orch.evolution_report(
                start_date=parsed_start,
                end_date=parsed_end
            )

        if not evo:
            console.print("[yellow]⚠ No evolution data available.[/yellow]")
            raise SystemExit(1)

        # Filter by principle if specified
        if principle_id:
            evo = {k: v for k, v in evo.items() if k == principle_id}
            if not evo:
                console.print(
                    f"[yellow]⚠ Principle {principle_id} not found.[/yellow]"
                )
                raise SystemExit(1)

        # Display results
        evo_table = Table(
            title=f"Evolution ({len(evo)} principles)",
            show_header=True
        )
        evo_table.add_column("Principle ID", style="cyan")
        evo_table.add_column("First Seen", style="green")
        evo_table.add_column("Conviction Δ", justify="right")
        evo_table.add_column("Mentions", justify="right")
        evo_table.add_column("Drift", justify="right")

        for pid, data in sorted(evo.items(), key=lambda x: x[1]["conviction_change"], reverse=True)[:20]:
            first = data["first_appearance"]
            conviction_change = data["conviction_change"]
            color = "green" if conviction_change > 0 else "yellow" if conviction_change < 0 else "white"
            drift = data.get("embedding_drift")
            drift_str = f"{drift:.3f}" if drift is not None else "N/A"

            evo_table.add_row(
                pid[:8],
                str(first),
                f"[{color}]{conviction_change:+.2f}[/{color}]",
                str(data["mention_count"]),
                drift_str
            )

        console.print(evo_table)
        console.print()

    except Exception as e:
        console.print(f"[bold red]Evolution analysis failed: {e}[/bold red]")
        raise SystemExit(1)


# ── Command: stats ──────────────────────────────────────────────────────────

@cli.command()
@click.option("--data-dir", type=click.Path(), default=None,
              help="Data directory override")
def stats(data_dir):
    """Display system statistics.

    Example:
        noosphere stats
    """
    try:
        with console.status(
            "[bold green]Computing statistics...",
            spinner="dots"
        ):
            orch = get_orchestrator(data_dir)
            stats_dict = orch.get_stats()

        # Display stats
        table = Table(title="Noosphere Statistics", show_header=False)
        table.add_row("Methodological Principles", str(stats_dict["methodological_principles"]))
        table.add_row("Substantive Conclusions", str(stats_dict["substantive_conclusions"]))
        table.add_row("Claims in Graph", str(stats_dict["claims_in_graph"]))
        table.add_row("Relationships", str(stats_dict["relationships"]))
        table.add_row("Episodes", str(stats_dict["episodes"]))
        table.add_row("Temporal Snapshots", str(stats_dict["temporal_snapshots"]))
        table.add_row("Founders", str(stats_dict["founders"]))
        table.add_row("Input Sources", str(stats_dict["input_sources"]))
        table.add_row("Average Coherence", f"{stats_dict['avg_coherence']:.3f}")
        table.add_row("Average Conviction", f"{stats_dict['avg_conviction']:.3f}")

        console.print(table)
        console.print()

    except Exception as e:
        console.print(f"[bold red]Stats failed: {e}[/bold red]")
        raise SystemExit(1)


# ── Command: search ────────────────────────────────────────────────────────

@cli.command()
@click.argument("query", type=str)
@click.option("--k", type=int, default=5,
              help="Number of results to return")
@click.option("--data-dir", type=click.Path(), default=None,
              help="Data directory override")
def search(query, k, data_dir):
    """Semantic search over principles.

    Example:
        noosphere search "optimal decision making" --k 10
    """
    try:
        with console.status(
            "[bold green]Searching principles...",
            spinner="dots"
        ):
            orch = get_orchestrator(data_dir)
            results = orch.search_principles(query, k=k)

        if not results:
            console.print("[yellow]⚠ No results found.[/yellow]")
            raise SystemExit(1)

        # Display results
        table = Table(title=f"Search Results ({len(results)})", show_header=True)
        table.add_column("Score", justify="right", style="cyan")
        table.add_column("Principle", style="white")

        for principle, score in results:
            # Truncate principle text
            text = principle.text[:80]
            if len(principle.text) > 80:
                text += "..."

            table.add_row(f"{score:.3f}", text)

        console.print(table)
        console.print()

    except Exception as e:
        console.print(f"[bold red]Search failed: {e}[/bold red]")
        raise SystemExit(1)


# ── Command: contradictions ────────────────────────────────────────────────

@cli.command()
@click.option("--data-dir", type=click.Path(), default=None,
              help="Data directory override")
def contradictions(data_dir):
    """Find all contradictions in the knowledge graph.

    Example:
        noosphere contradictions
    """
    try:
        with console.status(
            "[bold green]Detecting contradictions...",
            spinner="dots"
        ):
            orch = get_orchestrator(data_dir)
            contras = orch.get_contradictions()

        if not contras:
            console.print(
                "[bold green]✓ No contradictions detected.[/bold green]"
            )
            raise SystemExit(0)

        # Display contradictions
        table = Table(title=f"Contradictions ({len(contras)})", show_header=True)
        table.add_column("Principle A", style="yellow")
        table.add_column("Principle B", style="yellow")
        table.add_column("Severity", justify="right", style="red")

        for a_principle, b_principle, severity in sorted(contras, key=lambda x: x[2], reverse=True):
            a_text = (a_principle.text[:40] + "...") if len(a_principle.text) > 40 else a_principle.text
            b_text = (b_principle.text[:40] + "...") if len(b_principle.text) > 40 else b_principle.text

            table.add_row(a_text, b_text, f"{severity:.2f}")

        console.print(table)
        console.print()

    except Exception as e:
        console.print(f"[bold red]Contradiction detection failed: {e}[/bold red]")
        raise SystemExit(1)


# ── Command: principles ────────────────────────────────────────────────────

@cli.command()
@click.option("--min-conviction", type=float, default=0.0,
              help="Filter by minimum conviction score (0-1)")
@click.option("--discipline", "disciplines", type=str, default="",
              help="Filter by comma-separated disciplines")
@click.option("--limit", type=int, default=20,
              help="Maximum principles to show")
@click.option("--data-dir", type=click.Path(), default=None,
              help="Data directory override")
def principles(min_conviction, disciplines, limit, data_dir):
    """List principles with optional filters.

    Example:
        noosphere principles --min-conviction 0.7 --discipline "AI,Philosophy"
    """
    try:
        # Parse disciplines
        parsed_disciplines = parse_disciplines(disciplines)

        with console.status(
            "[bold green]Loading principles...",
            spinner="dots"
        ):
            orch = get_orchestrator(data_dir)

        # Filter principles
        filtered = []
        for p in orch.graph.principles.values():
            if p.conviction_score < min_conviction:
                continue
            if parsed_disciplines and not any(
                d in p.disciplines for d in parsed_disciplines
            ):
                continue
            filtered.append(p)

        if not filtered:
            console.print(
                "[yellow]⚠ No principles match the criteria.[/yellow]"
            )
            raise SystemExit(1)

        # Sort by conviction
        filtered.sort(key=lambda p: p.conviction_score, reverse=True)

        # Display table
        table = Table(
            title=f"Principles ({len(filtered)} total)",
            show_header=True
        )
        table.add_column("Conviction", justify="right", style="cyan")
        table.add_column("Principle", style="white")
        table.add_column("Disciplines", style="green")

        for principle in filtered[:limit]:
            disciplines_str = ", ".join(d.value for d in principle.disciplines[:2])
            if len(principle.disciplines) > 2:
                disciplines_str += "..."

            table.add_row(
                f"{principle.conviction_score:.2f}",
                principle.text[:60] + ("..." if len(principle.text) > 60 else ""),
                disciplines_str
            )

        console.print(table)
        console.print()

    except Exception as e:
        console.print(f"[bold red]Failed to list principles: {e}[/bold red]")
        raise SystemExit(1)


# ── Command: calibration ──────────────────────────────────────────────────

@cli.command()
@click.option("--data-dir", type=click.Path(), default=None,
              help="Data directory override")
def calibration(data_dir):
    """Show calibration feedback: how well do methods track reality?

    Transforms accuracy data from the Conclusions Registry into
    methodological observations — the bridge between substance and method.

    Example:
        noosphere calibration
    """
    try:
        with console.status(
            "[bold green]Analyzing calibration data...",
            spinner="dots"
        ):
            orch = get_orchestrator(data_dir)
            feedback = orch.calibration_feedback()

        if not feedback:
            console.print(
                "[yellow]⚠ No resolved conclusions to calibrate against. "
                "Use 'noosphere conclusions resolve' to record outcomes.[/yellow]"
            )
            raise SystemExit(1)

        console.print(
            Panel(
                "Methodological feedback derived from substantive "
                "prediction accuracy. These observations describe HOW "
                "methods perform, not WHAT is true.",
                title="Calibration Feedback",
                expand=False,
            )
        )

        for i, fb in enumerate(feedback, 1):
            text = fb.get("text", "")
            confidence = fb.get("confidence", 0.0)
            source = fb.get("source", "")

            style = "green" if confidence >= 0.7 else "yellow" if confidence >= 0.4 else "red"
            console.print(
                f"\n  [{style}]{i}. [{confidence:.0%} confidence][/{style}]"
            )
            console.print(f"     {text}")
            if source:
                console.print(f"     [dim]Source: {source}[/dim]")

        console.print()

    except Exception as e:
        console.print(f"[bold red]Calibration failed: {e}[/bold red]")
        raise SystemExit(1)


# ── Command: conclusions ─────────────────────────────────────────────────

@cli.command()
@click.option("--method", type=str, default=None,
              help="Filter by reasoning method used")
@click.option("--domain", type=str, default=None,
              help="Filter by domain")
@click.option("--unresolved", is_flag=True,
              help="Show only unresolved conclusions")
@click.option("--limit", type=int, default=20,
              help="Maximum conclusions to show")
@click.option("--data-dir", type=click.Path(), default=None,
              help="Data directory override")
def conclusions(method, domain, unresolved, limit, data_dir):
    """List substantive conclusions tracked for calibration.

    These are claims routed OUT of the brain — they describe what the
    founders believe is true. Tracked here so their accuracy can feed
    back into methodological evaluation.

    Example:
        noosphere conclusions --method analogy --unresolved
    """
    try:
        with console.status(
            "[bold green]Loading conclusions...",
            spinner="dots"
        ):
            orch = get_orchestrator(data_dir)
            all_conclusions = list(orch.conclusions.conclusions.values())

        if not all_conclusions:
            console.print(
                "[yellow]⚠ No substantive conclusions recorded yet.[/yellow]"
            )
            raise SystemExit(1)

        # Apply filters
        filtered = all_conclusions
        if method:
            filtered = [c for c in filtered if method.lower() in (c.method_used or "").lower()]
        if domain:
            filtered = [c for c in filtered if domain.lower() in (c.domain or "").lower()]
        if unresolved:
            filtered = [c for c in filtered if c.resolved is None]

        if not filtered:
            console.print(
                "[yellow]⚠ No conclusions match the filters.[/yellow]"
            )
            raise SystemExit(1)

        # Display table
        table = Table(
            title=f"Substantive Conclusions ({len(filtered)} of {len(all_conclusions)})",
            show_header=True,
        )
        table.add_column("ID", style="dim", max_width=8)
        table.add_column("Conclusion", style="white", max_width=50)
        table.add_column("Method", style="cyan")
        table.add_column("Domain", style="green")
        table.add_column("Status", justify="center")

        for c in filtered[:limit]:
            status = "[green]Resolved[/green]" if c.resolved is not None else "[yellow]Open[/yellow]"
            text = c.text[:50] + ("..." if len(c.text) > 50 else "")
            table.add_row(
                c.id[:8] if hasattr(c, "id") else "?",
                text,
                c.method_used or "?",
                c.domain or "?",
                status,
            )

        console.print(table)
        console.print()

    except Exception as e:
        console.print(f"[bold red]Conclusions list failed: {e}[/bold red]")
        raise SystemExit(1)


# ── Command: classify ────────────────────────────────────────────────────

@cli.command()
@click.argument("text", type=str)
@click.option("--data-dir", type=click.Path(), default=None,
              help="Data directory override")
def classify(text, data_dir):
    """Classify a single claim as methodological or substantive.

    Useful for testing the discourse classifier on individual statements.

    Example:
        noosphere classify "We should always look for base rates first"
    """
    try:
        with console.status(
            "[bold green]Classifying...",
            spinner="dots"
        ):
            orch = get_orchestrator(data_dir)
            results = orch.classifier.classify_batch([text])

        if not results:
            console.print("[red]Classification failed.[/red]")
            raise SystemExit(1)

        cc = results[0]
        type_colors = {
            "METHODOLOGICAL": "green",
            "META_METHODOLOGICAL": "bold green",
            "SUBSTANTIVE": "yellow",
            "MIXED": "cyan",
            "NON_PROPOSITIONAL": "dim",
        }
        color = type_colors.get(cc.discourse_type.value, "white")

        console.print(f"\n  Claim: {text}")
        console.print(f"  Type:  [{color}]{cc.discourse_type.value}[/{color}]")
        console.print(f"  Confidence: {cc.confidence:.0%}")
        if cc.method_attribution:
            console.print(f"  Method Attribution: {cc.method_attribution}")
        if cc.methodological_content:
            console.print(f"  Methodological Component: {cc.methodological_content}")
        if cc.substantive_content:
            console.print(f"  Substantive Component: {cc.substantive_content}")
        if cc.decomposition_notes:
            console.print(f"  Notes: {cc.decomposition_notes}")
        console.print()

    except Exception as e:
        console.print(f"[bold red]Classification failed: {e}[/bold red]")
        raise SystemExit(1)


# ── Command: ingest-written ──────────────────────────────────────────────

@cli.command("ingest-written")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--author", type=str, required=True,
              help="Name of the founder who wrote this")
@click.option("--title", type=str, default="",
              help="Document title")
@click.option("--date", "input_date", type=str, default=None,
              help="Date written (YYYY-MM-DD, defaults to today)")
@click.option("--description", type=str, default="",
              help="Brief description of the document")
@click.option("--type", "source_type", type=click.Choice(["written", "annotation", "external"]),
              default="written",
              help="Type of written input")
@click.option("--data-dir", type=click.Path(), default=None,
              help="Data directory override")
def ingest_written(file_path, author, title, input_date, description, source_type, data_dir):
    """Ingest a written document from a specific founder.

    Supports .txt, .md, .pdf, and .docx files. Every claim extracted
    is attributed to the named author and routed through the same
    methodology/substance classification pipeline as transcripts.

    Example:
        noosphere ingest-written essay.md --author "Michael" \\
          --title "On Meta-Methodology" --type written
    """
    try:
        console.print(
            f"\n[bold]Ingesting written input[/bold] by [cyan]{author}[/cyan]",
        )

        parsed_date = parse_date(input_date) if input_date else None

        with console.status(
            "[bold green]Processing document...",
            spinner="dots"
        ):
            orch = get_orchestrator(data_dir)
            result = orch.ingest_written_input(
                file_path=file_path,
                author_name=author,
                title=title,
                input_date=parsed_date,
                description=description,
                source_type=source_type,
            )

        # Display summary
        summary = Table(title="Written Input Summary", show_header=False)
        summary.add_row("Author", result.get("author", author))
        summary.add_row("Claims Extracted", str(result.get("claims", 0)))
        summary.add_row("Methodological", str(result.get("methodological", 0)))
        summary.add_row("Substantive", str(result.get("substantive", 0)))
        summary.add_row("Principles Distilled", str(result.get("principles_distilled", 0)))

        console.print(summary)
        console.print(
            "\n[bold green]✓ Written input ingestion complete[/bold green]\n"
        )

    except Exception as e:
        console.print(f"[bold red]Written ingestion failed: {e}[/bold red]")
        raise SystemExit(1)


# ── Command: founders ────────────────────────────────────────────────────

@cli.command()
@click.option("--name", type=str, default=None,
              help="Show specific founder's profile")
@click.option("--convergence", is_flag=True,
              help="Show inter-founder convergence/divergence analysis")
@click.option("--authorship", is_flag=True,
              help="Show principle authorship distribution")
@click.option("--data-dir", type=click.Path(), default=None,
              help="Data directory override")
def founders(name, convergence, authorship, data_dir):
    """Manage and analyse founder profiles.

    With no flags, lists all registered founders and their stats.
    Use --name to see a specific founder's intellectual profile.
    Use --convergence to see how founders are aligning or diverging.
    Use --authorship to see principle contribution distribution.

    Example:
        noosphere founders
        noosphere founders --name "Michael"
        noosphere founders --convergence
    """
    try:
        with console.status(
            "[bold green]Loading founder data...",
            spinner="dots"
        ):
            orch = get_orchestrator(data_dir)

        if name:
            # Single founder profile
            report = orch.founder_report(founder_name=name)
            if "error" in report:
                console.print(f"[red]{report['error']}[/red]")
                raise SystemExit(1)

            table = Table(title=f"Founder Profile: {name}", show_header=False)
            for key, val in report.items():
                if key == "id":
                    continue
                label = key.replace("_", " ").title()
                table.add_row(label, str(val))
            console.print(table)

        elif convergence:
            # Convergence/divergence analysis
            report = orch.founder_report()
            if report.get("status") == "insufficient_data":
                console.print(
                    "[yellow]⚠ Need embedding data from at least 2 founders.[/yellow]"
                )
                raise SystemExit(1)

            console.print(Panel(
                f"Overall Convergence: [bold]{report['overall_convergence']:.3f}[/bold]\n"
                f"Most Aligned: {report['most_aligned']['pair'][0]} ↔ "
                f"{report['most_aligned']['pair'][1]} "
                f"({report['most_aligned']['similarity']:.3f})\n"
                f"Most Divergent: {report['most_divergent']['pair'][0]} ↔ "
                f"{report['most_divergent']['pair'][1]} "
                f"({report['most_divergent']['similarity']:.3f})",
                title="Convergence Analysis",
                expand=False,
            ))

            if report.get("per_founder_isolation"):
                iso_table = Table(title="Per-Founder Isolation", show_header=True)
                iso_table.add_column("Founder", style="cyan")
                iso_table.add_column("Isolation", justify="right")
                for fname, iso in sorted(
                    report["per_founder_isolation"].items(),
                    key=lambda x: -x[1]
                ):
                    color = "red" if iso > 0.3 else "yellow" if iso > 0.1 else "green"
                    iso_table.add_row(fname, f"[{color}]{iso:.4f}[/{color}]")
                console.print(iso_table)

        elif authorship:
            # Principle authorship
            report = orch.principle_authorship()
            if not report.get("per_founder"):
                console.print("[yellow]⚠ No authorship data available.[/yellow]")
                raise SystemExit(1)

            table = Table(title="Principle Authorship", show_header=True)
            table.add_column("Founder", style="cyan")
            table.add_column("Influence", justify="right")
            table.add_column("Principles", justify="right")
            table.add_column("Method %", justify="right")

            for fname, data in sorted(
                report["per_founder"].items(),
                key=lambda x: -x[1]["total_influence"]
            ):
                meth = data.get("methodological_orientation")
                meth_str = f"{meth:.0%}" if meth is not None else "?"
                table.add_row(
                    fname,
                    f"{data['total_influence']:.2f}",
                    str(data["principle_count"]),
                    meth_str,
                )
            console.print(table)
            console.print(
                f"\n  Collaborative: {report['collaborative_principles']} | "
                f"Individual: {report['individual_principles']} | "
                f"Total: {report['total_principles']}"
            )

        else:
            # List all founders
            all_founders = orch.founder_registry.all_founders()
            if not all_founders:
                console.print(
                    "[yellow]⚠ No founders registered. "
                    "Ingest episodes or written inputs first.[/yellow]"
                )
                raise SystemExit(1)

            table = Table(title=f"Founders ({len(all_founders)})", show_header=True)
            table.add_column("Name", style="cyan")
            table.add_column("Claims", justify="right")
            table.add_column("Written", justify="right")
            table.add_column("Method %", justify="right")
            table.add_column("Principles", justify="right")
            table.add_column("Last Active", style="dim")

            for fp in sorted(all_founders, key=lambda f: -f.claim_count):
                table.add_row(
                    fp.name,
                    str(fp.claim_count),
                    str(fp.written_input_count),
                    f"{fp.methodological_orientation:.0%}",
                    str(len(fp.principle_ids)),
                    fp.last_active.isoformat() if fp.last_active else "—",
                )
            console.print(table)

        console.print()

    except Exception as e:
        console.print(f"[bold red]Founder analysis failed: {e}[/bold red]")
        raise SystemExit(1)


# ── Command: register-founder ────────────────────────────────────────────

@cli.command("register-founder")
@click.argument("name", type=str)
@click.option("--domains", type=str, default="",
              help="Comma-separated primary domains")
@click.option("--data-dir", type=click.Path(), default=None,
              help="Data directory override")
def register_founder(name, domains, data_dir):
    """Pre-register a founder before ingesting their content.

    Example:
        noosphere register-founder "Michael" --domains "Philosophy,AI,Strategy"
    """
    try:
        orch = get_orchestrator(data_dir)
        parsed_domains = parse_disciplines(domains) if domains else []
        fp = orch.founder_registry.register(
            name=name,
            primary_domains=parsed_domains,
        )
        orch.founder_registry.save()
        console.print(
            f"\n[bold green]✓ Registered founder: {name} ({fp.id[:8]}...)[/bold green]\n"
        )
    except Exception as e:
        console.print(f"[bold red]Registration failed: {e}[/bold red]")
        raise SystemExit(1)


# ── Command: synthesis ──────────────────────────────────────────────────────

@cli.command("synthesis")
@click.option("--manuscript", is_flag=True, help="Show the current manuscript")
@click.option("--questions", type=int, default=None,
              help="Show next questions generated after episode N")
@click.option("--sources", type=int, default=None,
              help="Show source recommendations for episode N")
@click.option("--contradictions", is_flag=True,
              help="Generate a fresh contradiction report")
@click.option("--add-source", type=str, default=None,
              help='Add a source to the catalogue: "Author|Title|Year|Topic"')
@click.option("--data-dir", type=click.Path(), default=None,
              help="Data directory override")
def synthesis(manuscript, questions, sources, contradictions, add_source, data_dir):
    """Access post-discussion synthesis outputs.

    Examples:
        noosphere synthesis --manuscript
        noosphere synthesis --questions 5
        noosphere synthesis --sources 5
        noosphere synthesis --contradictions
        noosphere synthesis --add-source "Quine|Two Dogmas of Empiricism|1951|Analytic-synthetic distinction..."
    """
    try:
        orch = get_orchestrator(data_dir)
        synth_dir = orch.data_dir / "synthesis"

        if add_source:
            parts = add_source.split("|")
            if len(parts) != 4:
                console.print("[red]Format: 'Author|Title|Year|Topic description'[/red]")
                raise SystemExit(1)
            author, title, year, topic = parts
            orch.synthesis.add_source(
                title=title.strip(),
                author=author.strip(),
                year=int(year.strip()),
                topic=topic.strip(),
            )
            console.print(f"\n[bold green]✓ Added source: {author.strip()} — {title.strip()}[/bold green]\n")
            return

        if manuscript:
            path = synth_dir / "manuscript.md"
            if not path.exists():
                console.print("[yellow]No manuscript yet. Ingest an episode first.[/yellow]")
                return
            content = path.read_text()
            console.print(Panel(
                content[:5000] + ("\n\n[dim]... (truncated)[/dim]" if len(content) > 5000 else ""),
                title="[bold]Manuscript[/bold]",
                border_style="blue",
            ))
            console.print(f"\n[dim]Full manuscript: {path} ({len(content)} chars)[/dim]\n")
            return

        if questions is not None:
            import glob
            pattern = str(synth_dir / f"next_questions_after_ep{questions}.md")
            matches = glob.glob(pattern)
            if not matches:
                console.print(f"[yellow]No questions found for episode {questions}[/yellow]")
                return
            content = Path(matches[0]).read_text()
            console.print(Panel(content, title=f"[bold]Next Questions (after ep {questions})[/bold]", border_style="green"))
            return

        if sources is not None:
            pattern = str(synth_dir / f"sources_ep{sources}.md")
            import glob
            matches = glob.glob(pattern)
            if not matches:
                console.print(f"[yellow]No source recommendations for episode {sources}[/yellow]")
                return
            content = Path(matches[0]).read_text()
            console.print(Panel(content, title=f"[bold]Source Recommendations (ep {sources})[/bold]", border_style="magenta"))
            return

        if contradictions:
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
                progress.add_task("Generating contradiction report...", total=None)
                contras = orch.get_contradictions()
                report = orch.synthesis.generate_contradiction_report(contras)
            console.print(Panel(
                report[:4000] + ("\n\n[dim]... (truncated)[/dim]" if len(report) > 4000 else ""),
                title="[bold]Contradiction Report[/bold]",
                border_style="red",
            ))
            return

        # Default: show what synthesis outputs exist
        console.print("\n[bold]Synthesis Outputs[/bold]\n")
        if synth_dir.exists():
            files = sorted(synth_dir.iterdir())
            if files:
                for f in files:
                    size = f.stat().st_size
                    console.print(f"  {f.name} ({size:,} bytes)")
            else:
                console.print("  [dim]No synthesis outputs yet. Ingest an episode to generate.[/dim]")
        else:
            console.print("  [dim]No synthesis directory yet. Ingest an episode to generate.[/dim]")
        console.print()

    except Exception as e:
        console.print(f"[bold red]Synthesis error: {e}[/bold red]")
        raise SystemExit(1)


# ── Command: research ───────────────────────────────────────────────────────

@cli.command("research")
@click.option("--episode", "-e", type=int, default=None,
              help="Show research brief for episode N")
@click.option("--generate", "-g", is_flag=True,
              help="Force-generate a fresh research brief from the current graph state")
@click.option("--list", "list_briefs", is_flag=True,
              help="List all research briefs")
@click.option("--json-out", is_flag=True,
              help="Output the brief as JSON instead of Markdown")
@click.option("--data-dir", type=click.Path(), default=None,
              help="Data directory override")
def research(episode, generate, list_briefs, json_out, data_dir):
    """Access research briefs — topic and reading suggestions for next discussions.

    Examples:
        noosphere research --list
        noosphere research --episode 5
        noosphere research --generate
    """
    import glob as glob_mod

    try:
        orch = get_orchestrator(data_dir)
        briefs_dir = orch.data_dir / "synthesis" / "research_briefs"

        if list_briefs:
            console.print("\n[bold]Research Briefs[/bold]\n")
            if briefs_dir.exists():
                files = sorted(briefs_dir.iterdir())
                if files:
                    for f in files:
                        size = f.stat().st_size
                        console.print(f"  {f.name} ({size:,} bytes)")
                else:
                    console.print("  [dim]No research briefs yet. Ingest an episode to generate.[/dim]")
            else:
                console.print("  [dim]No research briefs directory. Ingest an episode to generate.[/dim]")
            console.print()
            return

        if episode is not None:
            pattern = str(briefs_dir / f"research_brief_ep{episode}.md")
            matches = glob_mod.glob(pattern)
            if not matches:
                console.print(f"[yellow]No research brief for episode {episode}[/yellow]")
                return

            content = Path(matches[0]).read_text()

            if json_out:
                console.print(content)
            else:
                console.print(Panel(
                    content[:6000] + ("\n\n[dim]... (truncated)[/dim]" if len(content) > 6000 else ""),
                    title=f"[bold]Research Brief (Episode {episode})[/bold]",
                    border_style="cyan",
                ))
            return

        if generate:
            from noosphere.models import Episode as EpisodeModel
            from datetime import date as date_cls

            # Use the most recent episode, or create a synthetic one
            all_principles = list(orch.graph.principles.values())
            if not all_principles:
                console.print("[yellow]No principles in the graph yet. Ingest content first.[/yellow]")
                return

            # Find latest episode number
            ep_nums = [
                int(f.stem.split("ep")[-1])
                for f in (orch.data_dir / "synthesis").glob("summary_ep*.md")
            ] if (orch.data_dir / "synthesis").exists() else []

            ep_num = max(ep_nums) if ep_nums else 0

            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
                progress.add_task("Generating research brief (this may take a moment)...", total=None)

                ep = EpisodeModel(
                    number=ep_num,
                    title="Latest state",
                    date=date_cls.today(),
                    speakers=[],
                )
                contradictions = orch.graph.get_contradictions() if hasattr(orch.graph, 'get_contradictions') else []
                claims = list(orch.graph.claims.values())[:60] if hasattr(orch.graph, 'claims') else []

                brief = orch.research_advisor.generate_research_brief(
                    episode=ep,
                    claims=claims,
                    new_principles=all_principles[:15],
                    contradictions=contradictions,
                    all_principles=all_principles,
                )

            if json_out:
                import json as json_mod
                console.print(json_mod.dumps(orch.research_advisor.brief_to_dict(brief), indent=2))
            else:
                console.print(f"\n[bold green]✓ Research brief generated: {len(brief.topics)} topics[/bold green]")
                for i, t in enumerate(brief.topics, 1):
                    prio_color = {"high": "red", "medium": "yellow", "exploratory": "green"}.get(t.priority, "white")
                    console.print(f"\n  [{prio_color}]{i}. {t.title}[/{prio_color}]")
                    console.print(f"     [dim]{t.philosophical_question}[/dim]")
                    console.print(f"     [dim]Readings: {len(t.readings)} | Empirical anchors: {len(t.empirical_anchors)}[/dim]")
                console.print(f"\n  [dim]Full brief saved to: {orch.data_dir / 'synthesis' / 'research_briefs'}[/dim]\n")
            return

        # Default: show help
        console.print("\n[bold]Research Advisor[/bold]")
        console.print("  Use --list to see available briefs")
        console.print("  Use --episode N to view a specific brief")
        console.print("  Use --generate to create a fresh brief from current graph state")
        console.print()

    except Exception as e:
        console.print(f"[bold red]Research advisor error: {e}[/bold red]")
        raise SystemExit(1)


# ── Command: equities ──────────────────────────────────────────────────────


@click.group("equities")
def equities_cli() -> None:
    """Equity-track ingestion and paper trading."""


@equities_cli.group("ingest")
def equities_ingest_cli() -> None:
    """Run equity ingestors."""


@equities_cli.group("paper")
def equities_paper_cli() -> None:
    """Paper-trading commands (Alpaca paper environment)."""


@equities_ingest_cli.command("alpaca")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Run against an in-memory store; no durable rows are written.",
)
def equities_ingest_alpaca(dry_run: bool) -> None:
    """Ingest tradeable US equities + ETFs from Alpaca."""
    from dataclasses import asdict

    from noosphere.equities.alpaca_ingestor import ingest_once
    from noosphere.equities.config import AlpacaConfig
    from noosphere.store import Store

    cfg = AlpacaConfig.from_env()
    store = (
        Store.from_database_url("sqlite:///:memory:")
        if dry_run
        else _store_from_settings()
    )
    result = asyncio.run(ingest_once(store, config=cfg))
    click.echo(
        json.dumps(
            {
                "ok": not result.errors,
                "dry_run": dry_run,
                "configured": cfg.is_configured,
                "accepted_symbols": cfg.accepted_symbols or ["*"],
                "result": asdict(result),
            },
            indent=2,
            default=str,
        )
    )


@equities_paper_cli.command("status")
def equities_paper_status() -> None:
    """Print Alpaca paper account + currently-open paper positions."""
    from noosphere.equities._alpaca_client import AlpacaClient
    from noosphere.equities.config import AlpacaConfig
    from noosphere.models import EquityPosition, EquityPositionMode, EquityPositionStatus

    cfg = AlpacaConfig.from_env()
    if not cfg.is_configured:
        click.echo(
            json.dumps({"ok": False, "error": "ALPACA_NOT_CONFIGURED"}, indent=2),
            err=True,
        )
        raise SystemExit(2)

    store = _store_from_settings()

    async def _run() -> dict[str, object]:
        client = AlpacaClient(
            api_base=cfg.api_base,
            data_base=cfg.data_base,
            api_key_id=cfg.api_key_id,
            api_secret_key=cfg.api_secret_key,
            timeout_s=cfg.request_timeout_s,
        )
        try:
            account = await client.get_account()
            broker_positions = await client.list_positions()
        finally:
            await client.aclose()
        return {"account": account, "broker_positions": broker_positions}

    payload = asyncio.run(_run())

    from sqlmodel import select as _select

    with store.session() as session:
        open_paper = list(
            session.exec(
                _select(EquityPosition)
                .where(EquityPosition.mode == EquityPositionMode.PAPER.value)
                .where(EquityPosition.status == EquityPositionStatus.OPEN.value)
            ).all()
        )
    local_view = [
        {
            "id": pos.id,
            "signal_id": pos.signal_id,
            "instrument_id": pos.instrument_id,
            "side": _enum_value(pos.side),
            "qty": str(pos.qty),
            "entry_price": str(pos.entry_price),
        }
        for pos in open_paper
    ]

    click.echo(
        json.dumps(
            {"ok": True, "open_paper_positions": local_view, **payload},
            indent=2,
            default=str,
        )
    )


@equities_paper_cli.command("close")
@click.argument("position_id")
def equities_paper_close(position_id: str) -> None:
    """Close a paper position by submitting the offsetting market order."""
    from noosphere.equities._alpaca_client import AlpacaClient
    from noosphere.equities.config import AlpacaConfig
    from noosphere.equities.paper_trader import close_paper_position

    cfg = AlpacaConfig.from_env()
    if not cfg.is_configured:
        click.echo(
            json.dumps({"ok": False, "error": "ALPACA_NOT_CONFIGURED"}, indent=2),
            err=True,
        )
        raise SystemExit(2)

    store = _store_from_settings()

    async def _run():
        client = AlpacaClient(
            api_base=cfg.api_base,
            data_base=cfg.data_base,
            api_key_id=cfg.api_key_id,
            api_secret_key=cfg.api_secret_key,
            timeout_s=cfg.request_timeout_s,
        )
        try:
            return await close_paper_position(store, position_id, client=client)
        finally:
            await client.aclose()

    pos = asyncio.run(_run())
    click.echo(
        json.dumps(
            {
                "ok": True,
                "position_id": pos.id,
                "status": _enum_value(pos.status),
                "exit_price": str(pos.exit_price) if pos.exit_price is not None else None,
                "realized_pnl_usd": (
                    str(pos.realized_pnl_usd)
                    if pos.realized_pnl_usd is not None
                    else None
                ),
            },
            indent=2,
            default=str,
        )
    )


def _enum_value(value: object) -> str:
    return str(value.value if hasattr(value, "value") else value)


# ── Command: quantitative ──────────────────────────────────────────────────


@click.group("quantitative")
def quantitative_cli() -> None:
    """Quantitative-formalisation runner (prompt 63).

    Pulls APPROVED ``QuantitativeFormalisation`` specs from the store,
    runs the numerical tests they describe, and writes one
    ``QuantitativeTestResult`` per pass plus plots under
    ``benchmarks/quantitative/<formalisation_id>/<run_stamp>/``.
    """


@quantitative_cli.command("run")
@click.option(
    "--formalisation",
    "formalisation_id",
    type=str,
    default=None,
    help="Run a single APPROVED formalisation by id.",
)
@click.option(
    "--all",
    "run_all",
    is_flag=True,
    default=False,
    help="Run every APPROVED formalisation in the store.",
)
@click.option(
    "--data-dir",
    "data_dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Override the file:// data root (defaults to noosphere/data/quantitative/).",
)
def quantitative_run(
    formalisation_id: Optional[str],
    run_all: bool,
    data_dir: Optional[Path],
) -> None:
    """Run one or every APPROVED quantitative formalisation."""
    from noosphere.forecasts.scheduler import database_url_from_env
    from noosphere.quantitative.runner import QuantitativeRunner
    from noosphere.store import Store

    if not formalisation_id and not run_all:
        raise click.UsageError("pass --formalisation <id> or --all")
    store = Store.from_database_url(database_url_from_env())
    runner = QuantitativeRunner(store, data_dir=data_dir)
    results = []
    if run_all:
        approved = store.list_quantitative_formalisations(status="APPROVED")
        for f in approved:
            results.append(asyncio.run(runner.run(f.id)))
    else:
        results.append(asyncio.run(runner.run(formalisation_id)))
    click.echo(
        json.dumps(
            [
                {
                    "formalisation_id": r.formalisation_id,
                    "run_stamp": r.run_stamp,
                    "status": r.status.value if hasattr(r.status, "value") else r.status,
                    "test_count": len(r.test_outputs),
                    "artifacts_path": r.artifacts_path,
                    "threshold_crossings": r.threshold_crossings,
                    "error": r.error,
                }
                for r in results
            ],
            indent=2,
            default=str,
        )
    )


@quantitative_cli.command("status")
def quantitative_status() -> None:
    """Print the last-run summary for every APPROVED formalisation."""
    from noosphere.forecasts.scheduler import database_url_from_env
    from noosphere.store import Store

    store = Store.from_database_url(database_url_from_env())
    rows = []
    for f in store.list_quantitative_formalisations(status="APPROVED"):
        latest = store.get_latest_quantitative_test_result(f.id)
        rows.append(
            {
                "formalisation_id": f.id,
                "principle_id": f.principle_id,
                "latest_run_stamp": latest.run_stamp if latest else None,
                "status": (
                    (latest.status.value if hasattr(latest.status, "value") else latest.status)
                    if latest
                    else None
                ),
                "headline_summary": latest.decision_summary if latest else None,
                "artifacts_path": latest.artifacts_path if latest else None,
                "threshold_crossings": latest.threshold_crossings if latest else [],
            }
        )
    click.echo(json.dumps(rows, indent=2, default=str))


# ── Command: algorithms ────────────────────────────────────────────────────


@click.group("algorithms")
def algorithms_cli() -> None:
    """LogicalAlgorithm drafter + queue inspector (Round 19 prompt 02).

    Drafts are written as ``DRAFT`` rows the founder accepts in the
    triage queue at ``/algorithms/queue``. The CLI never promotes a
    row to ``ACTIVE`` — that path lives in the founder UI.
    """


@algorithms_cli.command("draft")
@click.option(
    "--cluster",
    "cluster",
    type=str,
    default=None,
    help="Comma-separated principle ids to draft from.",
)
@click.option(
    "--auto",
    "auto",
    is_flag=True,
    default=False,
    help=(
        "Iterate every principle cluster without a recent draft and "
        "propose one each, capped by ALGORITHMS_MAX_DRAFTS_PER_RUN."
    ),
)
@click.option(
    "--organization-id",
    "organization_id",
    type=str,
    default=None,
    help="Org id the drafted rows belong to (defaults to the settings org).",
)
def algorithms_draft(
    cluster: Optional[str],
    auto: bool,
    organization_id: Optional[str],
) -> None:
    """Draft a LogicalAlgorithm from one or more principle clusters."""
    import os

    from noosphere.algorithms.budget import load_persistent_guard
    from noosphere.algorithms.drafter import AlgorithmDrafter
    from noosphere.forecasts.scheduler import database_url_from_env
    from noosphere.llm import llm_client_from_settings
    from noosphere.store import Store

    if not cluster and not auto:
        raise click.UsageError("pass --cluster <ids> or --auto")

    store = Store.from_database_url(database_url_from_env())
    org = organization_id or os.environ.get("ALGORITHMS_ORGANIZATION_ID", "")
    if not org:
        raise click.UsageError(
            "no organization id provided and ALGORITHMS_ORGANIZATION_ID is unset"
        )

    # Build an in-memory id → Principle map; the noosphere store keeps
    # accepted principles only and the drafter needs them looked up by
    # id.  A thin wrapper exposes ``get_principle`` on top.
    principles = {p.id: p for p in store.list_principles()}

    class _StoreView:
        def get_principle(self, principle_id):
            return principles.get(principle_id)

        def list_algorithms_for_org(self, organization_id, *, status=None):
            return store.list_algorithms_for_org(organization_id, status=status)

        def put_algorithm(self, algorithm, *, revoked_principle_ids=None):
            return store.put_algorithm(
                algorithm, revoked_principle_ids=revoked_principle_ids
            )

    view = _StoreView()
    llm = llm_client_from_settings()
    drafter = AlgorithmDrafter(llm, organization_id=org)
    budget = load_persistent_guard()

    clusters: list[list[str]] = []
    if cluster:
        clusters.append([pid.strip() for pid in cluster.split(",") if pid.strip()])
    if auto:
        max_drafts = int(os.environ.get("ALGORITHMS_MAX_DRAFTS_PER_RUN", "6"))
        # Auto mode is intentionally narrow: the drafter walks the
        # store's accepted principles in id order and proposes one
        # algorithm per *unique pair* up to the cap.  Real clustering
        # is the distillation pipeline's job; this CLI only iterates.
        ids = sorted(principles.keys())
        seen: set[frozenset[str]] = set()
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                key = frozenset({a, b})
                if key in seen:
                    continue
                seen.add(key)
                clusters.append([a, b])
                if len(clusters) >= max_drafts + (1 if cluster else 0):
                    break
            if len(clusters) >= max_drafts + (1 if cluster else 0):
                break

    results = []
    for c in clusters:
        result = asyncio.run(
            drafter.draft_from_cluster(view, c, budget=budget)
        )
        results.append(
            {
                "cluster": c,
                "outcome": result.outcome.value,
                "algorithm_id": result.algorithm_id,
                "reason": result.reason,
            }
        )
    click.echo(json.dumps(results, indent=2, default=str))


@algorithms_cli.command("list")
@click.option(
    "--status",
    "status",
    type=click.Choice(
        ["DRAFT", "UNDER_REVIEW", "ACTIVE", "PAUSED", "RETIRED"],
        case_sensitive=False,
    ),
    default=None,
    help="Filter by status (defaults to all).",
)
@click.option(
    "--organization-id",
    "organization_id",
    type=str,
    default=None,
    help="Org id to list rows for (defaults to the settings org).",
)
def algorithms_list(status: Optional[str], organization_id: Optional[str]) -> None:
    """Print LogicalAlgorithm rows for the configured org."""
    import os

    from noosphere.algorithms.schemas import AlgorithmStatus
    from noosphere.forecasts.scheduler import database_url_from_env
    from noosphere.store import Store

    store = Store.from_database_url(database_url_from_env())
    org = organization_id or os.environ.get("ALGORITHMS_ORGANIZATION_ID", "")
    if not org:
        raise click.UsageError(
            "no organization id provided and ALGORITHMS_ORGANIZATION_ID is unset"
        )
    status_value = AlgorithmStatus(status.upper()) if status else None
    rows = store.list_algorithms_for_org(org, status=status_value)
    out = [
        {
            "id": a.id,
            "name": a.name,
            "status": getattr(a.status, "value", str(a.status)),
            "source_principle_ids": list(a.source_principle_ids),
            "input_count": len(a.inputs),
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in rows
    ]
    click.echo(json.dumps(out, indent=2, default=str))


@algorithms_cli.command("tick")
@click.option(
    "--once",
    "once",
    is_flag=True,
    default=True,
    help=(
        "Run a single algorithms_tick + algorithms_resolution pass and "
        "exit. Default; the standing loop lives behind 'algorithms run'."
    ),
)
@click.option(
    "--organization-id",
    "organization_id",
    type=str,
    default=None,
    help="Org id whose ACTIVE algorithms to tick (defaults to settings org).",
)
def algorithms_tick(once: bool, organization_id: Optional[str]) -> None:
    """Fire ACTIVE algorithms against current observability."""
    import os
    from noosphere.algorithms.adapters import AdapterRegistry
    from noosphere.algorithms.adapters.currents_source import CurrentsAdapter
    from noosphere.algorithms.adapters.manual_source import (
        ArtifactFieldAdapter,
        ManualOperatorAdapter,
    )
    from noosphere.algorithms.adapters.markets_source import MarketsAdapter
    from noosphere.algorithms.input_resolver import InputResolver
    from noosphere.algorithms.runtime import AlgorithmRuntime
    from noosphere.forecasts.scheduler import database_url_from_env
    from noosphere.llm import llm_client_from_settings
    from noosphere.store import Store

    store = Store.from_database_url(database_url_from_env())
    org = organization_id or os.environ.get("ALGORITHMS_ORGANIZATION_ID", "")
    if not org:
        raise click.UsageError(
            "no organization id provided and ALGORITHMS_ORGANIZATION_ID is unset"
        )
    registry = AdapterRegistry()
    registry.register(CurrentsAdapter(store=store, organization_id=org))
    registry.register(MarketsAdapter(store=store, organization_id=org))
    registry.register(ManualOperatorAdapter(provider=lambda: {}))
    registry.register(ArtifactFieldAdapter(cell_provider=lambda _a, _f: None))
    runtime = AlgorithmRuntime(
        resolver=InputResolver(registry),
        llm=llm_client_from_settings(),
        organization_id=org,
    )
    tick = asyncio.run(runtime.tick_once(store))
    click.echo(
        json.dumps(
            {
                "fired": tick.fired,
                "skipped_no_input": tick.skipped_no_input,
                "skipped_predicate_false": tick.skipped_predicate_false,
                "skipped_idempotent": tick.skipped_idempotent,
                "skipped_sandbox": tick.skipped_sandbox,
                "skipped_token_cap": tick.skipped_token_cap,
                "errors": tick.errors,
                "invocation_ids": tick.invocation_ids,
            },
            indent=2,
            default=str,
        )
    )


@algorithms_cli.command("run")
@click.option(
    "--organization-id",
    "organization_id",
    type=str,
    default=None,
    help="Org id whose ACTIVE algorithms to tick (defaults to settings org).",
)
def algorithms_run(organization_id: Optional[str]) -> None:
    """Run the algorithms_tick + algorithms_resolution sub-loops forever.

    Production deploys typically run the consolidated Forecasts
    scheduler container, which already drives the algorithm sub-loops.
    This entry point exists for operators who want to run the algorithm
    runtime alone on a dedicated host.
    """
    import os

    from noosphere.forecasts.scheduler import (
        SchedulerConfig,
        database_url_from_env,
        run_forever,
    )
    from noosphere.store import Store

    if organization_id:
        os.environ.setdefault("FORECASTS_ORG_ID", organization_id)
    store = Store.from_database_url(database_url_from_env())
    config = SchedulerConfig.from_env()
    asyncio.run(run_forever(store, config=config))


@algorithms_cli.command("fire")
@click.option(
    "--algorithm",
    "algorithm_id",
    type=str,
    required=True,
    help="LogicalAlgorithm id to fire.",
)
@click.option(
    "--inputs",
    "inputs_path",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
    help="Path to a JSON file mapping input name → value.",
)
def algorithms_fire(algorithm_id: str, inputs_path: str) -> None:
    """Force-fire one algorithm against operator-provided inputs.

    The invocation is tagged ``forced=True`` so the founder UI can
    filter the row out of the live track-record.
    """
    from noosphere.algorithms.adapters import AdapterRegistry
    from noosphere.algorithms.input_resolver import InputResolver
    from noosphere.algorithms.runtime import AlgorithmRuntime
    from noosphere.forecasts.scheduler import database_url_from_env
    from noosphere.llm import llm_client_from_settings
    from noosphere.store import Store

    with open(inputs_path, "r", encoding="utf-8") as fh:
        forced_inputs = json.load(fh)
    store = Store.from_database_url(database_url_from_env())
    algorithm = store.get_algorithm(algorithm_id)
    if algorithm is None:
        raise click.UsageError(f"algorithm {algorithm_id!r} not found")
    registry = AdapterRegistry()
    runtime = AlgorithmRuntime(
        resolver=InputResolver(registry),
        llm=llm_client_from_settings(),
        organization_id=algorithm.organization_id,
    )
    invocation = asyncio.run(
        runtime.fire_algorithm(
            store,
            algorithm=algorithm,
            forced_inputs=forced_inputs,
            forced=True,
        )
    )
    if invocation is None:
        raise click.ClickException(
            "runtime declined to produce an invocation; "
            "see structured logs for the reason"
        )
    click.echo(
        json.dumps(
            {
                "invocation_id": invocation.id,
                "algorithm_id": invocation.algorithm_id,
                "derived_output": invocation.derived_output,
                "confidence_low": invocation.confidence_low,
                "confidence_high": invocation.confidence_high,
                "predicted_horizon": invocation.predicted_horizon,
                "reasoning_trace": invocation.reasoning_trace,
            },
            indent=2,
            default=str,
        )
    )


@algorithms_cli.command("calibrate")
@click.option(
    "--algorithm",
    "algorithm_id",
    type=str,
    default=None,
    help="LogicalAlgorithm id to recompute calibration for.",
)
@click.option(
    "--all",
    "all_algos",
    is_flag=True,
    default=False,
    help="Recompute calibration for every ACTIVE algorithm in the org.",
)
@click.option(
    "--organization-id",
    "organization_id",
    type=str,
    default=None,
    help="Org id (defaults to ALGORITHMS_ORGANIZATION_ID).",
)
def algorithms_calibrate(
    algorithm_id: Optional[str],
    all_algos: bool,
    organization_id: Optional[str],
) -> None:
    """Recompute calibration snapshots and trigger triage recommendations."""
    import os

    from noosphere.algorithms.calibration import compute_stats
    from noosphere.algorithms.retirement import (
        RecommendedAction,
        build_recommendation,
    )
    from noosphere.forecasts.scheduler import database_url_from_env
    from noosphere.models import (
        AlgorithmCalibrationSnapshot,
        AlgorithmTriageRecommendation,
    )
    from noosphere.store import Store

    if not algorithm_id and not all_algos:
        raise click.UsageError("pass --algorithm <id> or --all")

    store = Store.from_database_url(database_url_from_env())
    org = organization_id or os.environ.get("ALGORITHMS_ORGANIZATION_ID", "")

    if all_algos:
        if not org:
            raise click.UsageError(
                "no organization id provided and ALGORITHMS_ORGANIZATION_ID is unset"
            )
        algorithms = store.list_active_algorithms(organization_id=org)
    else:
        algo = store.get_algorithm(algorithm_id)
        if algo is None:
            raise click.UsageError(f"algorithm {algorithm_id!r} not found")
        algorithms = [algo]

    rows: list[dict] = []
    for algorithm in algorithms:
        invocations = store.list_invocations_for_algorithm(
            algorithm.id, limit=2000
        )
        stats = compute_stats(invocations)
        snapshot = AlgorithmCalibrationSnapshot(
            algorithm_id=algorithm.id,
            organization_id=algorithm.organization_id,
            total_invocations=stats.total_invocations,
            resolved_invocations=stats.resolved_invocations,
            accuracy=stats.accuracy,
            mean_brier=stats.mean_brier,
            mean_horizon_error=stats.mean_horizon_error,
            directional_accuracy=stats.directional_accuracy,
            confidence_calibration_drift=stats.confidence_calibration_drift,
            last_30d_accuracy=stats.last_30d_accuracy,
            last_30d_resolved=stats.last_30d_resolved,
            probabilistic_resolved=stats.probabilistic_resolved,
            directional_resolved=stats.directional_resolved,
            confidence_band_resolved=stats.confidence_band_resolved,
        )
        store.put_calibration_snapshot(snapshot)
        current_multiplier = store.get_algorithm_weighting_multiplier(
            algorithm.id
        )
        recommendation = build_recommendation(
            algorithm_id=algorithm.id,
            stats=stats,
            current_multiplier=current_multiplier,
        )
        triage_id = None
        action_value = (
            recommendation.recommended_action.value
            if hasattr(recommendation.recommended_action, "value")
            else str(recommendation.recommended_action)
        )
        if action_value != RecommendedAction.NONE.value:
            triage_row = AlgorithmTriageRecommendation(
                algorithm_id=algorithm.id,
                organization_id=algorithm.organization_id,
                recommended_action=action_value,
                trigger_reasons=[
                    r.value if hasattr(r, "value") else str(r)
                    for r in recommendation.reasons
                ],
                recommended_multiplier=recommendation.recommended_multiplier,
                narrative=recommendation.narrative,
            )
            store.put_triage_recommendation(triage_row)
            triage_id = triage_row.id
        rows.append(
            {
                "algorithm_id": algorithm.id,
                "name": algorithm.name,
                "snapshot_id": snapshot.id,
                "stats": stats.model_dump(),
                "recommended_action": action_value,
                "triage_id": triage_id,
                "narrative": recommendation.narrative,
            }
        )
    click.echo(json.dumps(rows, indent=2, default=str))


@algorithms_cli.command("triage")
@click.option(
    "--pending",
    "pending",
    is_flag=True,
    default=False,
    help="List PENDING triage recommendations.",
)
@click.option(
    "--organization-id",
    "organization_id",
    type=str,
    default=None,
    help="Org id (defaults to ALGORITHMS_ORGANIZATION_ID).",
)
def algorithms_triage(pending: bool, organization_id: Optional[str]) -> None:
    """List calibration triage recommendations for the operator queue."""
    import os

    from noosphere.forecasts.scheduler import database_url_from_env
    from noosphere.models import TriageRecommendationStatus
    from noosphere.store import Store

    org = organization_id or os.environ.get("ALGORITHMS_ORGANIZATION_ID", "")
    if not org:
        raise click.UsageError(
            "no organization id provided and ALGORITHMS_ORGANIZATION_ID is unset"
        )
    store = Store.from_database_url(database_url_from_env())
    status = TriageRecommendationStatus.PENDING if pending else None
    rows = store.list_triage_recommendations(
        organization_id=org, status=status
    )
    payload = [
        {
            "id": r.id,
            "algorithm_id": r.algorithm_id,
            "recommended_at": r.recommended_at,
            "recommended_action": (
                r.recommended_action.value
                if hasattr(r.recommended_action, "value")
                else r.recommended_action
            ),
            "trigger_reasons": r.trigger_reasons,
            "recommended_multiplier": r.recommended_multiplier,
            "narrative": r.narrative,
            "status": (
                r.status.value if hasattr(r.status, "value") else r.status
            ),
        }
        for r in rows
    ]
    click.echo(json.dumps(payload, indent=2, default=str))


# ── Command group: contradiction (canonical engine, R19/p06) ──────────────


@click.group("contradiction")
def contradiction_cli() -> None:
    """Canonical contradiction engine (one method, version-stamped)."""


@contradiction_cli.command("detect")
@click.option("--a", "principle_a_id", required=True, type=str,
              help="Principle id on side A")
@click.option("--b", "principle_b_id", required=True, type=str,
              help="Principle id on side B")
@click.option("--persist/--no-persist", default=True,
              help="Persist the result to the contradiction_result table")
def contradiction_detect(
    principle_a_id: str, principle_b_id: str, persist: bool
) -> None:
    """Run the canonical engine on one principle pair."""
    from noosphere.coherence.contradiction_engine import (
        ContradictionEngine,
        stable_pair_id,
    )

    store = _store_from_settings()
    pa = store.get_principle(principle_a_id) if hasattr(store, "get_principle") else None
    pb = store.get_principle(principle_b_id) if hasattr(store, "get_principle") else None
    if pa is None or pb is None:
        click.echo(
            json.dumps(
                {
                    "ok": False,
                    "error": "principle not found",
                    "principle_a_found": pa is not None,
                    "principle_b_found": pb is not None,
                },
                indent=2,
            ),
            err=True,
        )
        raise SystemExit(2)

    engine = ContradictionEngine()
    result = asyncio.run(engine.detect(pa, pb, store=store))
    payload = result.to_dict()
    if persist and hasattr(store, "put_contradiction_result"):
        store.put_contradiction_result(
            result_id=stable_pair_id(pa.id, pb.id) + ":" + result.detection_method,
            principle_a_id=result.principle_a_id,
            principle_b_id=result.principle_b_id,
            score=result.score,
            confidence_low=result.confidence_low,
            confidence_high=result.confidence_high,
            verdict=result.verdict.value,
            axis=result.axis,
            human_explanation=result.human_explanation,
            detection_method=result.detection_method,
            detected_at=result.detected_at,
            raw_sparsity=result.raw_sparsity,
            direction_method=result.direction_method,
            extras=result.extras,
        )
        payload["persisted"] = True
    click.echo(json.dumps(payload, indent=2, default=str))


@contradiction_cli.command("sweep")
@click.option("--since", "since_iso", required=True, type=str,
              help="ISO timestamp; re-run engine across pairs of principles "
                   "created/updated since this instant")
@click.option("--max-concurrency", type=int, default=4)
@click.option("--limit-pairs", type=int, default=200,
              help="Cap the number of pairs evaluated this sweep")
def contradiction_sweep(
    since_iso: str, max_concurrency: int, limit_pairs: int
) -> None:
    """Re-run the canonical engine on principles added since a timestamp."""
    from noosphere.coherence.contradiction_engine import (
        ContradictionEngine,
        stable_pair_id,
    )

    try:
        since = datetime.fromisoformat(since_iso)
    except ValueError as exc:
        raise click.BadParameter(f"--since must be ISO format: {exc}")

    store = _store_from_settings()
    if not hasattr(store, "list_principles"):
        click.echo(
            json.dumps({"ok": False, "error": "store has no list_principles"}),
            err=True,
        )
        raise SystemExit(2)
    principles = [
        p for p in store.list_principles()
        if (p.updated_at or p.created_at) >= since
    ]
    pairs: list[tuple[Any, Any]] = []
    for i in range(len(principles)):
        for j in range(i + 1, len(principles)):
            pairs.append((principles[i], principles[j]))
            if len(pairs) >= limit_pairs:
                break
        if len(pairs) >= limit_pairs:
            break

    engine = ContradictionEngine()
    results = asyncio.run(
        engine.batch_detect(
            pairs, store=store, max_concurrency=max_concurrency
        )
    )
    persisted = 0
    if hasattr(store, "put_contradiction_result"):
        for r in results:
            store.put_contradiction_result(
                result_id=stable_pair_id(r.principle_a_id, r.principle_b_id)
                + ":"
                + r.detection_method,
                principle_a_id=r.principle_a_id,
                principle_b_id=r.principle_b_id,
                score=r.score,
                confidence_low=r.confidence_low,
                confidence_high=r.confidence_high,
                verdict=r.verdict.value,
                axis=r.axis,
                human_explanation=r.human_explanation,
                detection_method=r.detection_method,
                detected_at=r.detected_at,
                raw_sparsity=r.raw_sparsity,
                direction_method=r.direction_method,
                extras=r.extras,
            )
            persisted += 1
    click.echo(
        json.dumps(
            {
                "ok": True,
                "since": since.isoformat(),
                "principles_considered": len(principles),
                "pairs_evaluated": len(results),
                "contradictions": sum(
                    1 for r in results if r.verdict.value == "CONTRADICTORY"
                ),
                "persisted": persisted,
            },
            indent=2,
        )
    )


@contradiction_cli.command("methods")
def contradiction_methods() -> None:
    """List available detection method versions + benchmark stats."""
    from noosphere.coherence.contradiction_engine import list_methods

    payload = [
        {
            "name": m.name,
            "description": m.description,
            "embedding_family": m.embedding_family,
            "geometry": m.geometry,
            "benchmark_auroc": m.benchmark_auroc,
            "benchmark_calibration_ece": m.benchmark_calibration_ece,
            "benchmark_run_stamp": m.benchmark_run_stamp,
        }
        for m in list_methods()
    ]
    click.echo(json.dumps(payload, indent=2))


@contradiction_cli.command("lifecycle")
@click.option("--id", "contradiction_id", required=True, type=str,
              help="Contradiction id to inspect")
def contradiction_lifecycle(contradiction_id: str) -> None:
    """Print the full lifecycle event log for one contradiction."""
    from noosphere.coherence.lifecycle import LifecycleRecord

    store = _store_from_settings()
    row = store.get_contradiction_lifecycle(contradiction_id)
    if row is None:
        click.echo(
            json.dumps(
                {
                    "ok": False,
                    "error": "no lifecycle row found",
                    "contradiction_id": contradiction_id,
                },
                indent=2,
            ),
            err=True,
        )
        raise SystemExit(2)
    events = LifecycleRecord.parse_events_json(row.events_json)
    payload = {
        "ok": True,
        "id": row.id,
        "contradiction_id": row.contradiction_id,
        "current_status": row.current_status,
        "last_transition_at": row.last_transition_at.isoformat(),
        "supported_principle_id": row.supported_principle_id,
        "subsuming_principle_id": row.subsuming_principle_id,
        "pending_subsumption_principle_id": (
            row.pending_subsumption_principle_id
        ),
        "events": [ev.to_dict() for ev in events],
    }
    click.echo(json.dumps(payload, indent=2, default=str))


@contradiction_cli.command("sweep-resolutions")
@click.option("--limit", type=int, default=200,
              help="Cap the number of standing contradictions inspected")
@click.option("--principle-id", "principle_id", type=str, default=None,
              help="Only sweep against this one principle (default: every "
                   "principle updated since the last sweep window)")
def contradiction_sweep_resolutions(
    limit: int, principle_id: Optional[str]
) -> None:
    """Replay every STANDING / WEAKENED contradiction against the current
    corpus to find newly-eligible auto-resolutions.

    Without ``--principle-id`` we treat every principle as a potential
    new source, walking the lifecycle queue once per principle. With
    ``--principle-id`` set we only score that one principle against the
    current standing contradictions — handy after a manual re-ingest.
    """
    from noosphere.coherence.auto_resolver import on_new_principle

    store = _store_from_settings()
    if not hasattr(store, "list_principles"):
        click.echo(
            json.dumps({"ok": False, "error": "store has no list_principles"}),
            err=True,
        )
        raise SystemExit(2)

    if principle_id:
        principles = [store.get_principle(principle_id)]
        principles = [p for p in principles if p is not None]
    else:
        principles = store.list_principles()[:limit]

    total_transitioned = 0
    total_examined = 0
    per_principle: list[dict[str, Any]] = []
    for p in principles:
        report = asyncio.run(on_new_principle(store, p.id))
        total_examined += report.examined
        total_transitioned += report.transitioned
        per_principle.append(
            {
                "principle_id": p.id,
                "examined": report.examined,
                "transitioned": report.transitioned,
                "subsumption_candidates": report.subsumption_candidates,
                "transitions": [
                    {
                        "contradiction_id": o.contradiction_id,
                        "from": o.previous_status.value,
                        "to": o.new_status.value,
                        "rationale": o.decision.rationale,
                    }
                    for o in report.outcomes
                    if o.previous_status != o.new_status
                ],
            }
        )
    click.echo(
        json.dumps(
            {
                "ok": True,
                "principles_scanned": len(principles),
                "lifecycles_examined": total_examined,
                "transitions": total_transitioned,
                "per_principle": per_principle,
            },
            indent=2,
            default=str,
        )
    )


# ── Library / provenance commands (prompt 09) ───────────────────────────────


@click.group("library")
def library_cli() -> None:
    """Manage the upload-time provenance demarcation.

    Every artifact carries one of four kinds — PROPRIETARY,
    ENDORSED_EXTERNAL, STUDIED_EXTERNAL, OPPOSING_EXTERNAL — set by the
    founder. These commands are the founder-controlled tag surface; the
    agent never sets provenance on its own.
    """


_PROVENANCE_CHOICES = click.Choice(
    [
        "PROPRIETARY",
        "ENDORSED_EXTERNAL",
        "STUDIED_EXTERNAL",
        "OPPOSING_EXTERNAL",
    ],
    case_sensitive=False,
)


@library_cli.command("tag")
@click.option("--artifact", "artifact_id", required=True, type=str,
              help="Artifact id to retag.")
@click.option("--provenance", required=True, type=_PROVENANCE_CHOICES,
              help="One of the four provenance kinds.")
@click.option("--rationale", type=str, default="",
              help="Required (≥ 30 chars) for any non-PROPRIETARY kind.")
def library_tag(artifact_id: str, provenance: str, rationale: str) -> None:
    """Retag an artifact's provenance.

    The agent must never invoke this on the founder's behalf without an
    explicit instruction — provenance is founder-set, never inferred.
    """
    store = _store_from_settings()
    try:
        ok = store.set_artifact_provenance(
            artifact_id, provenance.upper(), rationale=rationale
        )
    except ValueError as exc:
        raise click.UsageError(str(exc)) from exc
    if not ok:
        raise click.ClickException(f"No artifact found with id {artifact_id!r}")
    click.echo(json.dumps({"ok": True, "artifact_id": artifact_id,
                           "provenance": provenance.upper()}, indent=2))


@library_cli.command("list")
@click.option("--provenance", type=_PROVENANCE_CHOICES, default=None,
              help="Filter by provenance kind; omit to list all kinds.")
@click.option("--limit", type=int, default=200,
              help="Maximum number of rows to return.")
def library_list(provenance: Optional[str], limit: int) -> None:
    """List artifacts, optionally narrowed to one provenance kind."""
    store = _store_from_settings()
    rows = store.list_artifacts_by_provenance(
        provenance.upper() if provenance else None, limit=limit
    )
    out = [
        {
            "id": a.id,
            "title": a.title,
            "author": a.author,
            "provenance": getattr(a.provenance, "value", str(a.provenance)),
            "rationale": a.provenance_rationale,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in rows
    ]
    click.echo(json.dumps({"count": len(out), "artifacts": out}, indent=2))


@library_cli.command("audit-untagged")
@click.option("--limit", type=int, default=500,
              help="Maximum number of PROPRIETARY-defaulted rows to surface.")
def library_audit_untagged(limit: int) -> None:
    """Surface rows that still need founder review.

    After the prompt-09 migration every existing artifact defaults to
    PROPRIETARY. This command lists them — and the count — so the
    founder knows what to walk through in `/library/triage` next.
    """
    store = _store_from_settings()
    rows = store.list_untagged_artifacts(limit=limit)
    counts = store.count_artifacts_by_provenance()
    click.echo(
        json.dumps(
            {
                "default_proprietary_count": counts.get("PROPRIETARY", 0),
                "counts_by_kind": counts,
                "shown": len(rows),
                "artifacts": [
                    {
                        "id": a.id,
                        "title": a.title,
                        "uri": a.uri,
                        "created_at": a.created_at.isoformat() if a.created_at else None,
                    }
                    for a in rows
                ],
            },
            indent=2,
        )
    )


# ── Command group: synthesizer (prompt 10) ─────────────────────────────────


@click.group("synthesizer")
def synthesizer_cli() -> None:
    """Synthesizer engine — ad-hoc query and queue inspection (prompt 10)."""


@synthesizer_cli.command("query")
@click.option(
    "--question",
    "question",
    required=True,
    type=str,
    help="The operator's question (investment / forecast / explanatory / strategic).",
)
@click.option(
    "--organization-id",
    "organization_id",
    type=str,
    default=None,
    help="Org id (defaults to ALGORITHMS_ORGANIZATION_ID).",
)
@click.option(
    "--domain",
    "domain",
    type=str,
    default="",
    help="Optional domain hint for governing-principle selection.",
)
@click.option(
    "--no-budget",
    "no_budget",
    is_flag=True,
    default=False,
    help="Skip the hourly token budget guard (useful for ad-hoc runs).",
)
def synthesizer_query(
    question: str,
    organization_id: Optional[str],
    domain: str,
    no_budget: bool,
) -> None:
    """Run one synthesis pass against the operator's question."""

    import os

    from noosphere.forecasts.scheduler import database_url_from_env
    from noosphere.llm import llm_client_from_settings
    from noosphere.store import Store
    from noosphere.synthesizer.budget import load_persistent_guard
    from noosphere.synthesizer.engine import SynthesizerEngine

    org = organization_id or os.environ.get("ALGORITHMS_ORGANIZATION_ID", "")
    if not org:
        raise click.UsageError(
            "no organization id provided and ALGORITHMS_ORGANIZATION_ID is unset"
        )
    store = Store.from_database_url(database_url_from_env())
    llm = llm_client_from_settings()
    engine = SynthesizerEngine(llm=llm, organization_id=org)
    budget = None if no_budget else load_persistent_guard()
    context: dict[str, str] = {}
    if domain:
        context["domain"] = domain
    result = asyncio.run(
        engine.synthesize(question, store=store, budget=budget, context=context)
    )
    click.echo(json.dumps(result.to_dict(), indent=2, default=str))


@synthesizer_cli.command("status")
@click.option(
    "--organization-id",
    "organization_id",
    type=str,
    default=None,
    help="Org id (defaults to ALGORITHMS_ORGANIZATION_ID).",
)
@click.option(
    "--limit",
    "limit",
    type=int,
    default=10,
    help="Number of recent memos to surface.",
)
def synthesizer_status(
    organization_id: Optional[str], limit: int
) -> None:
    """Show backlog, last memos, and abstention rate."""

    import os

    from noosphere.forecasts.scheduler import database_url_from_env
    from noosphere.models import SynthesizerTaskStatus
    from noosphere.store import Store

    org = organization_id or os.environ.get("ALGORITHMS_ORGANIZATION_ID", "")
    store = Store.from_database_url(database_url_from_env())

    pending = store.list_pending_synthesizer_tasks(
        organization_id=org or None, limit=200
    )
    memos = store.list_synthesizer_memos(organization_id=org or None, limit=limit)

    # Abstention rate over the recent memo window: memos persist on
    # CONCLUDED outcomes only, so the abstention rate has to be derived
    # from the corresponding task rows. We approximate by walking the
    # most recent finished task per memo when possible.
    abstained = concluded = 0
    try:
        with store.session() as s:  # pragma: no cover - exec ok, depends on store
            from sqlmodel import select
            from noosphere.store import StoredSynthesizerTask  # type: ignore

            stmt = select(StoredSynthesizerTask).where(
                StoredSynthesizerTask.status == "DONE"
            )
            if org:
                stmt = stmt.where(StoredSynthesizerTask.organization_id == org)
            for row in s.exec(stmt).all():
                if row.outcome == "CONCLUDED":
                    concluded += 1
                else:
                    abstained += 1
    except Exception:
        pass
    total = concluded + abstained
    abstention_rate = (abstained / total) if total else 0.0

    payload: dict[str, Any] = {
        "organization_id": org or None,
        "pending_tasks": len(pending),
        "pending_task_ids": [t.id for t in pending[:10]],
        "recent_memos": [
            {
                "id": memo.id,
                "question": memo.question,
                "created_at": memo.created_at.isoformat()
                if memo.created_at
                else None,
                "synthesizer_version": memo.synthesizer_version,
            }
            for memo in memos
        ],
        "task_window": {
            "concluded": concluded,
            "abstained": abstained,
            "abstention_rate": round(abstention_rate, 3),
        },
    }
    click.echo(json.dumps(payload, indent=2, default=str))


# ── Command group: memo (prompt 11) ────────────────────────────────────────


@click.group("memo")
def memo_cli() -> None:
    """Investment-memo lifecycle (prompt 11).

    Memos are the canonical artifact the synthesizer emits and the
    portfolio agent consumes. They are built from a CONCLUDED
    SynthesisResult, persisted in DRAFT, reviewed by an operator, and
    sent / archived / published.
    """


@memo_cli.command("build")
@click.option(
    "--synthesis",
    "synthesis_id",
    required=True,
    type=str,
    help="The persisted synthesizer-memo (synth memo id) to render.",
)
@click.option(
    "--organization-id",
    "organization_id",
    type=str,
    default=None,
    help="Org id (defaults to ALGORITHMS_ORGANIZATION_ID).",
)
@click.option(
    "--addressee",
    "addressee",
    type=str,
    default=None,
    help="Override the auto-filled portfolio-agent addressee.",
)
def memo_build(
    synthesis_id: str,
    organization_id: Optional[str],
    addressee: Optional[str],
) -> None:
    """Build an InvestmentMemo from a persisted synthesis result."""

    import os
    from types import SimpleNamespace

    from noosphere.forecasts.scheduler import database_url_from_env
    from noosphere.store import Store
    from noosphere.synthesizer.engine import (
        Conclusion,
        QuestionType,
        ReasoningChainStep,
        SynthesisOutcome,
        SynthesisResult,
    )
    from noosphere.synthesizer.memo_builder import build_memo

    store = Store.from_database_url(database_url_from_env())
    raw = store.get_synthesizer_memo(synthesis_id)
    if raw is None:
        raise click.UsageError(f"no synthesizer memo found with id {synthesis_id!r}")

    cdata = dict(raw.conclusion_json or {})
    chain = [
        ReasoningChainStep(
            step_kind=str(step.get("step_kind") or "STEP"),
            principle_id=str(step.get("principle_id") or ""),
            derived_fact=str(step.get("derived_fact") or ""),
            observation_id=step.get("observation_id"),
        )
        for step in (cdata.get("reasoning_chain") or [])
    ]
    qtype_value = cdata.get("conclusion_type") or "EXPLANATORY"
    try:
        qtype = QuestionType(qtype_value)
    except ValueError:
        qtype = QuestionType.EXPLANATORY
    conclusion = Conclusion(
        conclusion_type=qtype,
        assertion=str(cdata.get("assertion") or ""),
        confidence_low=float(cdata.get("confidence_low") or 0.0),
        confidence_high=float(cdata.get("confidence_high") or 0.0),
        governing_principles=list(cdata.get("governing_principles") or []),
        cited_observations=list(cdata.get("cited_observations") or []),
        reasoning_chain=chain,
        implied_bet=cdata.get("implied_bet"),
    )
    synthesis_result = SimpleNamespace(
        outcome=SynthesisOutcome.CONCLUDED,
        conclusion=conclusion,
        question=raw.question,
        question_type=qtype,
        memo_id=raw.id,
        synthesizer_version=raw.synthesizer_version,
    )

    org = organization_id or raw.organization_id or os.environ.get(
        "ALGORITHMS_ORGANIZATION_ID", ""
    )
    if not org:
        raise click.UsageError(
            "no organization id provided and ALGORITHMS_ORGANIZATION_ID is unset"
        )

    memo = build_memo(
        synthesis_result,
        store=store,
        organization_id=org,
        addressee=addressee,
    )
    click.echo(
        json.dumps(
            {
                "id": memo.id,
                "slug": memo.slug,
                "status": memo.status
                if isinstance(memo.status, str)
                else memo.status.value,
                "md_path": memo.md_path,
                "pdf_path": memo.pdf_path,
                "addressee": memo.addressee,
                "title": memo.title,
            },
            indent=2,
            default=str,
        )
    )


@memo_cli.command("send")
@click.option(
    "--id", "memo_id", required=True, type=str, help="Memo id to send."
)
@click.option(
    "--addressee",
    "addressee",
    type=str,
    default=None,
    help="Override addressee at send time.",
)
def memo_send(memo_id: str, addressee: Optional[str]) -> None:
    """Dispatch a memo to its portfolio agent (DRAFT/UNDER_REVIEW → SENT)."""

    from noosphere.forecasts.scheduler import database_url_from_env
    from noosphere.store import Store
    from noosphere.synthesizer.memo_builder import send_memo

    store = Store.from_database_url(database_url_from_env())
    memo = send_memo(store, memo_id, addressee=addressee)
    if memo is None:
        raise click.UsageError(f"memo {memo_id!r} not found")
    click.echo(
        json.dumps(
            {
                "id": memo.id,
                "status": memo.status
                if isinstance(memo.status, str)
                else memo.status.value,
                "sent_at": memo.sent_at.isoformat() if memo.sent_at else None,
                "addressee": memo.addressee,
            },
            indent=2,
            default=str,
        )
    )


@memo_cli.command("publish")
@click.option(
    "--id", "memo_id", required=True, type=str, help="Memo id to publish."
)
def memo_publish(memo_id: str) -> None:
    """Mark a memo PUBLIC; surfaces it on the /memos reader page."""

    from noosphere.forecasts.scheduler import database_url_from_env
    from noosphere.store import Store
    from noosphere.synthesizer.memo_builder import publish_memo

    store = Store.from_database_url(database_url_from_env())
    memo = publish_memo(store, memo_id)
    if memo is None:
        raise click.UsageError(f"memo {memo_id!r} not found")
    click.echo(
        json.dumps(
            {
                "id": memo.id,
                "slug": memo.slug,
                "status": memo.status
                if isinstance(memo.status, str)
                else memo.status.value,
                "published_at": memo.published_at.isoformat()
                if memo.published_at
                else None,
            },
            indent=2,
            default=str,
        )
    )


@memo_cli.command("list")
@click.option(
    "--status",
    "status_value",
    type=click.Choice(
        ["DRAFT", "UNDER_REVIEW", "SENT", "ARCHIVED", "PUBLIC"]
    ),
    default=None,
    help="Filter by memo status.",
)
@click.option(
    "--since",
    "since_iso",
    type=str,
    default=None,
    help="ISO-8601 timestamp; only memos created at/after this time.",
)
@click.option(
    "--organization-id",
    "organization_id",
    type=str,
    default=None,
    help="Org id (defaults to ALGORITHMS_ORGANIZATION_ID).",
)
@click.option(
    "--limit", "limit", type=int, default=50, help="Cap on rows returned."
)
def memo_list(
    status_value: Optional[str],
    since_iso: Optional[str],
    organization_id: Optional[str],
    limit: int,
) -> None:
    """List investment memos by status."""

    import os

    from noosphere.forecasts.scheduler import database_url_from_env
    from noosphere.models import MemoStatus
    from noosphere.store import Store

    org = organization_id or os.environ.get("ALGORITHMS_ORGANIZATION_ID", "")
    since = None
    if since_iso:
        try:
            since = datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
        except ValueError as exc:
            raise click.UsageError(f"invalid --since: {exc}")
    status = MemoStatus(status_value) if status_value else None

    store = Store.from_database_url(database_url_from_env())
    rows = store.list_investment_memos(
        organization_id=org or None,
        status=status,
        since=since,
        limit=limit,
    )
    click.echo(
        json.dumps(
            [
                {
                    "id": m.id,
                    "slug": m.slug,
                    "title": m.title,
                    "status": m.status
                    if isinstance(m.status, str)
                    else m.status.value,
                    "addressee": m.addressee,
                    "created_at": m.created_at.isoformat()
                    if m.created_at
                    else None,
                    "sent_at": m.sent_at.isoformat() if m.sent_at else None,
                    "published_at": m.published_at.isoformat()
                    if m.published_at
                    else None,
                }
                for m in rows
            ],
            indent=2,
            default=str,
        )
    )


# ── Command group: bet (prompt 15) ─────────────────────────────────────────


@click.group("bet")
def bet_cli() -> None:
    """Polymorphic-bet lifecycle (prompt 15).

    A ``BetSpec`` is the abstract claim. MARKET bets gate on the
    eight-gate safety contract via ``authorize``; non-financial bets
    (ADVISORY / STRATEGIC / SCIENTIFIC) skip authorization. ADVISORY
    and STRATEGIC bets are operator-only on the way out — the agent
    refuses to decide them unilaterally.
    """


@bet_cli.command("propose")
@click.option(
    "--memo", "memo_id", required=True, type=str, help="InvestmentMemo id."
)
@click.option(
    "--organization-id",
    "organization_id",
    type=str,
    default=None,
    help="Org id (defaults to ALGORITHMS_ORGANIZATION_ID).",
)
def bet_propose(memo_id: str, organization_id: Optional[str]) -> None:
    """Create a BetSpec from a memo's implied bet."""
    import os

    from noosphere.bets.spec import bet_spec_from_implied_bet
    from noosphere.forecasts.scheduler import database_url_from_env
    from noosphere.store import Store

    store = Store.from_database_url(database_url_from_env())
    memo = store.get_investment_memo(memo_id)
    if memo is None:
        raise click.UsageError(f"memo {memo_id!r} not found")
    org = (organization_id or memo.organization_id
           or os.environ.get("ALGORITHMS_ORGANIZATION_ID", "")).strip()
    if not org:
        raise click.UsageError("organization_id is required")
    if not memo.implied_bet:
        raise click.UsageError(
            f"memo {memo_id!r} has no implied_bet — cannot propose a BetSpec"
        )
    spec = bet_spec_from_implied_bet(
        memo.implied_bet,
        organization_id=org,
        memo_id=memo.id,
        fallback_proposition=memo.tldr or memo.title,
    )
    saved = store.put_bet_spec(spec)
    click.echo(
        json.dumps(
            {
                "ok": True,
                "bet_spec": {
                    "id": saved.id,
                    "kind": saved.kind if isinstance(saved.kind, str)
                    else saved.kind.value,
                    "status": saved.status if isinstance(saved.status, str)
                    else saved.status.value,
                    "memo_id": saved.created_by_memo_id,
                    "horizon_at": saved.horizon_at.isoformat(),
                },
            },
            indent=2,
            default=str,
        )
    )


@bet_cli.command("authorize")
@click.option("--bet", "bet_id", required=True, type=str)
@click.option(
    "--operator", "operator_id", type=str, default="operator",
    help="Operator id stamped on the authorization log line.",
)
def bet_authorize(bet_id: str, operator_id: str) -> None:
    """Authorize a MARKET_BET. Equivalent to the eight-gate authorize-live step."""

    from noosphere.bets.spec import BetKind, BetStatus
    from noosphere.forecasts.scheduler import database_url_from_env
    from noosphere.store import Store

    store = Store.from_database_url(database_url_from_env())
    spec = store.get_bet_spec(bet_id)
    if spec is None:
        raise click.UsageError(f"bet_spec {bet_id!r} not found")
    kind_value = spec.kind if isinstance(spec.kind, str) else spec.kind.value
    if kind_value != BetKind.MARKET_BET.value:
        raise click.UsageError(
            f"bet authorize only applies to MARKET_BET (got {kind_value})"
        )
    status_value = (
        spec.status if isinstance(spec.status, str) else spec.status.value
    )
    if status_value not in {BetStatus.PROPOSED.value, BetStatus.AUTHORIZED.value}:
        raise click.UsageError(
            f"cannot authorize bet in status {status_value!r}"
        )
    spec.status = BetStatus.AUTHORIZED
    store.put_bet_spec(spec)
    click.echo(
        json.dumps(
            {
                "ok": True,
                "bet_spec_id": spec.id,
                "status": BetStatus.AUTHORIZED.value,
                "operator_id": operator_id,
            },
            indent=2,
        )
    )


@bet_cli.command("resolve")
@click.option("--bet", "bet_id", required=True, type=str)
@click.option(
    "--outcome",
    type=click.Choice(
        ["CORRECT", "INCORRECT", "PARTIALLY_CORRECT", "UNDETERMINED"],
        case_sensitive=False,
    ),
    required=True,
)
@click.option(
    "--evidence",
    "evidence_ids",
    type=str,
    default="",
    help="Comma-separated artifact ids.",
)
@click.option("--note", "note", type=str, default="", help="Free-form evidence note.")
@click.option(
    "--operator", "operator_id", type=str, default="operator",
)
@click.option("--pnl-usd", "pnl_usd", type=float, default=None)
@click.option("--cost-realized", "cost_realized", type=float, default=None)
@click.option("--accuracy-score", "accuracy_score", type=float, default=None)
@click.option(
    "--audience-response", "audience_response", type=str, default=None,
    help="Operator note for ADVISORY bets.",
)
def bet_resolve(
    bet_id: str,
    outcome: str,
    evidence_ids: str,
    note: str,
    operator_id: str,
    pnl_usd: Optional[float],
    cost_realized: Optional[float],
    accuracy_score: Optional[float],
    audience_response: Optional[str],
) -> None:
    """Operator-driven resolution. Required path for ADVISORY / STRATEGIC bets."""

    from noosphere.bets.lifecycle import operator_resolve_bet
    from noosphere.forecasts.scheduler import database_url_from_env
    from noosphere.store import Store

    store = Store.from_database_url(database_url_from_env())
    evidence_artifact_ids = [
        x.strip() for x in (evidence_ids or "").split(",") if x.strip()
    ]
    spec = operator_resolve_bet(
        store,
        bet_id,
        outcome=outcome,
        evidence_note=note,
        evidence_artifact_ids=evidence_artifact_ids,
        operator_id=operator_id,
        pnl_usd=pnl_usd,
        cost_realized=cost_realized,
        accuracy_score=accuracy_score,
        audience_response=audience_response,
    )
    if spec is None:
        raise click.UsageError(f"bet_spec {bet_id!r} not found")
    click.echo(
        json.dumps(
            {
                "ok": True,
                "bet_spec_id": spec.id,
                "outcome": spec.outcome if isinstance(spec.outcome, str)
                else (spec.outcome.value if spec.outcome else None),
                "status": spec.status if isinstance(spec.status, str)
                else spec.status.value,
            },
            indent=2,
        )
    )


@bet_cli.command("list")
@click.option(
    "--kind",
    type=click.Choice(
        ["MARKET_BET", "ADVISORY_BET", "STRATEGIC_BET", "SCIENTIFIC_BET"],
        case_sensitive=False,
    ),
    default=None,
)
@click.option(
    "--status",
    type=click.Choice(
        ["PROPOSED", "AUTHORIZED", "OPEN", "RESOLVED", "CANCELLED", "EXPIRED"],
        case_sensitive=False,
    ),
    default=None,
)
@click.option(
    "--organization-id", "organization_id", type=str, default=None,
)
@click.option("--limit", "limit", type=int, default=50)
def bet_list(
    kind: Optional[str],
    status: Optional[str],
    organization_id: Optional[str],
    limit: int,
) -> None:
    """List BetSpec rows, optionally filtered by kind / status."""

    import os

    from noosphere.forecasts.scheduler import database_url_from_env
    from noosphere.store import Store

    org = (organization_id or os.environ.get("ALGORITHMS_ORGANIZATION_ID", "")
           or "").strip() or None
    store = Store.from_database_url(database_url_from_env())
    rows = store.list_bet_specs(
        organization_id=org,
        kind=kind.upper() if kind else None,
        status=status.upper() if status else None,
        limit=limit,
    )
    click.echo(
        json.dumps(
            [
                {
                    "id": b.id,
                    "kind": b.kind if isinstance(b.kind, str) else b.kind.value,
                    "status": b.status if isinstance(b.status, str)
                    else b.status.value,
                    "proposition": b.proposition,
                    "horizon_at": b.horizon_at.isoformat(),
                    "memo_id": b.created_by_memo_id,
                    "outcome": (
                        b.outcome if isinstance(b.outcome, str)
                        else (b.outcome.value if b.outcome else None)
                    ),
                }
                for b in rows
            ],
            indent=2,
            default=str,
        )
    )


# ── Command group: portfolio-agent (prompt 12) ─────────────────────────────


@click.group("portfolio-agent")
def portfolio_agent_cli() -> None:
    """Portfolio-agent admin (prompt 12).

    Portfolio agents consume SENT memos and route them to a HUMAN
    inbox, the AUTO_PAPER engine, or the AUTO_LIVE per-bet
    confirmation queue. AUTO_LIVE never auto-submits; it queues live
    bets in the existing operator console for per-bet confirmation.
    """


@portfolio_agent_cli.command("create")
@click.option("--name", required=True, type=str, help="Human-readable agent name.")
@click.option(
    "--kind",
    type=click.Choice(["HUMAN", "AUTO_PAPER", "AUTO_LIVE"], case_sensitive=False),
    default="HUMAN",
    help="Default mode for subscriptions that don't override it.",
)
@click.option(
    "--description", "description", type=str, default="", help="Short description."
)
@click.option(
    "--organization-id",
    "organization_id",
    type=str,
    default=None,
    help="Org id (defaults to ALGORITHMS_ORGANIZATION_ID env var).",
)
@click.option(
    "--ceiling",
    "ceiling",
    type=float,
    default=50.0,
    help="Soft USD ceiling applied to AUTO_PAPER / AUTO_LIVE bets.",
)
def portfolio_agent_create(
    name: str,
    kind: str,
    description: str,
    organization_id: Optional[str],
    ceiling: float,
) -> None:
    """Create a new portfolio agent in the given organization."""
    import os

    from noosphere.models import (
        PortfolioAgent,
        PortfolioAgentKind,
        PortfolioAgentStatus,
    )

    org = (organization_id or os.getenv("ALGORITHMS_ORGANIZATION_ID") or "").strip()
    if not org:
        click.echo(
            json.dumps(
                {"ok": False, "error": "organization_id is required"},
                indent=2,
            ),
            err=True,
        )
        raise SystemExit(2)

    store = _store_from_settings()
    agent = PortfolioAgent(
        organization_id=org,
        name=name,
        description=description,
        kind=PortfolioAgentKind(kind.upper()),
        status=PortfolioAgentStatus.ACTIVE,
        default_bet_ceiling_usd=float(ceiling),
    )
    saved = store.put_portfolio_agent(agent)
    click.echo(
        json.dumps(
            {
                "ok": True,
                "agent": {
                    "id": saved.id,
                    "name": saved.name,
                    "kind": (
                        saved.kind.value
                        if hasattr(saved.kind, "value")
                        else str(saved.kind)
                    ),
                    "status": (
                        saved.status.value
                        if hasattr(saved.status, "value")
                        else str(saved.status)
                    ),
                    "default_bet_ceiling_usd": saved.default_bet_ceiling_usd,
                    "organization_id": saved.organization_id,
                },
            },
            indent=2,
            default=str,
        )
    )


@portfolio_agent_cli.command("subscribe")
@click.option("--agent", "agent_id", required=True, type=str, help="Agent id.")
@click.option(
    "--topic",
    "topic",
    type=str,
    default="*",
    help='Topic to match (use "*" for wildcard).',
)
@click.option(
    "--question-type",
    "question_type",
    type=click.Choice(
        ["INVESTMENT_DECISION", "FORECAST", "EXPLANATORY", "STRATEGIC"],
        case_sensitive=False,
    ),
    required=True,
    help="Memo question type to match.",
)
@click.option(
    "--mode",
    "mode",
    type=click.Choice(
        ["HUMAN", "AUTO_PAPER", "AUTO_LIVE"], case_sensitive=False
    ),
    default=None,
    help="Override the agent's default kind for this subscription only.",
)
def portfolio_agent_subscribe(
    agent_id: str,
    topic: str,
    question_type: str,
    mode: Optional[str],
) -> None:
    """Add a (topic, question_type, mode) subscription to a portfolio agent.

    AUTO_PAPER promotion is gated by
    :data:`noosphere.portfolio_agent.router.AUTO_PAPER_REQUIRES_CALIBRATION_THRESHOLD`
    — the CLI checks the threshold against historical HUMAN-mode
    dispatches and refuses to promote until it clears.
    """
    from noosphere.models import (
        MemoQuestionType,
        PortfolioAgentKind,
        PortfolioAgentSubscription,
    )
    from noosphere.portfolio_agent.router import can_promote_to_auto_paper

    store = _store_from_settings()
    agent = store.get_portfolio_agent(agent_id)
    if agent is None:
        click.echo(
            json.dumps({"ok": False, "error": f"unknown agent: {agent_id}"}, indent=2),
            err=True,
        )
        raise SystemExit(2)

    mode_enum = (
        PortfolioAgentKind(mode.upper())
        if mode is not None
        else None
    )
    if mode_enum == PortfolioAgentKind.AUTO_PAPER:
        allowed, reason = can_promote_to_auto_paper(
            store,
            organization_id=agent.organization_id,
            topic=topic,
            question_type=MemoQuestionType(question_type.upper()),
        )
        if not allowed:
            click.echo(
                json.dumps(
                    {
                        "ok": False,
                        "error": "AUTO_PAPER promotion blocked",
                        "reason": reason,
                    },
                    indent=2,
                ),
                err=True,
            )
            raise SystemExit(2)

    sub = PortfolioAgentSubscription(
        topic=topic,
        question_type=MemoQuestionType(question_type.upper()),
        mode=mode_enum,
    )
    agent.subscriptions.append(sub)
    saved = store.put_portfolio_agent(agent)
    click.echo(
        json.dumps(
            {
                "ok": True,
                "agent_id": saved.id,
                "subscription_count": len(saved.subscriptions),
                "added": {
                    "topic": sub.topic,
                    "question_type": (
                        sub.question_type.value
                        if hasattr(sub.question_type, "value")
                        else str(sub.question_type)
                    ),
                    "mode": (
                        sub.mode.value
                        if sub.mode is not None and hasattr(sub.mode, "value")
                        else (str(sub.mode) if sub.mode else None)
                    ),
                },
            },
            indent=2,
            default=str,
        )
    )


@portfolio_agent_cli.command("inbox")
@click.option("--agent", "agent_id", required=True, type=str, help="Agent id.")
@click.option("--limit", "limit", type=int, default=50)
def portfolio_agent_inbox(agent_id: str, limit: int) -> None:
    """List PENDING dispatches for a HUMAN-mode portfolio agent."""
    from noosphere.models import MemoDispatchOutcome

    store = _store_from_settings()
    agent = store.get_portfolio_agent(agent_id)
    if agent is None:
        click.echo(
            json.dumps({"ok": False, "error": f"unknown agent: {agent_id}"}, indent=2),
            err=True,
        )
        raise SystemExit(2)

    dispatches = store.list_memo_dispatches(
        agent_id=agent_id,
        outcome=MemoDispatchOutcome.PENDING,
        limit=limit,
    )
    rows: List[dict[str, Any]] = []
    for d in dispatches:
        memo = store.get_investment_memo(d.memo_id)
        rows.append(
            {
                "dispatch_id": d.id,
                "memo_id": d.memo_id,
                "memo_title": getattr(memo, "title", None) if memo else None,
                "dispatched_at": (
                    d.dispatched_at.isoformat() if d.dispatched_at else None
                ),
                "eight_gate_status": d.eight_gate_status,
                "deferred_until": (
                    d.deferred_until.isoformat() if d.deferred_until else None
                ),
            }
        )
    click.echo(
        json.dumps(
            {
                "ok": True,
                "agent_id": agent_id,
                "pending_count": len(rows),
                "dispatches": rows,
            },
            indent=2,
            default=str,
        )
    )


# ── Knowledge-graph commands (Round 19 prompt 13) ──────────────────────────


@click.group("graph")
def graph_cli() -> None:
    """Knowledge-graph build + edge reasoning commands."""


@graph_cli.command("build")
@click.option("--org", "org_id", required=True, type=str, help="Organization id.")
@click.option(
    "--no-persist",
    is_flag=True,
    default=False,
    help="Build the snapshot but do not write it to the snapshot table.",
)
def graph_build_command(org_id: str, no_persist: bool) -> None:
    """Full rebuild of one org's knowledge graph snapshot."""
    from noosphere.knowledge_graph import build_for_org

    store = _store_from_settings()
    snap = build_for_org(store, org_id, persist=not no_persist)
    click.echo(
        json.dumps(
            {
                "ok": True,
                "snapshot_id": snap.id,
                "node_count": snap.node_count,
                "edge_count": snap.edge_count,
                "persisted": not no_persist,
                "notes": snap.notes,
            },
            indent=2,
            default=str,
        )
    )


@graph_cli.command("reason")
@click.option("--org", "org_id", required=True, type=str, help="Organization id.")
@click.option("--node-a", "node_a_ref", required=True, type=str)
@click.option("--node-b", "node_b_ref", required=True, type=str)
@click.option(
    "--edge-type",
    "edge_kind",
    required=True,
    type=str,
    help="DERIVED_FROM | INVOKES | CONTRADICTS | SUPPORTS | APPLIES_TO | "
    "PREDICTS | CITES | MENTIONS",
)
def graph_reason_command(
    org_id: str, node_a_ref: str, node_b_ref: str, edge_kind: str
) -> None:
    """Ad-hoc agent reasoning over a single edge."""
    import asyncio

    from noosphere.knowledge_graph.agent_reasoner import reason_about_edge
    from noosphere.models import KGEdge, KGEdgeKind, KGNode, KGNodeKind

    store = _store_from_settings()
    snap = store.get_latest_graph_snapshot(org_id)
    if snap is None:
        click.echo(
            json.dumps(
                {"ok": False, "error": "no snapshot for org; run `graph build` first"}
            ),
            err=True,
        )
        raise SystemExit(2)

    def _resolve(ref: str) -> KGNode | None:
        for n in snap.nodes:
            if n.id == ref or n.ref == ref:
                return n
        return None

    a = _resolve(node_a_ref)
    b = _resolve(node_b_ref)
    if a is None or b is None:
        click.echo(
            json.dumps(
                {
                    "ok": False,
                    "error": "node ref(s) not found in latest snapshot",
                    "node_a_found": a is not None,
                    "node_b_found": b is not None,
                }
            ),
            err=True,
        )
        raise SystemExit(2)

    try:
        kind_enum = KGEdgeKind(edge_kind.strip().upper())
    except ValueError:
        click.echo(
            json.dumps({"ok": False, "error": f"unknown edge type: {edge_kind}"}),
            err=True,
        )
        raise SystemExit(2)

    edge = next(
        (
            e
            for e in snap.edges
            if e.src == a.id and e.dst == b.id and str(e.kind) == kind_enum.value
        ),
        None,
    )
    if edge is None:
        edge = KGEdge(
            id="kgedge_synthetic",
            src=a.id,
            dst=b.id,
            kind=kind_enum,
            weight=0.0,
            attrs={"synthetic": True},
        )

    llm = None
    try:
        from noosphere.llm import llm_client_from_settings

        llm = llm_client_from_settings()
    except Exception:
        llm = None

    result = asyncio.run(
        reason_about_edge(a, b, edge, store=store, llm=llm)
    )
    click.echo(json.dumps(result.model_dump(mode="json"), indent=2, default=str))


@graph_cli.command("stats")
@click.option("--org", "org_id", required=True, type=str, help="Organization id.")
def graph_stats_command(org_id: str) -> None:
    """Node/edge counts by type plus density for the latest snapshot."""
    store = _store_from_settings()
    snap = store.get_latest_graph_snapshot(org_id)
    if snap is None:
        click.echo(json.dumps({"ok": False, "error": "no snapshot"}), err=True)
        raise SystemExit(2)
    node_counts: dict[str, int] = {}
    for n in snap.nodes:
        k = n.kind.value if hasattr(n.kind, "value") else str(n.kind)
        node_counts[k] = node_counts.get(k, 0) + 1
    edge_counts: dict[str, int] = {}
    for e in snap.edges:
        k = e.kind.value if hasattr(e.kind, "value") else str(e.kind)
        edge_counts[k] = edge_counts.get(k, 0) + 1
    n = snap.node_count or len(snap.nodes)
    e = snap.edge_count or len(snap.edges)
    max_edges = max(1, n * (n - 1)) if n > 1 else 1
    density = (e / max_edges) if max_edges else 0.0
    click.echo(
        json.dumps(
            {
                "ok": True,
                "snapshot_id": snap.id,
                "snapshot_at": snap.snapshot_at.isoformat()
                if snap.snapshot_at
                else None,
                "node_count": n,
                "edge_count": e,
                "density": density,
                "nodes_by_kind": node_counts,
                "edges_by_kind": edge_counts,
            },
            indent=2,
            default=str,
        )
    )


# ── Command group: dialectic (prompt 14) ───────────────────────────────────


@click.group("dialectic")
def dialectic_cli() -> None:
    """Dialectic live recording mode (prompt 14).

    Create + manage podcast / meeting sessions whose utterances are
    transcribed live, principle-extracted (PROVISIONAL until founder
    triage), and contradiction-checked against the running session and
    the firm's committed history.
    """


def _get_dialectic_store():
    import os

    from noosphere.forecasts.scheduler import database_url_from_env
    from noosphere.store import Store

    url = database_url_from_env() or os.environ.get("THESEUS_DATABASE_URL")
    if not url:
        raise click.UsageError(
            "Set THESEUS_DATABASE_URL (or the scheduler env vars) before "
            "running dialectic commands."
        )
    return Store(url)


def _resolve_org(organization_id: Optional[str]) -> str:
    import os

    org = (
        organization_id
        or os.environ.get("DIALECTIC_ORG_ID")
        or os.environ.get("ALGORITHMS_ORG_ID")
        or os.environ.get("ALGORITHMS_ORGANIZATION_ID")
    )
    if not org:
        raise click.UsageError(
            "organization_id is required (pass --organization-id or set "
            "DIALECTIC_ORG_ID)."
        )
    return org


@dialectic_cli.command("record")
@click.option("--title", required=True, type=str, help="Session title.")
@click.option(
    "--speakers",
    required=True,
    type=str,
    help="Comma-separated speaker display names.",
)
@click.option(
    "--organization-id",
    "organization_id",
    type=str,
    default=None,
    help="Org id (defaults to DIALECTIC_ORG_ID).",
)
@click.option(
    "--visibility",
    type=click.Choice(["PRIVATE", "PUBLIC"]),
    default="PRIVATE",
)
def dialectic_record(
    title: str,
    speakers: str,
    organization_id: Optional[str],
    visibility: str,
) -> None:
    """Create a new live-recording session (un-consented).

    Participants must individually flip to consented=True before the
    recorder will start streaming. This command prints the session id
    and the per-participant consent URLs.
    """

    from dialectic.live_recorder import build_default_session
    from noosphere.models import DialecticVisibility

    store = _get_dialectic_store()
    org = _resolve_org(organization_id)
    names = [n.strip() for n in speakers.split(",") if n.strip()]
    if not names:
        raise click.UsageError("--speakers must list at least one name")
    session = build_default_session(
        organization_id=org, title=title, speaker_names=names
    )
    session.visibility = DialecticVisibility(visibility)
    store.put_dialectic_session(session)
    payload = {
        "session_id": session.id,
        "title": session.title,
        "visibility": session.visibility.value,
        "status": session.status.value,
        "participants": [
            {
                "speaker_id": p.speaker_id,
                "display_name": p.display_name,
                "consented": p.consented,
            }
            for p in session.participants
        ],
    }
    click.echo(json.dumps(payload, indent=2, default=str))


@dialectic_cli.command("sessions")
@click.option(
    "--organization-id",
    "organization_id",
    type=str,
    default=None,
)
@click.option(
    "--status",
    "status_filter",
    type=click.Choice(
        ["RECORDING", "PROCESSING", "COMPLETE", "FAILED", "ARCHIVED"]
    ),
    default=None,
)
@click.option("--limit", type=int, default=50)
def dialectic_sessions(
    organization_id: Optional[str],
    status_filter: Optional[str],
    limit: int,
) -> None:
    """List dialectic sessions, optionally filtered by status."""
    store = _get_dialectic_store()
    org = _resolve_org(organization_id)
    sessions = store.list_dialectic_sessions(
        org, status=status_filter, limit=limit
    )
    out = [
        {
            "id": s.id,
            "title": s.title,
            "status": s.status.value,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "live_contradictions_detected": s.live_contradictions_detected,
            "principles_extracted": s.principles_extracted,
        }
        for s in sessions
    ]
    click.echo(json.dumps(out, indent=2, default=str))


@dialectic_cli.command("triage")
@click.option("--session", "session_id", required=True, type=str)
def dialectic_triage(session_id: str) -> None:
    """Print the triage queue for a finished session.

    Provisional principles surface here so the founder can accept,
    reject, or edit before any of them get promoted to ACTIVE.
    Nothing is promoted by this command — it is a read-only view.
    """
    store = _get_dialectic_store()
    session = store.get_dialectic_session(session_id)
    if session is None:
        raise click.UsageError(f"session {session_id} not found")
    utterances = store.list_dialectic_utterances(session_id)
    queue = []
    for u in utterances:
        if not u.derived_principle_ids:
            continue
        queue.append(
            {
                "utterance_id": u.id,
                "speaker_id": u.speaker_id,
                "text": u.text,
                "provisional_principle_ids": u.derived_principle_ids,
                "status": "PROVISIONAL",
            }
        )
    click.echo(
        json.dumps(
            {
                "session_id": session_id,
                "status": session.status.value,
                "queue_size": len(queue),
                "queue": queue,
            },
            indent=2,
            default=str,
        )
    )


# ── Command: env (validation + reporting) ───────────────────────────────────


@click.group("env")
def env_cli() -> None:
    """Env-var validation against the canonical registry.

    The registry lives in ``noosphere.core.env_validation`` and is the
    single source of truth for which vars are required in which mode.
    """


@env_cli.command("validate")
@click.option("--mode", "mode", type=str, default=None,
              help="Override THESEUS_MODE for the validation run.")
def env_validate(mode: Optional[str]) -> None:
    """Validate the current env against the registry. Exit 1 on failure."""
    from noosphere.core.env_validation import parse_mode, validate_env
    from noosphere.scripts.validate_live_credentials import render_report

    selected = parse_mode(mode or __import__("os").environ.get("THESEUS_MODE"))
    report = validate_env(selected)
    click.echo(render_report(report))
    if report.failures():
        raise SystemExit(1)


@env_cli.command("report")
def env_report() -> None:
    """Print the validation report as JSON (the /readyz/env response)."""
    import json as _json
    from noosphere.core.env_validation import parse_mode, validate_env

    selected = parse_mode(__import__("os").environ.get("THESEUS_MODE"))
    report = validate_env(selected)
    click.echo(_json.dumps(report.to_dict(), indent=2, sort_keys=True))


@env_cli.command("required")
@click.option("--mode", "mode", type=str, default=None,
              help="Mode to list required vars for (default THESEUS_MODE).")
def env_required(mode: Optional[str]) -> None:
    """List every required env var for the named mode (one per line)."""
    from noosphere.core.env_validation import parse_mode, required_vars_for_mode

    selected = parse_mode(mode or __import__("os").environ.get("THESEUS_MODE"))
    for name in required_vars_for_mode(selected):
        click.echo(name)


# ── Plugin discovery ────────────────────────────────────────────────────────
from noosphere.cli_commands import register_commands

cli.add_command(forecasts_cli)
cli.add_command(equities_cli)
cli.add_command(quantitative_cli)
cli.add_command(algorithms_cli)
cli.add_command(contradiction_cli)
cli.add_command(library_cli)
cli.add_command(synthesizer_cli)
cli.add_command(memo_cli)
cli.add_command(bet_cli)
cli.add_command(portfolio_agent_cli)
cli.add_command(graph_cli)
cli.add_command(dialectic_cli)
cli.add_command(env_cli)
register_commands(cli)


if __name__ == "__main__":
    cli()
