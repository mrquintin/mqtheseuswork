"""CLI commands for method documentation compilation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

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


def _parse_ref(ref: str):
    from noosphere.models import MethodRef
    name, version = (ref.split("@", 1) + ["latest"])[:2]
    return MethodRef(name=name, version=version)


@click.group("docs")
def cli() -> None:
    """Documentation: compile signed method-doc bundles."""


@cli.command("build")
@click.argument("ref")
@click.option("--out", "out_dir", type=click.Path(), default="./method_docs",
              help="Output directory")
@click.option("--reviewed-by", type=str, default=None, help="Reviewer name")
@click.option("--require-review", is_flag=True, help="Require review signature")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def build_cmd(ref: str, out_dir: str, reviewed_by: str | None,
              require_review: bool, as_json: bool) -> None:
    """Compile a method-doc bundle. REF is name[@version]."""
    from noosphere.docgen import compile_method_doc
    from noosphere.ledger import KeyRing

    store = _get_store()
    keyring = KeyRing(store)
    method_ref = _parse_ref(ref)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    with console.status("[bold green]Compiling documentation...", spinner="dots"):
        doc = compile_method_doc(
            method_ref, out, keyring,
            reviewed_by=reviewed_by,
            require_review=require_review,
        )

    if as_json:
        _render(doc.model_dump(), True)
        return
    table = Table(title=f"MethodDoc: {ref}", show_header=False)
    table.add_row("Spec", str(doc.spec_md_path))
    table.add_row("Rationale", str(doc.rationale_md_path))
    table.add_row("Calibration", str(doc.calibration_md_path))
    table.add_row("Transfer", str(doc.transfer_md_path))
    table.add_row("Template", doc.template_version)
    if doc.signed_by:
        table.add_row("Signed by", doc.signed_by)
    console.print(table)


@cli.command("paper")
@click.argument("seed_conclusion_id", required=False)
@click.option(
    "--cluster-id",
    type=str,
    default=None,
    help="Override the cluster id used for the artifact slug.",
)
@click.option(
    "--out-root",
    "out_root",
    type=click.Path(),
    default="docs/research/auto",
    help="Directory where paper drafts land. Existing slug subdirs are reused.",
)
@click.option(
    "--title", type=str, default=None, help="Override the paper title."
)
@click.option(
    "--no-pdf",
    is_flag=True,
    default=False,
    help="Skip pdflatex; emit only the .tex file.",
)
@click.option("--list", "list_only", is_flag=True, default=False,
              help="List existing drafts under --out-root and exit.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def paper_cmd(
    seed_conclusion_id: str | None,
    cluster_id: str | None,
    out_root: str,
    title: str | None,
    no_pdf: bool,
    list_only: bool,
    as_json: bool,
) -> None:
    """Generate (or list) machine-drafted, founder-reviewed papers.

    Provide a SEED_CONCLUSION_ID to draft a new paper; the cluster
    selector walks the cascade to assemble the supporting cluster.
    With --list, this command instead prints existing drafts under
    --out-root.
    """
    from noosphere.docgen.paper_generator import (
        discover_paper_drafts,
        generate_paper,
    )

    out_dir = Path(out_root)

    if list_only:
        drafts = discover_paper_drafts(out_dir)
        if as_json:
            _render(drafts, True)
            return
        if not drafts:
            console.print("[dim]No drafts under {0}[/dim]".format(out_dir))
            return
        table = Table(title=f"Auto-paper drafts ({out_dir})")
        table.add_column("Slug")
        table.add_column("Cluster")
        table.add_column("Lead conclusion")
        table.add_column("State")
        table.add_column("PDF?")
        for d in drafts:
            table.add_row(
                d.get("slug", ""),
                d.get("cluster_id", ""),
                d.get("lead_conclusion_id", ""),
                d.get("review_state", ""),
                "yes" if d.get("pdf_path") else "no",
            )
        console.print(table)
        return

    if not seed_conclusion_id:
        raise click.UsageError(
            "SEED_CONCLUSION_ID is required unless --list is passed."
        )

    store = _get_store()
    with console.status("[bold green]Drafting paper...", spinner="dots"):
        artifact = generate_paper(
            store,
            seed_conclusion_id=seed_conclusion_id,
            cluster_id=cluster_id,
            out_root=out_dir,
            title=title,
            build_pdf=not no_pdf,
        )

    if as_json:
        _render(
            {
                "cluster_id": artifact.cluster_id,
                "slug": artifact.slug,
                "tex_path": str(artifact.tex_path),
                "pdf_path": str(artifact.pdf_path) if artifact.pdf_path else None,
                "row_refs": [list(r) for r in artifact.row_refs],
                "todo_count": artifact.todo_count,
            },
            True,
        )
        return

    table = Table(title=f"Auto-paper draft: {artifact.slug}", show_header=False)
    table.add_row("Cluster", artifact.cluster_id)
    table.add_row("TeX", str(artifact.tex_path))
    table.add_row(
        "PDF",
        str(artifact.pdf_path) if artifact.pdf_path else "(not built)",
    )
    table.add_row("Row references", str(len(artifact.row_refs)))
    table.add_row("TODO markers", str(artifact.todo_count))
    console.print(table)
    console.print(
        "[dim]Disclosure: machine-drafted, founder-reviewed. "
        "The .tex file is the source of truth; PDF is a build artifact.[/dim]"
    )


@cli.command("export-articles")
@click.option(
    "--since",
    "since",
    required=True,
    type=str,
    help="Start of the publish window (YYYY-MM-DD or ISO-8601 datetime).",
)
@click.option(
    "--until",
    "until",
    type=str,
    default=None,
    help="Optional inclusive end of the publish window.",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["pdf", "html"], case_sensitive=False),
    default="pdf",
    help="Output format. PDF requires WeasyPrint.",
)
@click.option(
    "--out",
    "out_path",
    type=click.Path(),
    required=True,
    help="Output file. For --format pdf an HTML companion is written too.",
)
@click.option(
    "--site-base",
    type=str,
    default=None,
    help="Override the canonical web base URL written into endnotes.",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def export_articles_cmd(
    since: str,
    until: str | None,
    fmt: str,
    out_path: str,
    site_base: str | None,
    as_json: bool,
) -> None:
    """Bind every published article in a window into one printable PDF.

    Visibility is the same as the public site: the export reads the
    same ``PublishedConclusion`` table the blog reads from, so a
    founder running this on their workstation cannot leak anything
    the public site doesn't already show.
    """
    from noosphere.docgen.articles_export import export_articles

    since_dt = _parse_datetime(since, field="--since")
    until_dt = _parse_datetime(until, field="--until") if until else None
    store = _get_store()

    with console.status("[bold green]Composing bound articles...", spinner="dots"):
        manifest = export_articles(
            store,
            since=since_dt,
            until=until_dt,
            out_path=Path(out_path),
            fmt=fmt.lower(),
            site_base=site_base,
        )

    if as_json:
        _render(
            {
                "article_count": manifest.article_count,
                "out_path": str(manifest.out_path),
                "html_path": str(manifest.html_path),
                "pdf_path": str(manifest.pdf_path) if manifest.pdf_path else None,
                "skipped_pdf_reason": manifest.skipped_pdf_reason,
            },
            True,
        )
        return

    table = Table(
        title=f"Bound articles export · {manifest.article_count} article(s)",
        show_header=False,
    )
    table.add_row("HTML", str(manifest.html_path))
    table.add_row(
        "PDF",
        str(manifest.pdf_path)
        if manifest.pdf_path
        else (manifest.skipped_pdf_reason or "(not built)"),
    )
    console.print(table)


@cli.command("seasonal")
@click.argument("quarter_spec", required=False)
@click.option(
    "--year", type=int, default=None, help="Year (e.g. 2026); pair with --q."
)
@click.option(
    "--q", "quarter_n", type=int, default=None, help="Quarter 1..4."
)
@click.option(
    "--out-root",
    "out_root",
    type=click.Path(),
    default="docs/seasonal",
    help="Directory under which review slug subdirs live.",
)
@click.option(
    "--principles",
    "principles_path",
    type=click.Path(),
    default=None,
    help="Optional principle-distillation drafts JSON to source the Principles section.",
)
@click.option(
    "--narrative/--no-narrative",
    "with_narrative",
    default=False,
    help="Run the LLM narrative pass after assembling the structured object.",
)
@click.option(
    "--no-pdf",
    is_flag=True,
    default=False,
    help="Skip pdflatex; emit only the .tex + .json files.",
)
@click.option(
    "--list",
    "list_only",
    is_flag=True,
    default=False,
    help="List existing reviews under --out-root and exit.",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def seasonal_cmd(
    quarter_spec: str | None,
    year: int | None,
    quarter_n: int | None,
    out_root: str,
    principles_path: str | None,
    with_narrative: bool,
    no_pdf: bool,
    list_only: bool,
    as_json: bool,
) -> None:
    """Assemble a quarterly seasonal research review.

    QUARTER_SPEC accepts ``2026Q2`` or ``2026-Q2``; alternatively pass
    ``--year`` and ``--q``. With ``--list``, prints existing reviews
    under ``--out-root`` and exits.
    """
    from pathlib import Path

    from noosphere.docgen.seasonal_review import (
        assemble_seasonal_review,
        discover_seasonal_reviews,
        parse_quarter,
        render_seasonal_review,
        write_narrative,
    )

    out_dir = Path(out_root)

    if list_only:
        reviews = discover_seasonal_reviews(out_dir)
        if as_json:
            _render(reviews, True)
            return
        if not reviews:
            console.print(f"[dim]No seasonal reviews under {out_dir}[/dim]")
            return
        table = Table(title=f"Seasonal reviews ({out_dir})")
        table.add_column("Slug")
        table.add_column("Quarter")
        table.add_column("State")
        table.add_column("PDF?")
        for r in reviews:
            window = r.get("window") or {}
            table.add_row(
                r.get("slug", ""),
                window.get("label", ""),
                r.get("review_state", ""),
                "yes" if r.get("pdf_path") else "no",
            )
        console.print(table)
        return

    if quarter_spec:
        window = parse_quarter(quarter_spec)
        year_arg, quarter_arg = window.year, window.quarter
    elif year is not None and quarter_n is not None:
        year_arg, quarter_arg = year, quarter_n
    else:
        raise click.UsageError(
            "Pass either QUARTER_SPEC (e.g. 2026Q2) or --year and --q together."
        )

    store = _get_store()
    drafts = Path(principles_path) if principles_path else None
    with console.status("[bold green]Assembling seasonal review...", spinner="dots"):
        review = assemble_seasonal_review(
            store,
            year=year_arg,
            quarter=quarter_arg,
            principles_drafts_path=drafts,
        )

    narrative = None
    if with_narrative:
        from noosphere.llm import llm_client_from_settings

        client = llm_client_from_settings()
        with console.status(
            "[bold green]Writing seasonal narrative prose...", spinner="dots"
        ):
            narrative = write_narrative(review, client)

    artifact = render_seasonal_review(
        review,
        narrative=narrative,
        out_root=out_dir,
        build_pdf=not no_pdf,
    )

    if as_json:
        _render(
            {
                "slug": artifact.slug,
                "tex_path": str(artifact.tex_path),
                "json_path": str(artifact.json_path),
                "pdf_path": str(artifact.pdf_path) if artifact.pdf_path else None,
                "review_state": artifact.review_state,
                "structured": review.to_dict(),
            },
            True,
        )
        return

    table = Table(
        title=f"Seasonal review: {artifact.slug}",
        show_header=False,
    )
    table.add_row("Window", review.window.label)
    table.add_row("TeX", str(artifact.tex_path))
    table.add_row("JSON", str(artifact.json_path))
    table.add_row(
        "PDF",
        str(artifact.pdf_path) if artifact.pdf_path else "(not built)",
    )
    table.add_row("Self-critique findings", str(len(review.self_critique.findings)))
    console.print(table)
    console.print(
        "[dim]Disclosure: machine-drafted, founder-reviewed. "
        "Sign-off is required before this review is treated as published.[/dim]"
    )


def _parse_datetime(raw: str, *, field: str) -> datetime:
    """Accept ``YYYY-MM-DD`` or any ISO-8601 datetime."""
    text = raw.strip()
    try:
        if len(text) == 10 and text[4] == "-" and text[7] == "-":
            return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        # ``fromisoformat`` accepts ``...Z`` only on 3.11+, so normalize.
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise click.BadParameter(
            f"{field} must be YYYY-MM-DD or ISO-8601: {raw!r} ({exc})"
        ) from exc
