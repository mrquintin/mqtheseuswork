"""
Click-based CLI for Noosphere — The Brain of the Firm.

Provides command-line access to all orchestrator functionality with beautiful
terminal output via Rich library.

Commands:
  ingest       Ingest a transcript and update the knowledge graph
  ask          Query the inference engine
  graph        Export the knowledge graph
  coherence    Run coherence analysis
  evolution    Track principle evolution over time
  stats        Display system statistics
  search       Semantic search over principles
  contradictions  Find contradictions in the graph
  principles   List principles with filters
"""

import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text

from noosphere.orchestrator import NoosphereOrchestrator
from noosphere.models import Discipline

# ── Setup ────────────────────────────────────────────────────────────────────

console = Console()

# Suppress noosphere internal logging in CLI (except errors)
logging.getLogger("noosphere").setLevel(logging.WARNING)


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
    return NoosphereOrchestrator(data_dir or "./noosphere_data")


# ── CLI Group ────────────────────────────────────────────────────────────────

@click.group(invoke_without_command=True)
@click.version_option(version="0.1.0", prog_name="noosphere")
@click.pass_context
def cli(ctx):
    """Noosphere CLI — The Brain of the Firm knowledge system."""
    if ctx.invoked_subcommand is None:
        # Show help if no subcommand
        click.echo(ctx.get_help())


# ── Command: ingest ─────────────────────────────────────────────────────────

@cli.command()
@click.argument("transcript_path", type=click.Path(exists=True))
@click.option("--episode", "episode_num", type=int, required=True,
              help="Episode number")
@click.option("--date", "episode_date", type=str, required=True,
              help="Episode date (YYYY-MM-DD)")
@click.option("--title", type=str, default="",
              help="Episode title")
@click.option("--speakers", type=str, default="",
              help="Comma-separated list of speaker names")
@click.option("--data-dir", type=click.Path(), default=None,
              help="Data directory override")
def ingest(transcript_path, episode_num, episode_date, title, speakers, data_dir):
    """Ingest a transcript episode into the knowledge graph.

    Full pipeline: parse → extract claims → embed → classify → distill
    principles → update graph → coherence check → save.

    Example:
        noosphere ingest transcript.txt --episode 42 --date 2026-04-11 \\
          --title "Building AI" --speakers "Alice,Bob"
    """
    try:
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

                for a_id, b_id, severity in coh_report.contradictions_found[:10]:
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
        table.add_row("Principles", str(stats_dict["principle_count"]))
        table.add_row("Claims", str(stats_dict["claim_count"]))
        table.add_row("Relationships", str(stats_dict["relationship_count"]))
        table.add_row("Episodes", str(stats_dict["episode_count"]))
        table.add_row("Unique Disciplines", str(stats_dict["unique_disciplines"]))
        table.add_row("Temporal Snapshots", str(stats_dict["temporal_snapshots"]))
        table.add_row("Average Coherence", f"{stats_dict['average_coherence_score']:.3f}")
        table.add_row("Average Conviction", f"{stats_dict['average_conviction_score']:.3f}")

        if stats_dict["first_episode"]:
            table.add_row("First Episode", stats_dict["first_episode"])
        if stats_dict["last_episode"]:
            table.add_row("Last Episode", stats_dict["last_episode"])

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

        for a_id, b_id, severity in sorted(contras, key=lambda x: x[2], reverse=True):
            # Get principle texts for context
            a_principle = orch.get_principle(a_id)
            b_principle = orch.get_principle(b_id)

            a_text = (a_principle.text[:40] + "...") if a_principle else a_id[:8]
            b_text = (b_principle.text[:40] + "...") if b_principle else b_id[:8]

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


if __name__ == "__main__":
    cli()
