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
from typing import Optional, List

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text

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

@cli.command()
@click.option("--report", is_flag=True,
              help="Show detailed coherence report")
@click.option("--principle-id", type=str, default=None,
              help="Analyze specific principle by ID")
@click.option("--data-dir", type=click.Path(), default=None,
              help="Data directory override")
def coherence(report, principle_id, data_dir):
    """Run coherence analysis on the knowledge graph.

    Example:
        noosphere coherence --report
    """
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


# ── Plugin discovery ────────────────────────────────────────────────────────
from noosphere.cli_commands import register_commands

cli.add_command(forecasts_cli)
register_commands(cli)


if __name__ == "__main__":
    cli()
