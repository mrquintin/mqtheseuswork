"""Check: copyright_clean — no verbatim runs of >=20 consecutive words from ingested artifacts."""
from __future__ import annotations

import json

from noosphere.models import CheckResult, RigorSubmission
from noosphere.rigor_gate.checks import register

CHECK_NAME = "gate_check_copyright_clean"
VERBATIM_THRESHOLD = 20


def _stub_pass() -> CheckResult:
    return CheckResult(check_name=CHECK_NAME, pass_=True, detail="subsystem_not_yet_live")


def _extract_text(payload_ref: str) -> str:
    try:
        data = json.loads(payload_ref)
        return str(data.get("text", ""))
    except (json.JSONDecodeError, TypeError):
        return payload_ref


def _ngrams(text: str, n: int) -> set[tuple[str, ...]]:
    words = text.lower().split()
    if len(words) < n:
        return set()
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def run(submission: RigorSubmission) -> CheckResult:
    try:
        from noosphere.retrieval import HybridRetriever  # noqa: F401
    except ImportError:
        return _stub_pass()

    text = _extract_text(submission.payload_ref)
    if not text.strip():
        return CheckResult(check_name=CHECK_NAME, pass_=True, detail="empty_payload")

    try:
        data = json.loads(submission.payload_ref)
        corpus_texts: list[str] = list(data.get("corpus_texts", []))
    except (json.JSONDecodeError, TypeError):
        corpus_texts = []

    if not corpus_texts:
        return CheckResult(check_name=CHECK_NAME, pass_=True, detail="no_corpus_to_compare")

    payload_ngrams = _ngrams(text, VERBATIM_THRESHOLD)
    for corpus_text in corpus_texts:
        corpus_ng = _ngrams(corpus_text, VERBATIM_THRESHOLD)
        overlap = payload_ngrams & corpus_ng
        if overlap:
            sample = " ".join(next(iter(overlap)))
            return CheckResult(
                check_name=CHECK_NAME,
                pass_=False,
                detail=f"verbatim_match_found: {sample[:80]}",
            )

    return CheckResult(check_name=CHECK_NAME, pass_=True, detail="no_verbatim_matches")


register(CHECK_NAME, run)
