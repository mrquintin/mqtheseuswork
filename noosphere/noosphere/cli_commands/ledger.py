"""CLI commands for the Ledger (append-only signed audit log) subsystem."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

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


# ── publication signing ──────────────────────────────────────────────


def _publication_keyring(key_dir: Optional[str] = None):
    from noosphere.ledger.publication_signing import PublicationKeyring

    return PublicationKeyring(Path(key_dir) if key_dir else None)


@cli.command("publication-keygen")
@click.option("--key-dir", type=click.Path(), default=None,
              help="Override key directory (default ~/.theseus/keys/publication)")
@click.option("--rotate", is_flag=True,
              help="Rotate: generate a new key even if one exists; old keys remain valid for verifying historical material.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def publication_keygen(key_dir: Optional[str], rotate: bool, as_json: bool) -> None:
    """Generate (or rotate) the firm's publication signing key."""
    kr = _publication_keyring(key_dir)
    if rotate:
        fp = kr.rotate()
        action = "rotated"
    else:
        existing = kr.active_fingerprint()
        if existing and (kr.keys_dir / existing / "signing.key").is_file():
            if as_json:
                click.echo(json.dumps({"fingerprint": existing, "action": "noop"}, indent=2))
            else:
                console.print(
                    f"[yellow]Active publication key already exists: {existing}[/yellow]\n"
                    f"Pass --rotate to mint a new one.")
            return
        fp = kr.ensure()
        action = "generated"
    if as_json:
        click.echo(json.dumps({"fingerprint": fp, "action": action}, indent=2))
    else:
        console.print(f"[bold green]✓ Publication key {action}: {fp}[/bold green]")
        console.print(f"  Stored under: {kr.keys_dir / fp}")


@cli.command("publication-keys")
@click.option("--key-dir", type=click.Path(), default=None)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def publication_keys(key_dir: Optional[str], as_json: bool) -> None:
    """List publication signing keys (active + historical)."""
    kr = _publication_keyring(key_dir)
    metas = kr.list_keys()
    if as_json:
        click.echo(json.dumps([{
            "fingerprint": m.fingerprint,
            "created_at": m.created_at,
            "revoked_at": m.revoked_at,
            "is_active": m.is_active,
        } for m in metas], indent=2))
        return
    if not metas:
        console.print("[dim]No publication keys yet. Run `noosphere ledger publication-keygen`.[/dim]")
        return
    t = Table(title="Publication Keys")
    t.add_column("Fingerprint", style="cyan")
    t.add_column("Created")
    t.add_column("Status")
    for m in metas:
        if m.revoked:
            status = f"[red]revoked {m.revoked_at}[/red]"
        elif m.is_active:
            status = "[green]active[/green]"
        else:
            status = "[dim]historical[/dim]"
        t.add_row(m.fingerprint, m.created_at, status)
    console.print(t)


@cli.command("publication-revoke")
@click.argument("fingerprint")
@click.option("--key-dir", type=click.Path(), default=None)
@click.option("--yes", is_flag=True, help="Skip confirmation")
def publication_revoke(fingerprint: str, key_dir: Optional[str], yes: bool) -> None:
    """Revoke a publication key. Historical signatures stay valid; new signatures by this key fail."""
    kr = _publication_keyring(key_dir)
    if not yes:
        click.confirm(f"Revoke key {fingerprint}? Historical material will still verify.", abort=True)
    kr.revoke(fingerprint)
    console.print(f"[yellow]Revoked key {fingerprint}.[/yellow]")
    console.print("If this was the active key, run `publication-keygen` to mint a replacement.")


