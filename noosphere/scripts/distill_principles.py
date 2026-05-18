"""Run principle distillation against the (post-promotion) Conclusion
corpus and sync the resulting drafts into the Prisma ``Principle``
table — the same table the public /principles page reads from.

The shipped CLI command `noosphere principles distill` only prints
drafts to stdout or writes them to a JSON file; it does not persist
to the database. This script bridges that gap by calling
``sync_drafts_to_codex`` after running the pipeline.

USAGE
=====

    cd ~/Desktop/Theseus
    source .venv-currents/bin/activate
    set -a
    source .vercel/.env.production.local
    source theseus-codex/.env
    set +a

    # Dry-run: print how many drafts would land + sample 5:
    python noosphere/scripts/distill_principles.py --dry-run

    # Commit: sync drafts to the Principle table as `accepted` status:
    python noosphere/scripts/distill_principles.py --commit

    # With custom clustering parameters:
    python noosphere/scripts/distill_principles.py --commit \\
           --threshold 0.18 --min-cluster-size 4 --min-domain-breadth 2

WHAT THIS WRITES
================

Each cluster of ≥ min-cluster-size related Conclusions produces one
Principle row with:

  - status = "accepted"  (auto-accepted per founder direction)
  - publicVisible = true  (immediately surfaced on /principles)
  - reviewedAt/publishedAt = insert time
  - clusterConclusionIds + citedConclusionIds populated
  - convictionScore, domainBreadth, clusterCentroidSimilarity computed

After this completes, principles appear on /principles on the next
page reload. The founder can remediate any bad extraction by manually
flipping status='rejected' (which hides the row again).

COST
====

The pipeline calls the LLM once per cluster to synthesize the
principle text. With ~493 promoted Conclusions and a 0.18 cosine
threshold, expect 30-150 clusters → 30-150 LLM calls. ~$3-15 in
Anthropic API spend.

The pipeline also uses sentence-transformers embeddings locally
(no API cost), but the first run may take a few minutes to load
the model and embed all conclusions.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "noosphere"))

from noosphere.store import Store  # noqa: E402
from noosphere.forecasts.scheduler import database_url_from_env  # noqa: E402
from noosphere.distillation.principle_distillation import (  # noqa: E402
    PrincipleDistillationPipeline,
    sync_drafts_to_codex,
)
from noosphere.embeddings import (  # noqa: E402
    sentence_transformers_client_from_settings,
)
from noosphere.ontology import OntologyGraph  # noqa: E402
from sqlalchemy import text  # noqa: E402


def _detect_organization_id(engine) -> str | None:
    """If the Conclusion corpus belongs to exactly one organization,
    return its id. Otherwise return None and let the caller decide."""
    with engine.connect() as conn:
        rows = conn.execute(text(
            'SELECT "organizationId", count(*) FROM "Conclusion" '
            'GROUP BY "organizationId" ORDER BY count(*) DESC'
        )).fetchall()
    if len(rows) == 1:
        return rows[0][0]
    if not rows:
        return None
    print("Multiple organizations found in Conclusion table:")
    for org_id, n in rows:
        print(f"  {org_id}: {n} conclusions")
    return None


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true",
                   help="Run pipeline; print counts + sample; do NOT sync to DB.")
    g.add_argument("--commit", action="store_true",
                   help="Run pipeline AND sync drafts to the Principle table.")

    p.add_argument("--threshold", type=float, default=0.18,
                   help="Cosine-distance cluster cutoff (smaller = stricter).")
    p.add_argument("--min-cluster-size", type=int, default=4,
                   help="Minimum Conclusions per cluster to form a Principle.")
    p.add_argument("--min-domain-breadth", type=int, default=2,
                   help="Minimum distinct domains per cluster.")
    p.add_argument("--organization-id", type=str, default=None,
                   help="Override the auto-detected organization id.")
    p.add_argument("--no-replace-stale", action="store_true",
                   help="Keep recently-accepted Principles instead of "
                        "wiping ones produced by this sync in the last 24h. "
                        "Default is to wipe.")

    args = p.parse_args(argv)

    store = Store.from_database_url(database_url_from_env())
    engine = store.engine

    org_id: str | None = args.organization_id or _detect_organization_id(engine)
    if org_id is None:
        print("ERROR: could not determine organization_id. Pass --organization-id.")
        return 2

    print(f"Organization id           : {org_id}")
    print(f"Clustering threshold      : {args.threshold}")
    print(f"Min cluster size          : {args.min_cluster_size}")
    print(f"Min domain breadth        : {args.min_domain_breadth}")
    print(f"Replace recently accepted : {not args.no_replace_stale}")
    print()

    # ── Load conclusions ────────────────────────────────────────────────
    print("Loading Conclusions from DB...")
    conclusions = store.list_conclusions()
    print(f"  loaded {len(conclusions)} conclusions")

    # ── Build pipeline ──────────────────────────────────────────────────
    print("Building distillation pipeline "
          "(loads sentence-transformers model on first call)...")
    embedder = sentence_transformers_client_from_settings()
    pipeline = PrincipleDistillationPipeline(
        graph=OntologyGraph(),
        embedder=embedder,
        clustering_threshold=args.threshold,
        min_cluster_size=args.min_cluster_size,
        min_domain_breadth=args.min_domain_breadth,
    )

    # ── Run distillation ────────────────────────────────────────────────
    print("\nRunning distillation pipeline...")
    drafts = pipeline.run(conclusions)
    print(f"\nGenerated {len(drafts)} draft Principle(s).")

    if not drafts:
        print("Nothing to sync — no clusters met the threshold/size/breadth filters.")
        print("Try lowering --threshold, --min-cluster-size, or --min-domain-breadth.")
        return 0

    # ── Show a sample so we can sanity-check ────────────────────────────
    print(f"\nFirst {min(5, len(drafts))} drafts:")
    for d in drafts[:5]:
        text_preview = (getattr(d, "text", "") or "")[:140]
        domains = list(getattr(d, "domains", []))
        cluster_size = len(getattr(d, "cluster_conclusion_ids", []))
        print(f"\n  - text          : {text_preview}")
        print(f"    domains       : {', '.join(domains[:3])}")
        print(f"    cluster size  : {cluster_size}")
        print(f"    status        : {getattr(d, 'status', '?')}")
        if hasattr(d, "conviction_score"):
            print(f"    conviction    : {d.conviction_score:.3f}")

    if args.dry_run:
        print("\n--dry-run: no DB writes performed.")
        print("If the drafts look reasonable, re-run with --commit.")
        return 0

    # ── Sync to Principle table via raw psycopg2 connection ─────────────
    print(f"\nSyncing {len(drafts)} drafts to Prisma Principle table...")
    raw_conn = engine.raw_connection()
    try:
        counts = sync_drafts_to_codex(
            raw_conn,
            organization_id=org_id,
            drafts=drafts,
            replace_recently_accepted=not args.no_replace_stale,
        )
        raw_conn.commit()
    finally:
        raw_conn.close()

    print(f"\nSync counts: {counts}")
    print()
    print("Drafts auto-accepted: they appear on /principles immediately.")
    print("Remediate any bad extraction by setting status='rejected'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
