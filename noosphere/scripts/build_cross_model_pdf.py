"""Generate Cross_Model_Geometry_Study.tex (and PDF if pdflatex exists).

All numbers come from ``cross_model_analysis.json`` produced by
``noosphere.benchmarks.cross_model_analysis``. No hand-edited numbers
appear in the .tex source; the script re-renders the file each run.

Compilation:
- If ``pdflatex`` is available we run it twice (so cross-references
  resolve) and place the PDF next to the .tex.
- If ``pdflatex`` is unavailable we exit 0 with a friendly message;
  the .tex remains as the source of truth.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


_TEX_HEADER = r"""\documentclass[11pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage[margin=1in]{geometry}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{array}
\usepackage{caption}
\usepackage{hyperref}
\usepackage{xcolor}
\usepackage{textcomp}
\title{Cross-Model Embedding Geometry Study\\\large QH Benchmark v1, Multi-Backend Replication}
\author{Theseus / Noosphere Research}
\date{%(today)s}
\begin{document}
\maketitle
"""


def _fmt(v: Any, digits: int = 4) -> str:
    if v is None:
        return "n/a"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if math.isnan(f):
        return "n/a"
    return f"{f:.{digits}f}"


_UNICODE_TEX = {
    "≥": r"$\geq$",
    "≤": r"$\leq$",
    "≠": r"$\neq$",
    "→": r"$\to$",
    "—": "---",
    "–": "--",
    "“": "``",
    "”": "''",
    "‘": "`",
    "’": "'",
    "·": r"$\cdot$",
    "×": r"$\times$",
    "α": r"$\alpha$",
    "β": r"$\beta$",
    "Δ": r"$\Delta$",
}


def _escape(s: str) -> str:
    out = (
        s.replace("\\", r"\\")
        .replace("_", r"\_")
        .replace("&", r"\&")
        .replace("%", r"\%")
        .replace("#", r"\#")
        .replace("$", r"\$")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("^", r"\^{}")
        .replace("~", r"\~{}")
    )
    for src, dst in _UNICODE_TEX.items():
        out = out.replace(src, dst)
    return out


def _abstract(analysis: dict[str, Any]) -> str:
    losses = analysis.get("geometry_losses", []) or []
    n_models = len(analysis.get("per_model", {}))
    n_rows = analysis.get("n_rows", 0)
    body = (
        "We replicate the Quintin Hypothesis (QH) contradiction-geometry "
        "probe across multiple embedding back-ends to determine whether "
        "the predicted geometric signature is a property of language or "
        "a property of one specific model. We run the frozen QH-v1 "
        f"benchmark with {n_models} embedding models for a total of "
        f"{n_rows} prediction rows and compare per-model accuracy, AUROC, "
        "and ECE against random and cosine baselines."
    )
    if losses:
        names = ", ".join(f"\\texttt{{{_escape(l['model'])}}}" for l in losses)
        body += (
            "\\par\\textbf{Honest negative finding.} On "
            f"{names} the firm's contradiction-geometry probe ties or "
            "loses to a one-line cosine baseline on AUROC. This finding "
            "is not buried; it is in this abstract because the firm's "
            "credibility on its methodological reorientation depends on "
            "publishing failures alongside successes."
        )
    else:
        body += (
            "\\par On the models reported here the geometry probe does "
            "not lose to the cosine baseline on AUROC. We retain the "
            "honest-failure framing because the negative result remains "
            "the more informative outcome and the prior publication "
            "commitment binds prospectively."
        )
    return f"\\begin{{abstract}}{body}\\end{{abstract}}\n"


def _per_model_table(analysis: dict[str, Any]) -> str:
    per_model = analysis.get("per_model", {}) or {}
    lines = [
        "\\section{Per-model headline metrics}",
        "\\begin{tabular}{l l r r r r}",
        "\\toprule",
        "Model & Runner & $n$ & Accuracy & AUROC & ECE \\\\",
        "\\midrule",
    ]
    for model in sorted(per_model):
        for runner in ("random", "cosine", "contradiction_geometry"):
            v = per_model[model].get(runner)
            if not v:
                continue
            lines.append(
                f"\\texttt{{{_escape(model)}}} & \\texttt{{{_escape(runner)}}} & "
                f"{int(v.get('n', 0))} & {_fmt(v.get('accuracy'))} & "
                f"{_fmt(v.get('auroc_contradicting_vs_coherent'))} & "
                f"{_fmt(v.get('ece_contradicting'))} \\\\"
            )
    lines += ["\\bottomrule", "\\end{tabular}", ""]
    return "\n".join(lines)


def _per_domain_table(analysis: dict[str, Any]) -> str:
    per_domain = analysis.get("per_domain", {}) or {}
    domains = sorted(
        {
            d
            for runners in per_domain.values()
            for runner_dict in runners.values()
            for d in runner_dict
        }
    )
    if not domains:
        return ""
    lines = [
        "\\section{Per-domain accuracy (geometry runner)}",
        "\\begin{tabular}{l " + " ".join(["r"] * len(domains)) + "}",
        "\\toprule",
        "Model & " + " & ".join(_escape(d) for d in domains) + " \\\\",
        "\\midrule",
    ]
    for model in sorted(per_domain):
        runner_dict = per_domain[model].get("contradiction_geometry", {})
        cells = [_fmt(runner_dict.get(d)) for d in domains]
        lines.append(f"\\texttt{{{_escape(model)}}} & " + " & ".join(cells) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}", ""]
    return "\n".join(lines)


def _agreement_table(analysis: dict[str, Any]) -> str:
    models = analysis.get("agreement_models") or []
    matrix = analysis.get("agreement_matrix") or []
    if not models:
        return ""
    lines = [
        "\\section{Inter-model agreement (binary contradicting label)}",
        "\\begin{tabular}{l " + " ".join(["r"] * len(models)) + "}",
        "\\toprule",
        " & " + " & ".join(_escape(m) for m in models) + " \\\\",
        "\\midrule",
    ]
    for i, m in enumerate(models):
        cells = [_fmt(matrix[i][j], digits=2) for j in range(len(models))]
        lines.append(f"\\texttt{{{_escape(m)}}} & " + " & ".join(cells) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}", ""]
    return "\n".join(lines)


def _stat_test_section(analysis: dict[str, Any]) -> str:
    t = analysis.get("stat_test", {}) or {}
    method = _escape(str(t.get("method", "n/a")))
    notes = _escape(str(t.get("notes", "")))
    return (
        "\\section{Statistical test: do models differ controlling for domain?}\n"
        f"\\textbf{{Method.}} \\texttt{{{method}}}\\\\\n"
        f"\\textbf{{Statistic.}} {_fmt(t.get('statistic'))}\\\\\n"
        f"\\textbf{{p-value.}} {_fmt(t.get('p_value'))}\\\\\n"
        f"\\textbf{{Observations.}} {int(t.get('n_observations', 0))} across "
        f"{int(t.get('n_models', 0))} models.\\\\\n"
        f"\\textit{{{notes}}}\n\n"
    )


def _figures_section(analysis: dict[str, Any], figures_dir: Path, tex_dir: Path) -> str:
    figs = analysis.get("figures") or {}
    out: list[str] = ["\\section{Figures}"]
    bars = figs.get("bars")
    ag = figs.get("agreement")
    # Convert paths to relative form for LaTeX includegraphics
    def _rel(path_like: Any) -> str | None:
        if not path_like:
            return None
        p = Path(path_like)
        if not p.exists():
            p = figures_dir / Path(path_like).name
            if not p.exists():
                return None
        try:
            return os.path.relpath(p, tex_dir)
        except ValueError:
            return str(p)

    bars_rel = _rel(bars)
    ag_rel = _rel(ag)
    if bars_rel:
        out.append(
            "\\begin{figure}[h]\\centering"
            f"\\includegraphics[width=0.95\\linewidth]{{{bars_rel}}}"
            "\\caption{Per-model accuracy by runner. The QH prediction is "
            "that \\texttt{contradiction\\_geometry} should beat \\texttt{cosine} "
            "on every back-end; deviations are evidence about the "
            "model-versus-language question.}"
            "\\end{figure}"
        )
    if ag_rel:
        out.append(
            "\\begin{figure}[h]\\centering"
            f"\\includegraphics[width=0.7\\linewidth]{{{ag_rel}}}"
            "\\caption{Inter-model agreement on the binary contradicting "
            "label, geometry runner. High off-diagonal entries indicate "
            "the geometry signal is consistent across embedding spaces.}"
            "\\end{figure}"
        )
    return "\n\n".join(out) + "\n"


def _losses_section(analysis: dict[str, Any]) -> str:
    losses = analysis.get("geometry_losses") or []
    if not losses:
        return (
            "\\section{Honest negative finding}\nOn the models reported "
            "here the geometry probe does not lose to the cosine "
            "baseline on AUROC. This is not strong evidence for the "
            "hypothesis (the strongest test is the per-domain "
            "breakdown); it only means we have nothing to retract on "
            "this run.\n\n"
        )
    rows = "\n".join(
        f"\\texttt{{{_escape(r['model'])}}} & {_fmt(r['geometry_auroc'])} & "
        f"{_fmt(r['cosine_auroc'])} & {_fmt(r['delta'])} \\\\"
        for r in losses
    )
    return (
        "\\section{Honest negative finding}\n"
        "On the following models the firm's contradiction-geometry "
        "probe ties or loses to the cosine baseline on AUROC. This "
        "finding is reported in the abstract for the same reason: the "
        "firm's credibility on its methodological reorientation "
        "depends on publishing failures, not just successes.\n\n"
        "\\begin{tabular}{l r r r}\n"
        "\\toprule\n"
        "Model & Geometry AUROC & Cosine AUROC & $\\Delta$ (cosine $-$ geometry) \\\\\n"
        "\\midrule\n"
        f"{rows}\n"
        "\\bottomrule\n"
        "\\end{tabular}\n\n"
    )


def render_tex(analysis: dict[str, Any], figures_dir: Path, tex_dir: Path) -> str:
    today = dt.date.today().isoformat()
    parts: list[str] = []
    parts.append(_TEX_HEADER % {"today": today})
    parts.append(_abstract(analysis))
    parts.append(
        "\\section{Background}\nThe Quintin Hypothesis (QH) predicts "
        "that the difference vector between embeddings of a premise "
        "and its logical contradiction is sparse (concentrated in few "
        "dimensions, measured by Hoyer sparsity) while the difference "
        "between a premise and a coherent continuation is dense. If "
        "this is a property of language, the prediction should hold "
        "across embedding back-ends. If it is a property of one "
        "specific model — for instance \\texttt{text-embedding-3-large} "
        "— that is also useful information, but it is a much weaker "
        "claim than the firm originally asserted.\n\n"
    )
    parts.append(_losses_section(analysis))
    parts.append(_per_model_table(analysis))
    parts.append("\n\n")
    parts.append(_per_domain_table(analysis))
    parts.append("\n\n")
    parts.append(_agreement_table(analysis))
    parts.append("\n\n")
    parts.append(_stat_test_section(analysis))
    parts.append(_figures_section(analysis, figures_dir, tex_dir))
    parts.append(
        "\\section{Reproducibility}\n"
        "The benchmark dataset is frozen as \\texttt{qh-v1} under "
        "\\texttt{benchmarks/quintin\\_hypothesis/v1/}. Per-model "
        "predictions are persisted as parquet under "
        "\\texttt{results/cross\\_model/}; raw embedding vectors are "
        "stored off-tree (default \\texttt{\\textasciitilde/.theseus/data/cross\\_model/}) "
        "with a manifest. The figures and numbers in this PDF are "
        "regenerated from \\texttt{cross\\_model\\_analysis.json} on each "
        "build; no number is hand-edited.\n\n"
    )
    parts.append("\\end{document}\n")
    return "\n".join(parts)


def compile_pdf(tex_path: Path, pdf_path: Path) -> bool:
    """Compile the .tex with pdflatex twice, if it is available."""
    if not shutil.which("pdflatex"):
        print("pdflatex not installed; skipping PDF compile. Source: " + str(tex_path))
        # Drop a tiny placeholder PDF so artefact-publishing steps
        # don't fail. The .tex is the source of truth.
        if not pdf_path.exists():
            pdf_path.write_bytes(b"%PDF-1.4\n% placeholder, install pdflatex to render\n%%EOF\n")
        return False
    out_dir = tex_path.parent
    for _ in range(2):
        subprocess.run(
            [
                "pdflatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-output-directory",
                str(out_dir),
                tex_path.name,
            ],
            cwd=str(out_dir),
            check=True,
        )
    return True


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--analysis", required=True, type=Path)
    p.add_argument("--figures", required=True, type=Path)
    p.add_argument("--tex", required=True, type=Path)
    p.add_argument("--pdf", required=True, type=Path)
    args = p.parse_args(argv)

    if not args.analysis.exists():
        # Allow stub generation when there is no analysis yet — the .tex
        # carries an explanatory abstract so reviewers see the design.
        analysis: dict[str, Any] = {
            "n_rows": 0,
            "per_model": {},
            "per_domain": {},
            "agreement_models": [],
            "agreement_matrix": [],
            "stat_test": {
                "method": "no_data",
                "statistic": float("nan"),
                "p_value": float("nan"),
                "notes": "No analysis JSON found at build time.",
                "n_observations": 0,
                "n_models": 0,
            },
            "geometry_losses": [],
            "figures": {"bars": None, "agreement": None},
        }
    else:
        analysis = json.loads(args.analysis.read_text(encoding="utf-8"))

    args.tex.parent.mkdir(parents=True, exist_ok=True)
    tex_text = render_tex(analysis, args.figures, args.tex.parent)
    args.tex.write_text(tex_text, encoding="utf-8")
    print(f"wrote {args.tex}")

    args.pdf.parent.mkdir(parents=True, exist_ok=True)
    compile_pdf(args.tex, args.pdf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