def _build_canonical_input_from_db(slug: str, version: Optional[int]):
    """Build a canonical input by querying the live DB for the publication."""
    from sqlalchemy import text
    from noosphere.ledger.canonicalize import (
        MqsSnapshot,
        PublicationCanonicalInput,
    )
    from noosphere.models import PublishedConclusion

    store = _get_store()
    with store.session() as session:
        q = session.query(PublishedConclusion).filter(
            PublishedConclusion.slug == slug,
        )
        if version is not None:
            q = q.filter(PublishedConclusion.version == version)
        else:
            q = q.order_by(PublishedConclusion.version.desc())
        row = q.first()
        if row is None:
            raise click.ClickException(
                f"No published conclusion for slug={slug!r}"
                + (f" version={version}" if version is not None else "")
            )

        try:
            payload = json.loads(row.payload_json or "{}")
        except json.JSONDecodeError as exc:
            raise click.ClickException(f"Could not parse payload_json: {exc}")

        methodology = payload.get("methodology") or {}
        profiles = methodology.get("profiles") or []
        profile_ids = [p.get("id") for p in profiles if isinstance(p, dict) and p.get("id")]

        mqs: Optional[MqsSnapshot] = None
        try:
            mqs_row = session.execute(
                text(
                    'SELECT progressivity, severity, "aimMethodFit", '
                    'compressibility, "domainSensitivity", composite, "promptVersion" '
                    'FROM "MethodologyQualityScore" '
                    'WHERE "organizationId" = :org AND "conclusionId" = :cid '
                    'LIMIT 1'
                ),
                {"org": row.organization_id, "cid": row.source_conclusion_id},
            ).first()
        except Exception:
            mqs_row = None
        if mqs_row is not None:
            mqs = MqsSnapshot(
                composite=float(mqs_row[5] or 0.0),
                progressivity=float(mqs_row[0] or 0.0),
                severity=float(mqs_row[1] or 0.0),
                aim_method_fit=float(mqs_row[2] or 0.0),
                compressibility=float(mqs_row[3] or 0.0),
                domain_sensitivity=float(mqs_row[4] or 0.0),
                prompt_version=str(mqs_row[6] or ""),
            )

        return row, PublicationCanonicalInput(
            slug=row.slug,
            version=int(row.version),
            conclusion_text=str(payload.get("conclusionText", "")),
            methodology_profile_ids=profile_ids,
            citations=list(payload.get("citations") or []),
            discounted_confidence=float(row.discounted_confidence or 0.0),
            stated_confidence=float(row.stated_confidence or 0.0),
            mqs=mqs,
            published_at=row.published_at.isoformat() if row.published_at else "",
        )


def _persist_signature(row: Any, sig: Any) -> None:
    """Insert or update the signature row in the codex DB.

    Uses raw SQL so we don't require a PublicationSignature SQLModel
    on the noosphere side; the schema is defined in Prisma.
    """
    from sqlalchemy import text

    store = _get_store()
    payload = json.dumps(sig.to_dict(), separators=(",", ":"), ensure_ascii=False)
    with store.session() as session:
        try:
            existing = session.execute(
                text(
                    'SELECT id FROM "PublicationSignature" '
                    'WHERE "publishedConclusionId" = :pid LIMIT 1'
                ),
                {"pid": row.id},
            ).first()
        except Exception as exc:
            raise click.ClickException(
                "PublicationSignature table not available — run `prisma migrate deploy`. "
                f"Underlying error: {exc}"
            )
        if existing:
            session.execute(
                text(
                    'UPDATE "PublicationSignature" '
                    'SET "canonicalHash" = :h, "signatureHex" = :s, '
                    '"keyFingerprint" = :fp, "signedAt" = :sa, "payloadJson" = :pj '
                    'WHERE "publishedConclusionId" = :pid'
                ),
                {
                    "h": sig.canonical_hash,
                    "s": sig.signature_hex,
                    "fp": sig.key_fingerprint,
                    "sa": sig.signed_at,
                    "pj": payload,
                    "pid": row.id,
                },
            )
        else:
            from uuid import uuid4

            session.execute(
                text(
                    'INSERT INTO "PublicationSignature" '
                    '("id", "publishedConclusionId", "slug", "version", '
                    '"canonicalHash", "signatureHex", "keyFingerprint", '
                    '"signedAt", "payloadJson") '
                    'VALUES (:id, :pid, :slug, :ver, :h, :s, :fp, :sa, :pj)'
                ),
                {
                    "id": uuid4().hex,
                    "pid": row.id,
                    "slug": sig.slug,
                    "ver": sig.version,
                    "h": sig.canonical_hash,
                    "s": sig.signature_hex,
                    "fp": sig.key_fingerprint,
                    "sa": sig.signed_at,
                    "pj": payload,
                },
            )
        session.commit()


def _load_signature_from_db(slug: str, version: Optional[int]) -> Optional[dict]:
    from sqlalchemy import text

    store = _get_store()
    with store.session() as session:
        try:
            params: dict[str, Any] = {"slug": slug}
            sql = (
                'SELECT "payloadJson" FROM "PublicationSignature" '
                'WHERE "slug" = :slug'
            )
            if version is not None:
                sql += ' AND "version" = :ver'
                params["ver"] = version
            sql += ' ORDER BY "version" DESC LIMIT 1'
            row = session.execute(text(sql), params).first()
        except Exception:
            return None
    if row is None:
        return None
    try:
        return json.loads(row[0])
    except (TypeError, json.JSONDecodeError):
        return None


