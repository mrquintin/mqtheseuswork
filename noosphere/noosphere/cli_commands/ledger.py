"""CLI commands for the Ledger (append-only signed audit log) subsystem."""

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


def _parse_ts(val: Optional[str]) -> Optional[datetime]:
    if val is None:
        return None
    return datetime.fromisoformat(val).replace(tzinfo=timezone.utc)


@click.group("ledger")
def cli() -> None:
    """Ledger: verify chain integrity and export audit bundles."""


@cli.command("verify")
@click.option("--since", type=str, default=None, help="Start timestamp (ISO 8601)")
@click.option("--until", type=str, default=None, help="End timestamp (ISO 8601)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def verify(since: Optional[str], until: Optional[str], as_json: bool) -> None:
    """Verify ledger chain integrity and signatures."""
    from noosphere.ledger import KeyRing, verify as ledger_verify

    store = _get_store()
    keyring = KeyRing(store)
    report = ledger_verify(store, keyring, since=_parse_ts(since),
                           until=_parse_ts(until))
    if as_json:
        click.echo(json.dumps({
            "total_entries": report.total_entries,
            "chain_valid": report.chain_valid,
            "signatures_valid": report.signatures_valid,
            "ok": report.ok,
            "issues": [{"entry_id": i.entry_id, "issue_type": i.issue_type,
                        "detail": i.detail} for i in report.issues],
        }, indent=2, default=str))
        return
    style = "green" if report.ok else "red"
    table = Table(title="Ledger Verification", show_header=False)
    table.add_row("Total entries", str(report.total_entries))
    table.add_row("Chain valid", f"[{style}]{report.chain_valid}[/{style}]")
    table.add_row("Signatures valid", f"[{style}]{report.signatures_valid}[/{style}]")
    table.add_row("Issues", str(len(report.issues)))
    console.print(table)
    if report.issues:
        it = Table(title="Issues", show_header=True)
        it.add_column("Entry", style="yellow", max_width=12)
        it.add_column("Type")
        it.add_column("Detail", max_width=50)
        for issue in report.issues[:20]:
            it.add_row(issue.entry_id[:12], issue.issue_type, issue.detail[:50])
        console.print(it)


@cli.command("export")
@click.option("--from", "from_id", required=True, help="Starting ledger entry ID")
@click.option("--to", "to_id", required=True, help="Ending ledger entry ID")
@click.option("--out", "out_path", required=True, type=click.Path(),
              help="Output file path (.tar.gz)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def export(from_id: str, to_id: str, out_path: str, as_json: bool) -> None:
    """Export a ledger slice as a self-verifying bundle."""
    from pathlib import Path
    from noosphere.ledger import KeyRing, export_bundle

    store = _get_store()
    keyring = KeyRing(store)
    result = export_bundle(store, keyring, from_id=from_id, to_id=to_id,
                           out_path=Path(out_path))
    if as_json:
        click.echo(json.dumps({"path": str(result)}, indent=2))
        return
    console.print(f"[bold green]✓ Bundle exported to {result}[/bold green]")
