"""Memo PDF builder — pdflatex pipeline (prompt 11, Round 19).

The :func:`build_memo_pdf` entrypoint takes an :class:`InvestmentMemo`,
escapes the markdown body into LaTeX, fills the canonical template at
``docs/memos/_template.tex``, and shells out to
``docs/memos/build_memo_pdf.sh`` (the firm's two-pass pdflatex script)
to produce the rendered PDF.

The script is the canonical entrypoint — keeping the LaTeX invocation
out of Python means founders can rebuild a memo's PDF from a shell
without booting the synthesizer at all.

Failure modes (returns ``None``, never raises in production):

* ``pdflatex`` not on PATH — most CI / sandboxed dev environments.
* The template is missing / unreadable.
* The script exits non-zero (the LaTeX log is logged at WARNING).

When this function returns ``None`` the memo's :attr:`pdf_path`
remains ``None``; the markdown body is still written and the memo is
still persisted. PDFs are a derived artifact and a memo without a PDF
is still a complete memo.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from noosphere.models import InvestmentMemo, memo_paths


logger = logging.getLogger(__name__)


# Project root is two parents above this file:
# noosphere/noosphere/synthesizer/memo_pdf.py → repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATE_PATH = _REPO_ROOT / "docs" / "memos" / "_template.tex"
_BUILD_SCRIPT = _REPO_ROOT / "docs" / "memos" / "build_memo_pdf.sh"


# ── LaTeX escaping ─────────────────────────────────────────────────


_LATEX_SPECIAL = {
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


def _latex_escape(s: str) -> str:
    if not s:
        return ""
    out: list[str] = []
    for ch in s:
        out.append(_LATEX_SPECIAL.get(ch, ch))
    return "".join(out)


_HEADING_RE = re.compile(r"^(#{1,3})\s+(?:\d+\.\s+)?(.+?)\s*$")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*]+?)\*(?!\*)")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")


def _render_markdown_to_latex(body: str) -> str:
    """Best-effort markdown-to-LaTeX rendering.

    Restrained on purpose: handles H1/H2/H3, bold, italic, inline code,
    bullet lists, and numbered lists. The template owns the page
    geometry, font, and cover — this function only fills the
    ``%%BODY%%`` placeholder.
    """

    lines = body.splitlines()
    out: list[str] = []
    in_ul = False
    in_ol = False

    def _close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            out.append(r"\end{itemize}")
            in_ul = False
        if in_ol:
            out.append(r"\end{enumerate}")
            in_ol = False

    def _inline(text: str) -> str:
        # Order matters: escape first, then re-introduce the formatting
        # tokens. We bracket the format markers with sentinels so the
        # escaper doesn't touch them.
        bold_spans: list[str] = []
        italic_spans: list[str] = []
        code_spans: list[str] = []

        def _stash_bold(m: re.Match[str]) -> str:
            bold_spans.append(m.group(1))
            return f"\x00BOLD{len(bold_spans) - 1}\x00"

        def _stash_italic(m: re.Match[str]) -> str:
            italic_spans.append(m.group(1))
            return f"\x00ITAL{len(italic_spans) - 1}\x00"

        def _stash_code(m: re.Match[str]) -> str:
            code_spans.append(m.group(1))
            return f"\x00CODE{len(code_spans) - 1}\x00"

        t = _INLINE_CODE_RE.sub(_stash_code, text)
        t = _BOLD_RE.sub(_stash_bold, t)
        t = _ITALIC_RE.sub(_stash_italic, t)
        t = _latex_escape(t)
        for idx, span in enumerate(bold_spans):
            t = t.replace(
                f"\x00BOLD{idx}\x00", r"\textbf{" + _latex_escape(span) + r"}"
            )
        for idx, span in enumerate(italic_spans):
            t = t.replace(
                f"\x00ITAL{idx}\x00", r"\emph{" + _latex_escape(span) + r"}"
            )
        for idx, span in enumerate(code_spans):
            t = t.replace(
                f"\x00CODE{idx}\x00", r"\texttt{" + _latex_escape(span) + r"}"
            )
        return t

    for raw_line in lines:
        line = raw_line.rstrip()
        if not line.strip():
            _close_lists()
            out.append("")
            continue

        heading = _HEADING_RE.match(line)
        if heading is not None:
            _close_lists()
            level, text = len(heading.group(1)), heading.group(2)
            cmd = {1: r"\section*", 2: r"\subsection*", 3: r"\subsubsection*"}.get(
                level, r"\paragraph"
            )
            out.append(f"{cmd}{{{_inline(text)}}}")
            continue

        if line.lstrip().startswith(("- ", "* ")):
            if not in_ul:
                _close_lists()
                out.append(r"\begin{itemize}")
                in_ul = True
            item = line.lstrip()[2:]
            out.append(r"\item " + _inline(item))
            continue

        m = re.match(r"^(\d+)\.\s+(.+)$", line.lstrip())
        if m is not None:
            if not in_ol:
                _close_lists()
                out.append(r"\begin{enumerate}")
                in_ol = True
            out.append(r"\item " + _inline(m.group(2)))
            continue

        _close_lists()
        out.append(_inline(line))

    _close_lists()
    return "\n".join(out)


# ── Template fill ──────────────────────────────────────────────────


def _format_date(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d")


def render_template(memo: InvestmentMemo, *, template: Optional[str] = None) -> str:
    """Render the LaTeX source for ``memo``.

    ``template`` defaults to the canonical
    ``docs/memos/_template.tex`` text. Useful seam for tests that want
    to validate the substitution without depending on the on-disk
    template.
    """

    if template is None:
        if not _TEMPLATE_PATH.exists():
            raise FileNotFoundError(
                f"memo template missing at {_TEMPLATE_PATH}"
            )
        template = _TEMPLATE_PATH.read_text(encoding="utf-8")

    body = _render_markdown_to_latex(memo.body_markdown or "")
    return (
        template
        .replace("%%TITLE%%", _latex_escape(memo.title or "Untitled memo"))
        .replace("%%TLDR%%", _latex_escape(memo.tldr or ""))
        .replace(
            "%%ADDRESSEE%%",
            _latex_escape(memo.addressee or "Portfolio Agent"),
        )
        .replace("%%DATE%%", _latex_escape(_format_date(memo.created_at)))
        .replace(
            "%%AUTHOR%%",
            _latex_escape(
                f"Theseus — {memo.synthesizer_version or 'synthesizer'}"
            ),
        )
        .replace("%%BODY%%", body)
    )


# ── Public entrypoint ──────────────────────────────────────────────


def build_memo_pdf(memo: InvestmentMemo, *, repo_root: Optional[Path] = None) -> Optional[str]:
    """Render ``memo`` to a PDF via the pdflatex script. Returns the path or None.

    The returned path is project-relative (e.g.
    ``docs/memos/2026/05/foo-abcd1234.pdf``), matching what gets
    persisted as :attr:`InvestmentMemo.pdf_path`.
    """

    root = repo_root or _REPO_ROOT
    if shutil.which("pdflatex") is None:
        logger.info(
            "synthesizer.memo_pdf.skipped",
            extra={"reason": "pdflatex_not_on_path", "memo_id": memo.id},
        )
        return None
    template_path = root / "docs" / "memos" / "_template.tex"
    script_path = root / "docs" / "memos" / "build_memo_pdf.sh"
    if not template_path.exists() or not script_path.exists():
        logger.warning(
            "synthesizer.memo_pdf.skipped",
            extra={
                "reason": "template_or_script_missing",
                "memo_id": memo.id,
                "template": str(template_path),
                "script": str(script_path),
            },
        )
        return None

    md_rel, pdf_rel = memo_paths(created_at=memo.created_at, slug=memo.slug)
    pdf_abs = root / pdf_rel
    tex_abs = pdf_abs.with_suffix(".tex")
    pdf_abs.parent.mkdir(parents=True, exist_ok=True)

    try:
        latex_source = render_template(memo, template=template_path.read_text(encoding="utf-8"))
        tex_abs.write_text(latex_source, encoding="utf-8")
    except Exception as exc:
        logger.warning(
            "synthesizer.memo_pdf.render_failed",
            extra={"memo_id": memo.id, "error": f"{type(exc).__name__}: {exc}"},
        )
        return None

    try:
        proc = subprocess.run(
            ["bash", str(script_path), str(tex_abs)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning(
            "synthesizer.memo_pdf.script_failed",
            extra={"memo_id": memo.id, "error": f"{type(exc).__name__}: {exc}"},
        )
        return None
    if proc.returncode != 0:
        logger.warning(
            "synthesizer.memo_pdf.nonzero_exit",
            extra={
                "memo_id": memo.id,
                "returncode": proc.returncode,
                "stderr": (proc.stderr or "")[-2_000:],
            },
        )
        return None
    if not pdf_abs.exists():
        logger.warning(
            "synthesizer.memo_pdf.missing_output",
            extra={"memo_id": memo.id, "expected": str(pdf_abs)},
        )
        return None
    return pdf_rel


__all__ = [
    "build_memo_pdf",
    "render_template",
]