@cli.command("sign-publication")
@click.argument("slug")
@click.option("--version", type=int, default=None,
              help="Specific version to sign (default: latest).")
@click.option("--key-dir", type=click.Path(), default=None)
@click.option("--out", "out_path", type=click.Path(), default=None,
              help="Also write signature.json to this file.")
@click.option("--json", "as_json", is_flag=True)
def sign_publication(
    slug: str,
    version: Optional[int],
    key_dir: Optional[str],
    out_path: Optional[str],
    as_json: bool,
) -> None:
    """Sign a published conclusion and persist the signature."""
    from noosphere.ledger.publication_signing import sign_publication as do_sign

    kr = _publication_keyring(key_dir)
    kr.ensure()
    row, canonical = _build_canonical_input_from_db(slug, version)
    sig = do_sign(canonical, kr)
    _persist_signature(row, sig)
    payload = sig.to_dict()
    if out_path:
        Path(out_path).write_text(json.dumps(payload, indent=2))
    if as_json:
        click.echo(json.dumps(payload, indent=2))
        return
    console.print(f"[bold green]✓ Signed {slug} v{sig.version}[/bold green]")
    console.print(f"  Canonical hash : {sig.canonical_hash}")
    console.print(f"  Key fingerprint: {sig.key_fingerprint}")
    console.print(f"  Signed at      : {sig.signed_at}")


@cli.command("verify-publication")
@click.argument("slug")
@click.option("--version", type=int, default=None,
              help="Specific version to verify (default: latest).")
@click.option("--from-url", "from_url", type=str, default=None,
              help="Fetch signature.json from this URL (e.g. public site).")
@click.option("--from-file", "from_file", type=click.Path(exists=True), default=None,
              help="Read signature.json from a local file instead of the DB.")
@click.option("--key-dir", type=click.Path(), default=None)
@click.option("--json", "as_json", is_flag=True)
def verify_publication(
    slug: str,
    version: Optional[int],
    from_url: Optional[str],
    from_file: Optional[str],
    key_dir: Optional[str],
    as_json: bool,
) -> None:
    """Verify a published conclusion: pull signature, recompute canonical hash, check signature."""
    from noosphere.ledger.publication_signing import (
        PublicationSignature,
        verify_signature,
    )

    kr = _publication_keyring(key_dir)

    # 1. Locate the signature
    sig_dict: Optional[dict] = None
    if from_file:
        sig_dict = json.loads(Path(from_file).read_text())
    elif from_url:
        import urllib.request

        with urllib.request.urlopen(from_url, timeout=15) as resp:  # noqa: S310 — operator-driven
            sig_dict = json.loads(resp.read().decode("utf-8"))
    else:
        sig_dict = _load_signature_from_db(slug, version)

    if sig_dict is None:
        raise click.ClickException(
            f"No signature found for {slug}. Run `noosphere ledger sign-publication {slug}` "
            "or pass --from-url/--from-file."
        )

    sig = PublicationSignature.from_dict(sig_dict)

    # 2. Rebuild the canonical input from the LIVE DB
    target_version = version if version is not None else sig.version
    _row, live_input = _build_canonical_input_from_db(slug, target_version)

    # 3. Verify
    result = verify_signature(sig, kr, live_input=live_input)

    if as_json:
        click.echo(json.dumps({
            "ok": result.ok,
            "reason": result.reason,
            "slug": sig.slug,
            "version": sig.version,
            "key_fingerprint": result.key_fingerprint,
            "key_revoked": result.key_revoked,
            "expected_hash": result.expected_hash,
            "actual_hash": result.actual_hash,
            "issues": result.issues,
        }, indent=2))
        return

    if result.ok:
        console.print(f"[bold green]✓ Signature OK for {slug} v{sig.version}[/bold green]")
        console.print(f"  Canonical hash : {result.expected_hash}")
        console.print(f"  Key fingerprint: {result.key_fingerprint}")
    else:
        console.print(f"[bold red]✗ Signature FAILED for {slug} v{sig.version}[/bold red]")
        console.print(f"  Reason         : {result.reason}")
        console.print(f"  Expected hash  : {result.expected_hash}")
        console.print(f"  Actual hash    : {result.actual_hash}")
        for issue in result.issues:
            console.print(f"  • {issue}")
        raise SystemExit(1)
