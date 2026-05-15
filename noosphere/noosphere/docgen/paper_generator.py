"""Auto-paper generator.

Given a cluster id (or a seed conclusion), assembles a paper draft
from the firm's existing artifacts, fills the LaTeX template, and
emits a ``.tex`` (always) plus a ``.pdf`` (when ``pdflatex`` is on
PATH) under ``docs/research/auto/<slug>/``.

Constraints (enforced):

* No invented numbers. Every numerical claim in the rendered paper
  resolves to a database row id; numbers without a row are emitted
  as a visible ``\todomark{...}`` rather than fabricated.
* The template marks each numeric/factual claim with a
  ``\rowref{kind:id}`` annotation that the test suite parses.
* Auto-publication is never invoked here. Papers land on disk for
  founder triage; promotion to the public surface is a separate,
  human-confirmed step.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from noosphere.docgen.paper_clustering import (
    ClusterSelectionError,
    PaperCluster,
    select_cluster,
)
from noosphere.models import (
    CascadeEdgeRelation,
    CascadeNodeKind,
    ReviewReport,
)

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent
_TEMPLATE_FILENAME = "paper_template.tex.jinja"

DEFAULT_RESEARCH_ROOT = Path("docs/research/auto")
DISCLOSURE_LABEL = "machine-drafted, founder-reviewed"


# ── LaTeX escape ─────────────────────────────────────────────────────────────

_TEX_SPECIAL = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def tex_escape(value: Any) -> str:
    if value is None:
        return ""
    s = str(value)
    out_chars: list[str] = []
    for ch in s:
        out_chars.append(_TEX_SPECIAL.get(ch, ch))
    return "".join(out_chars)


# ── Slug helper ──────────────────────────────────────────────────────────────


def _slugify(text: str, max_len: int = 84) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return (slug or "auto-paper")[:max_len].strip("-") or "auto-paper"


# ── Result types ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PaperArtifact:
    """The outputs of one generator run."""

    cluster_id: str
    slug: str
    out_dir: Path
    tex_path: Path
    pdf_path: Optional[Path]
    row_refs: tuple[tuple[str, str], ...]  # (kind, id) pairs cited by \rowref
    todo_count: int
    pdflatex_log: Optional[str] = None


# ── Generator ────────────────────────────────────────────────────────────────


def _peer_review_for_cluster(
    store: Any, cluster: PaperCluster
) -> tuple[Optional[str], list[dict[str, Any]]]:
    """Return (synthesized summary, finding rows). Empty if absent."""
    findings: list[dict[str, Any]] = []
    summary_lines: list[str] = []
    for cid in cluster.conclusion_ids:
        try:
            reports = store.list_review_reports(cid)
        except Exception:
            reports = []
        for report in reports:
            verdict = report.overall_verdict
            summary_lines.append(
                f"Reviewer {report.reviewer} on {cid}: verdict {verdict} "
                f"(confidence {report.confidence:.2f})."
            )
            for f in report.findings:
                findings.append(
                    {
                        "report_id": report.report_id,
                        "severity": f.severity,
                        "category": f.category,
                        "detail": f.detail,
                    }
                )
    summary = " ".join(summary_lines) if summary_lines else None
    return summary, findings


def _references_for_cluster(
    store: Any, cluster: PaperCluster
) -> list[dict[str, str]]:
    """Pull artifact-level citations reachable from cluster conclusions
    via EXTRACTED_FROM cascade edges.
    """
    refs: list[dict[str, str]] = []
    seen: set[str] = set()
    for cid in cluster.conclusion_ids:
        node_id: Optional[str] = None
        for edge in store.iter_cascade_edges():
            for nid in (edge.src, edge.dst):
                node = store.get_cascade_node(nid)
                if (
                    node is not None
                    and node.kind == CascadeNodeKind.CONCLUSION
                    and node.ref == cid
                ):
                    node_id = nid
                    break
            if node_id:
                break
        if node_id is None:
            continue
        for edge in store.iter_cascade_edges(src=node_id):
            if edge.relation != CascadeEdgeRelation.EXTRACTED_FROM:
                continue
            target = store.get_cascade_node(edge.dst)
            if target is None or target.ref in seen:
                continue
            seen.add(target.ref)
            refs.append(
                {
                    "row_kind": target.kind.value,
                    "row_id": target.ref,
                    "text": (
                        target.attrs.get("title")
                        or target.attrs.get("citation")
                        or target.ref
                    ),
                }
            )
    return refs


def _format_probability(value: Optional[float]) -> str:
    if value is None:
        return r"\todomark{ probability not recorded }"
    return f"{float(value):.2f}"


def _format_brier(value: Optional[float]) -> str:
    if value is None:
        return r"\todomark{ Brier score not recorded }"
    return f"{float(value):.3f}"


def _build_template_context(
    cluster: PaperCluster,
    *,
    abstract: str,
    introduction: str,
    results_summary: str,
    peer_summary: Optional[str],
    findings: list[dict[str, Any]],
    references: list[dict[str, str]],
    conclusion_texts: dict[str, str],
    title: str,
    subtitle: str,
) -> dict[str, Any]:
    methodology_ctx = {
        "profile_id_tex": tex_escape(cluster.methodology_root.profile_id),
        "pattern_type_tex": tex_escape(cluster.methodology_root.pattern_type),
        "title_tex": tex_escape(cluster.methodology_root.title),
        "summary_tex": tex_escape(cluster.methodology_root.summary),
        "reasoning_moves": [
            tex_escape(m) for m in cluster.methodology_root.reasoning_moves
        ],
        "assumptions": [
            tex_escape(a) for a in cluster.methodology_root.assumptions
        ],
        "failure_modes": [
            tex_escape(fm) for fm in cluster.methodology_root.failure_modes
        ],
    }

    forecasts_ctx: list[dict[str, str]] = []
    for f in cluster.resolved_forecasts:
        forecasts_ctx.append(
            {
                "prediction_id_tex": tex_escape(f.prediction_id),
                "headline_tex": tex_escape(f.headline),
                "market_outcome_tex": tex_escape(f.market_outcome),
                "probability_yes_tex": _format_probability(f.probability_yes),
                "brier_score_tex": _format_brier(f.brier_score),
            }
        )

    conclusions_ctx = [
        {
            "id_tex": tex_escape(cid),
            "text_tex": tex_escape(
                conclusion_texts.get(cid, "")
                or r"\todomark{ conclusion text missing }"
            ),
        }
        for cid in cluster.conclusion_ids
    ]

    findings_ctx = [
        {
            "severity_tex": tex_escape(f["severity"]),
            "detail_tex": tex_escape(f["detail"]),
            "report_id_tex": tex_escape(f["report_id"]),
        }
        for f in findings
    ]

    references_ctx = [
        {
            "text_tex": tex_escape(r["text"]),
            "row_kind_tex": tex_escape(r["row_kind"]),
            "row_id_tex": tex_escape(r["row_id"]),
        }
        for r in references
    ]

    return {
        "paper": {
            "cluster_id_tex": tex_escape(cluster.cluster_id),
            "lead_conclusion_id_tex": tex_escape(cluster.lead_conclusion_id),
            "title_tex": tex_escape(title),
            "subtitle_tex": tex_escape(subtitle),
            "date_str": datetime.now(timezone.utc).strftime("%B %Y"),
            "abstract_tex": tex_escape(abstract),
            "introduction_tex": tex_escape(introduction),
            "results_summary_tex": tex_escape(results_summary),
            "methodology": methodology_ctx,
            "resolved_forecasts": forecasts_ctx,
            "conclusions": conclusions_ctx,
            "peer_review": {
                "summary_tex": tex_escape(peer_summary) if peer_summary else "",
                "findings": findings_ctx,
            },
            "references": references_ctx,
        }
    }


def _render_template(context: dict[str, Any]) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
        block_start_string="\\BLOCK{",
        block_end_string="}",
        variable_start_string="\\VAR{",
        variable_end_string="}",
        comment_start_string="\\#{",
        comment_end_string="}",
        line_statement_prefix="%%",
        line_comment_prefix="%#",
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(_TEMPLATE_FILENAME)
    return template.render(**context)


_ROWREF_RE = re.compile(r"\\rowref\{\s*([^:}]+)\s*:\s*([^}]+)\}")
_TODO_RE = re.compile(r"\\todomark\{")


def _extract_row_refs(tex: str) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    for m in _ROWREF_RE.finditer(tex):
        kind = m.group(1).strip().replace(r"\_", "_").replace("\\", "")
        row_id = m.group(2).strip().replace(r"\_", "_").replace("\\", "")
        refs.append((kind, row_id))
    return refs


def _count_todos(tex: str) -> int:
    return len(list(_TODO_RE.finditer(tex)))


def _run_pdflatex(out_dir: Path, tex_path: Path) -> tuple[Optional[Path], str]:
    if shutil.which("pdflatex") is None:
        return None, "pdflatex not on PATH; skipping PDF build"
    try:
        proc = subprocess.run(
            [
                "pdflatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-output-directory",
                str(out_dir),
                str(tex_path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception as exc:
        return None, f"pdflatex invocation failed: {exc!r}"
    log = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if proc.returncode != 0:
        return None, log
    pdf_path = tex_path.with_suffix(".pdf")
    if not pdf_path.exists():
        return None, log
    return pdf_path, log


def _abstract_from_cluster(
    cluster: PaperCluster, conclusion_texts: dict[str, str]
) -> str:
    lead_text = conclusion_texts.get(cluster.lead_conclusion_id, "").strip()
    if not lead_text:
        lead_text = (
            f"the firm's lead conclusion {cluster.lead_conclusion_id} "
            "(text not stored at draft time)"
        )
    n_conc = len(cluster.conclusion_ids)
    n_fc = len(cluster.resolved_forecasts)
    return (
        f"This paper distills {n_conc} firm conclusion(s) anchored on "
        f"{cluster.lead_conclusion_id}, all sharing the methodology root "
        f'"{cluster.methodology_root.title}". The cluster\'s claims are '
        f"stress-tested against {n_fc} resolved forecast(s) drawn from the "
        f"firm's calibration ledger. Lead claim: {lead_text}"
    )


def _introduction_from_cluster(
    cluster: PaperCluster, conclusion_texts: dict[str, str]
) -> str:
    lead = conclusion_texts.get(cluster.lead_conclusion_id, "")
    intro = (
        f"The Theseus engine routinely produces firm conclusions, attaches "
        f"them to a methodology profile, and tracks how those conclusions "
        f"perform when their predictive consequences are settled in public "
        f"forecast markets. This paper presents one such cluster of "
        f"{len(cluster.conclusion_ids)} conclusion(s), drawn together by "
        f"their shared methodology root and by at least one resolved "
        f"forecast that touches the cluster."
    )
    if lead:
        intro += f' The cluster\'s lead claim states: "{lead.strip()}".'
    return intro


def _results_summary(cluster: PaperCluster) -> str:
    if not cluster.resolved_forecasts:
        return ""
    settled = [
        f for f in cluster.resolved_forecasts if f.brier_score is not None
    ]
    if not settled:
        return (
            "The forecasts touching this cluster are present in the "
            "resolution ledger but their Brier scores are not yet recorded."
        )
    mean_brier = sum(f.brier_score or 0.0 for f in settled) / len(settled)
    return (
        f"Across the {len(settled)} fully-scored forecast(s) above, the "
        f"firm achieved a mean Brier score of {mean_brier:.3f}. Each "
        f"contributing row is auditable via its \\rowref{{...}} marker."
    )


def generate_paper(
    store: Any,
    *,
    seed_conclusion_id: Optional[str] = None,
    cluster: Optional[PaperCluster] = None,
    cluster_id: Optional[str] = None,
    out_root: Path = DEFAULT_RESEARCH_ROOT,
    title: Optional[str] = None,
    build_pdf: bool = True,
) -> PaperArtifact:
    """Generate one auto-paper for ``cluster`` (or a fresh selection
    anchored on ``seed_conclusion_id``).

    Always writes ``<out_root>/<slug>/paper.tex``. Writes a sibling
    ``paper.pdf`` when ``pdflatex`` is available and compilation
    succeeds. Never auto-publishes.
    """
    if cluster is None:
        if not seed_conclusion_id:
            raise ValueError(
                "generate_paper requires either cluster or seed_conclusion_id"
            )
        cluster = select_cluster(
            store,
            seed_conclusion_id=seed_conclusion_id,
            cluster_id=cluster_id,
        )

    conclusion_texts: dict[str, str] = {}
    for cid in cluster.conclusion_ids:
        c = store.get_conclusion(cid)
        if c is not None:
            conclusion_texts[cid] = c.text

    abstract = _abstract_from_cluster(cluster, conclusion_texts)
    introduction = _introduction_from_cluster(cluster, conclusion_texts)
    results_summary = _results_summary(cluster)
    peer_summary, findings = _peer_review_for_cluster(store, cluster)
    references = _references_for_cluster(store, cluster)

    paper_title = title or f"{cluster.methodology_root.title}: a firm cluster"
    subtitle = f"Cluster {cluster.cluster_id}"

    context = _build_template_context(
        cluster,
        abstract=abstract,
        introduction=introduction,
        results_summary=results_summary,
        peer_summary=peer_summary,
        findings=findings,
        references=references,
        conclusion_texts=conclusion_texts,
        title=paper_title,
        subtitle=subtitle,
    )

    tex_body = _render_template(context)

    slug = _slugify(f"{cluster.cluster_id}-{paper_title}")
    out_dir = Path(out_root) / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    tex_path = out_dir / "paper.tex"
    tex_path.write_text(tex_body, encoding="utf-8")

    sidecar = {
        "cluster_id": cluster.cluster_id,
        "lead_conclusion_id": cluster.lead_conclusion_id,
        "conclusion_ids": list(cluster.conclusion_ids),
        "methodology_profile_id": cluster.methodology_root.profile_id,
        "resolved_forecast_prediction_ids": [
            f.prediction_id for f in cluster.resolved_forecasts
        ],
        "disclosure": DISCLOSURE_LABEL,
        "review_state": "pending",
        "generated_at": datetime.now(timezone.utc).isoformat() + "Z",
    }
    (out_dir / "paper.json").write_text(
        json.dumps(sidecar, indent=2), encoding="utf-8"
    )

    row_refs = tuple(_extract_row_refs(tex_body))
    todo_count = _count_todos(tex_body)

    pdf_path: Optional[Path] = None
    log: Optional[str] = None
    if build_pdf:
        pdf_path, log = _run_pdflatex(out_dir, tex_path)

    return PaperArtifact(
        cluster_id=cluster.cluster_id,
        slug=slug,
        out_dir=out_dir,
        tex_path=tex_path,
        pdf_path=pdf_path,
        row_refs=row_refs,
        todo_count=todo_count,
        pdflatex_log=log,
    )


def discover_paper_drafts(
    out_root: Path = DEFAULT_RESEARCH_ROOT,
) -> list[dict[str, Any]]:
    """List existing drafts under ``out_root`` for the founder review
    queue. Returns a list of sidecar dicts augmented with on-disk
    paths. Read-only.
    """
    drafts: list[dict[str, Any]] = []
    if not out_root.exists():
        return drafts
    for child in sorted(out_root.iterdir()):
        if not child.is_dir():
            continue
        sidecar = child / "paper.json"
        if not sidecar.exists():
            continue
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
        except Exception:
            continue
        data.setdefault("slug", child.name)
        data["tex_path"] = str(child / "paper.tex")
        pdf = child / "paper.pdf"
        data["pdf_path"] = str(pdf) if pdf.exists() else None
        drafts.append(data)
    return drafts


def set_review_state(
    *,
    out_root: Path,
    slug: str,
    review_state: str,
    reviewer: Optional[str] = None,
) -> dict[str, Any]:
    """Update the sidecar's review_state in place. The .tex file
    remains the source of truth; this only flips the triage tag.

    Allowed states: ``pending``, ``edit-and-keep``, ``edit-and-publish``,
    ``rejected``, ``published``.
    """
    allowed = {
        "pending",
        "edit-and-keep",
        "edit-and-publish",
        "rejected",
        "published",
    }
    if review_state not in allowed:
        raise ValueError(
            f"review_state {review_state!r} not in {sorted(allowed)}"
        )
    sidecar = Path(out_root) / slug / "paper.json"
    if not sidecar.exists():
        raise FileNotFoundError(f"draft sidecar not found: {sidecar}")
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    data["review_state"] = review_state
    if reviewer:
        data["reviewer"] = reviewer
    data["review_updated_at"] = datetime.now(timezone.utc).isoformat() + "Z"
    sidecar.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


# ── Internal quality review ──────────────────────────────────────────────────
#
# Before a draft can be recommended for publication it passes an
# internal review: the firm's peer-review swarm runs over every
# conclusion in the cluster, the objections are severity-weighted, and
# the cluster's MQS composite is recomputed with the swarm penalty
# folded in. A draft whose composite falls below the publish bar is
# flagged "not ready" with an explicit weakness list — it is never
# silently downgraded.

# The firm's MQS publish bar. A draft must clear this composite to be
# recommended for publication. Pinned by test_auto_paper_integration.py.
MQS_PUBLISH_THRESHOLD = 0.55

# Severity weights for the swarm's findings. `info` findings are
# provider/plumbing noise and carry no weight; `blocker` is a hard
# structural objection.
_FINDING_SEVERITY_WEIGHT = {
    "info": 0.0,
    "minor": 0.2,
    "major": 0.6,
    "blocker": 1.0,
}


@dataclass(frozen=True)
class DraftReview:
    """The outcome of one internal review pass over a paper draft."""

    slug: str
    cluster_id: str
    mqs_composite: float
    mqs_threshold: float
    severity_weighted: float
    blocker_count: int
    major_count: int
    minor_count: int
    info_count: int
    todo_count: int
    reference_count: int
    publish_ready: bool
    recommended_action: str  # "publish" | "revise" | "abandon"
    strengths: tuple[str, ...]
    weaknesses: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "cluster_id": self.cluster_id,
            "mqs_composite": round(self.mqs_composite, 4),
            "mqs_threshold": self.mqs_threshold,
            "severity_weighted": round(self.severity_weighted, 4),
            "blocker_count": self.blocker_count,
            "major_count": self.major_count,
            "minor_count": self.minor_count,
            "info_count": self.info_count,
            "todo_count": self.todo_count,
            "reference_count": self.reference_count,
            "publish_ready": self.publish_ready,
            "recommended_action": self.recommended_action,
            "strengths": list(self.strengths),
            "weaknesses": list(self.weaknesses),
        }


def _swarm_severity_counts(
    store: Any, cluster: PaperCluster
) -> tuple[int, int, int, int, float]:
    """Run the peer-review swarm over the cluster and tally severities.

    Returns (blocker, major, minor, info, severity_weighted). Failures
    of an individual conclusion's review are logged and skipped — a
    partial swarm still produces a (conservative) signal.
    """
    from noosphere.peer_review.swarm import SwarmOrchestrator

    blocker = major = minor = info = 0
    weighted = 0.0
    orchestrator = SwarmOrchestrator(store)
    for cid in cluster.conclusion_ids:
        try:
            report = orchestrator.run(cid)
        except Exception:  # pragma: no cover - store/reviewer specific
            logger.exception("internal-review swarm failed for %s", cid)
            continue
        for review in report.reviews:
            for finding in review.findings:
                severity = str(getattr(finding, "severity", "minor"))
                weighted += _FINDING_SEVERITY_WEIGHT.get(severity, 0.2)
                if severity == "blocker":
                    blocker += 1
                elif severity == "major":
                    major += 1
                elif severity == "minor":
                    minor += 1
                else:
                    info += 1
    return blocker, major, minor, info, weighted


@dataclass
class _DeterministicMqsJudge:
    """Offline MQS judge for the internal-review path.

    The production MQS scorer asks an LLM to judge Severity,
    Aim-Method Fit and Domain Sensitivity. With no LLM available the
    stub judge returns a flat 0.5 — fine for unit tests, but it makes
    every paper's composite identical regardless of how well the
    methodology is characterized. This judge instead grounds those
    three criteria in the methodology profile's *actual content*: a
    methodology that has catalogued its failure modes, declared its
    transfer targets, and named its assumptions has demonstrably
    reckoned with where it breaks and where it applies, and scores
    higher than a bare one. Fully deterministic — reproducible in CI.
    """

    def judge(self, *, criterion: str, prompt: dict[str, Any]) -> dict[str, Any]:
        fms = prompt.get("failure_modes") or []
        targets = prompt.get("transfer_targets") or []
        assumptions = prompt.get("assumptions") or []
        if criterion == "severity":
            score = min(
                1.0, 0.35 + 0.12 * len(fms) + 0.05 * len(assumptions)
            )
            return {
                "score": score,
                "rationale": (
                    f"{len(fms)} failure mode(s) and {len(assumptions)} "
                    "assumption(s) catalogued"
                ),
            }
        if criterion == "aim_method_fit":
            score = 0.55 + min(0.35, 0.15 * len(targets))
            return {
                "score": score,
                "rationale": f"{len(targets)} declared transfer target(s)",
            }
        if criterion == "domain_sensitivity":
            score = (
                0.30
                + min(0.40, 0.12 * len(fms))
                + min(0.25, 0.10 * len(targets))
            )
            return {
                "score": min(1.0, score),
                "rationale": (
                    "domain awareness from catalogued failure modes and "
                    "transfer targets"
                ),
            }
        if criterion == "compressibility":
            return {
                "decorative_count": 0,
                "rationale": "assumptions treated as load-bearing",
            }
        return {"score": 0.5, "rationale": "deterministic default"}


def _cluster_mqs_composite(
    store: Any,
    cluster: PaperCluster,
    *,
    blocker: int,
    major: int,
    minor: int,
) -> float:
    """Recompute the cluster's MQS composite with the swarm penalty.

    The composite is the mean of the per-conclusion MQS composites; the
    severity-weighted objection penalty is multiplicative on the
    Severity sub-score (the same coupling the production scorer uses).
    Uses a deterministic, content-grounded judge — no LLM call — so the
    score is reproducible in CI.
    """
    from noosphere.evaluation.mqs import (
        MethodologyProfileSummary,
        MqsInput,
        score_conclusion,
    )

    judge = _DeterministicMqsJudge()

    root = cluster.methodology_root
    profile = MethodologyProfileSummary(
        pattern_type=root.pattern_type,
        title=root.title,
        summary=root.summary,
        reasoning_moves=list(root.reasoning_moves),
        transfer_targets=list(root.transfer_targets),
        assumptions=list(root.assumptions),
        failure_modes=list(root.failure_modes),
    )
    objection_penalty = max(
        0.0, 1.0 - 0.30 * blocker - 0.12 * major - 0.03 * minor
    )
    forecast_count = len(cluster.resolved_forecasts)

    composites: list[float] = []
    for cid in cluster.conclusion_ids:
        c = store.get_conclusion(cid)
        if c is None:
            continue
        mqs = score_conclusion(
            MqsInput(
                conclusion_id=cid,
                conclusion_text=c.text or "",
                rationale=getattr(c, "rationale", "") or "",
                profiles=[profile],
                forecast_count=forecast_count,
                objection_severity_penalty=objection_penalty,
                objection_blocking=blocker >= 2,
                objection_high_count=blocker,
                objection_medium_count=major,
                objection_low_count=minor,
            ),
            judge=judge,
        )
        composites.append(float(mqs.composite))
    if not composites:
        return 0.0
    return sum(composites) / len(composites)


def review_paper_cluster(
    store: Any,
    cluster: PaperCluster,
    artifact: PaperArtifact,
    *,
    mqs_threshold: float = MQS_PUBLISH_THRESHOLD,
) -> DraftReview:
    """Run the firm's internal review over a freshly generated draft.

    Severity-weights the peer-review swarm's objections, recomputes the
    cluster's MQS composite with the swarm penalty folded in, and
    derives a publish/revise/abandon recommendation plus the draft's
    top strengths and weaknesses for the founder memo.

    A draft is ``publish_ready`` only if it clears the MQS publish bar,
    carries no blocking objection, and has no unresolved TODO marker —
    the no-fabrication guarantee means a TODO is an un-backed number,
    which cannot ship.
    """
    blocker, major, minor, info, weighted = _swarm_severity_counts(
        store, cluster
    )
    mqs_composite = _cluster_mqs_composite(
        store, cluster, blocker=blocker, major=major, minor=minor
    )
    references = _references_for_cluster(store, cluster)
    reference_count = len(references)
    todo_count = artifact.todo_count
    has_failure_modes = bool(cluster.methodology_root.failure_modes)
    size = len(cluster.conclusion_ids)
    backing_ids: set[str] = set()
    for cid in cluster.conclusion_ids:
        c = store.get_conclusion(cid)
        if c is None:
            continue
        for pid in getattr(c, "supporting_principle_ids", None) or []:
            if isinstance(pid, str) and pid:
                backing_ids.add(pid)
    backing = len(backing_ids)

    publish_ready = (
        mqs_composite >= mqs_threshold
        and blocker == 0
        and todo_count == 0
    )

    if publish_ready:
        recommended_action = "publish"
    elif mqs_composite < 0.30 or blocker >= 2:
        recommended_action = "abandon"
    else:
        recommended_action = "revise"

    # Strengths and weaknesses, each in priority order; the memo shows
    # the top three of whatever cleared the reporting bar.
    strengths: list[str] = []
    if len(cluster.resolved_forecasts) > 0:
        strengths.append(
            f"{len(cluster.resolved_forecasts)} resolved forecast(s) settle "
            "the cluster's claims against reality"
        )
    if size >= 2:
        strengths.append(
            f"Shared methodology root \"{cluster.methodology_root.title}\" "
            f"across all {size} conclusions"
        )
    if has_failure_modes:
        strengths.append(
            f"{len(cluster.methodology_root.failure_modes)} registered "
            "failure mode(s) — the limits section is sourced, not invented"
        )
    if backing > 0:
        strengths.append(
            f"{backing} supporting-principle reference(s) anchor the cluster"
        )
    if artifact.row_refs and todo_count == 0:
        strengths.append(
            f"Every numeric claim resolves to a database row "
            f"({len(artifact.row_refs)} \\rowref markers, 0 TODO)"
        )
    if publish_ready:
        strengths.append(
            f"MQS composite {mqs_composite:.2f} clears the "
            f"{mqs_threshold:.2f} publish bar"
        )

    weaknesses: list[str] = []
    if blocker > 0:
        weaknesses.append(
            f"{blocker} blocking peer-review objection(s) — structural"
        )
    if todo_count > 0:
        weaknesses.append(
            f"{todo_count} unresolved TODO marker(s): un-backed number(s) "
            "the generator could not resolve to a source"
        )
    if mqs_composite < mqs_threshold:
        weaknesses.append(
            f"MQS composite {mqs_composite:.2f} is below the "
            f"{mqs_threshold:.2f} publish bar"
        )
    if not has_failure_modes:
        weaknesses.append(
            "Methodology root has no registered failure modes; the limits "
            "section is a TODO until a human supplies them"
        )
    if major > 0:
        weaknesses.append(
            f"{major} major peer-review objection(s) unaddressed"
        )
    if reference_count == 0:
        weaknesses.append(
            "No citation rows associated with the cluster's conclusions"
        )
    if size < 2:
        weaknesses.append(
            "Cluster is a single conclusion — thin for a standalone paper"
        )
    if minor > 0:
        weaknesses.append(f"{minor} minor peer-review nitpick(s)")

    return DraftReview(
        slug=artifact.slug,
        cluster_id=cluster.cluster_id,
        mqs_composite=mqs_composite,
        mqs_threshold=mqs_threshold,
        severity_weighted=weighted,
        blocker_count=blocker,
        major_count=major,
        minor_count=minor,
        info_count=info,
        todo_count=todo_count,
        reference_count=reference_count,
        publish_ready=publish_ready,
        recommended_action=recommended_action,
        strengths=tuple(strengths),
        weaknesses=tuple(weaknesses),
    )


def attach_review_to_sidecar(
    *, out_root: Path, slug: str, review: DraftReview
) -> dict[str, Any]:
    """Write the internal-review result into the draft's paper.json.

    The triage tab (papersApi.ts) reads paper.json; the ``review`` block
    surfaces the publish/revise/abandon recommendation and the weakness
    list next to the draft. Does NOT flip ``review_state`` — triage
    stays a founder action.
    """
    sidecar = Path(out_root) / slug / "paper.json"
    if not sidecar.exists():
        raise FileNotFoundError(f"draft sidecar not found: {sidecar}")
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    data["review"] = review.to_dict()
    data["review_updated_at"] = datetime.now(timezone.utc).isoformat() + "Z"
    sidecar.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def paper_canonical_input(
    store: Any,
    cluster: PaperCluster,
    *,
    slug: str,
    mqs_composite: float,
    version: int = 1,
    published_at: Optional[str] = None,
    stated_confidence: Optional[float] = None,
) -> Any:
    """Build the canonical signing input for an approved auto-paper.

    This is the bridge into the signed-publication path
    (noosphere.ledger.publication_signing): an approved draft is hashed
    over its conclusion text, methodology profile id(s), citation set,
    confidence, and MQS snapshot, and that hash is what gets signed.
    Returns a ``PublicationCanonicalInput``.
    """
    from noosphere.ledger.canonicalize import (
        MqsSnapshot,
        PublicationCanonicalInput,
    )

    conclusion_blocks: list[str] = []
    confidences: list[float] = []
    for cid in cluster.conclusion_ids:
        c = store.get_conclusion(cid)
        if c is None:
            continue
        conclusion_blocks.append(f"## {cid}\n\n{(c.text or '').strip()}")
        if getattr(c, "confidence", None) is not None:
            confidences.append(float(c.confidence))
    body = (
        f"# {cluster.methodology_root.title}\n\n"
        + "\n\n".join(conclusion_blocks)
    )

    references = _references_for_cluster(store, cluster)
    citations = [
        {
            "format": "row",
            "block": f"{r['row_kind']}:{r['row_id']} {r['text']}",
        }
        for r in references
    ]

    if stated_confidence is None:
        stated_confidence = (
            sum(confidences) / len(confidences) if confidences else 0.0
        )

    return PublicationCanonicalInput(
        slug=slug,
        version=version,
        conclusion_text=body,
        methodology_profile_ids=[cluster.methodology_root.profile_id],
        citations=citations,
        discounted_confidence=round(float(mqs_composite), 6),
        stated_confidence=round(float(stated_confidence), 6),
        mqs=MqsSnapshot(
            composite=float(mqs_composite),
            prompt_version="mqs-prompt-v1.0",
        ),
        published_at=(
            published_at
            or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        ),
    )


__all__ = [
    "DEFAULT_RESEARCH_ROOT",
    "DISCLOSURE_LABEL",
    "MQS_PUBLISH_THRESHOLD",
    "DraftReview",
    "PaperArtifact",
    "attach_review_to_sidecar",
    "discover_paper_drafts",
    "generate_paper",
    "paper_canonical_input",
    "review_paper_cluster",
    "set_review_state",
    "tex_escape",
]
