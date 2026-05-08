"""Curated failure-mode catalogs for registered methods.

A failure-mode catalog is a YAML file that sits next to the method
implementation (``<method>.FAILURES.yaml``) and lists the ways the
method is known or suspected to break. The catalog is human-curated:
LLMs may suggest entries, but a human must approve. The loader here is
strict — a malformed or missing catalog raises at import time so CI
catches drift.

Two query paths are exposed:

* :func:`failure_modes_for` — given a method name and a conclusion,
  filter the catalog to entries whose trigger conditions plausibly
  apply. The match is LLM-assisted with a deterministic threshold; the
  decision is persisted (input hash → output) so the same conclusion
  yields the same matched set without re-paying for inference.
* :func:`load_catalog` / :func:`load_all_catalogs` — raw access for
  publishing surfaces (founder UI, public methodology page, CLI lint).
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Optional

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

Severity = Literal["low", "medium", "high"]


class FailureModeCitation(BaseModel):
    """A single citation backing a failure mode."""

    title: str = Field(min_length=1)
    url: Optional[str] = None
    note: Optional[str] = None


class FailureMode(BaseModel):
    """One curated failure mode for a method."""

    name: str = Field(min_length=1)
    description: str
    worked_example: str = Field(min_length=1)
    trigger_conditions: str = Field(min_length=1)
    mitigation: str = Field(min_length=1)
    severity: Severity
    citations: list[FailureModeCitation] = Field(default_factory=list)
    public: bool = False

    @field_validator("description")
    @classmethod
    def _description_min_two_sentences(cls, v: str) -> str:
        text = v.strip()
        if not text:
            raise ValueError("description is required")
        # A "sentence" here is a span ending in . ! or ? — counted
        # liberally so that quoted text and abbreviations don't trip
        # us up in the common case.
        sentences = [s for s in _split_sentences(text) if s.strip()]
        if len(sentences) < 2:
            raise ValueError(
                "description must have at least two sentences "
                "(separate sentences with `.`, `!`, or `?`)"
            )
        return text


def _split_sentences(text: str) -> list[str]:
    out: list[str] = []
    buf: list[str] = []
    for ch in text:
        buf.append(ch)
        if ch in ".!?":
            out.append("".join(buf).strip())
            buf = []
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


class FailureCatalog(BaseModel):
    """Top-level shape of a ``<method>.FAILURES.yaml`` file.

    Either ``modes`` is a non-empty list of :class:`FailureMode`, or
    the catalog is explicitly opted out with ``failures:
    deliberately-empty`` and a ≥2-sentence justification.
    """

    method: str = Field(min_length=1)
    failures: Optional[Literal["deliberately-empty"]] = None
    justification: Optional[str] = None
    modes: list[FailureMode] = Field(default_factory=list)

    @classmethod
    def validate_shape(cls, data: dict[str, Any]) -> "FailureCatalog":
        catalog = cls.model_validate(data)
        if catalog.failures == "deliberately-empty":
            if catalog.modes:
                raise ValueError(
                    "deliberately-empty catalog must not list modes"
                )
            justification = (catalog.justification or "").strip()
            sentences = [
                s for s in _split_sentences(justification) if s.strip()
            ]
            if len(sentences) < 2:
                raise ValueError(
                    "deliberately-empty catalog requires a justification "
                    "of at least two sentences"
                )
        else:
            if not catalog.modes:
                raise ValueError(
                    "catalog must list at least one mode, or set "
                    "`failures: deliberately-empty` with a ≥2-sentence "
                    "justification"
                )
        return catalog


# ── Loader ─────────────────────────────────────────────────────────────

_METHODS_DIR = Path(__file__).parent
_CATALOG_SUFFIX = ".FAILURES.yaml"


class FailureCatalogError(Exception):
    """Raised when a catalog is missing or malformed."""


def catalog_path(method_name: str, methods_dir: Optional[Path] = None) -> Path:
    return (methods_dir or _METHODS_DIR) / f"{method_name}{_CATALOG_SUFFIX}"


def load_catalog(
    method_name: str, methods_dir: Optional[Path] = None
) -> FailureCatalog:
    path = catalog_path(method_name, methods_dir)
    if not path.exists():
        raise FailureCatalogError(
            f"missing failure-mode catalog: {path.name} "
            f"(every registered method requires one; opt out with "
            f"`failures: deliberately-empty` + justification)"
        )
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise FailureCatalogError(f"YAML parse error in {path.name}: {exc}")
    if not isinstance(raw, dict):
        raise FailureCatalogError(
            f"{path.name}: top-level must be a mapping"
        )
    raw.setdefault("method", method_name)
    try:
        return FailureCatalog.validate_shape(raw)
    except (ValidationError, ValueError) as exc:
        raise FailureCatalogError(f"{path.name}: {exc}")


def load_all_catalogs(
    methods_dir: Optional[Path] = None,
) -> dict[str, FailureCatalog]:
    base = methods_dir or _METHODS_DIR
    out: dict[str, FailureCatalog] = {}
    for path in sorted(base.glob(f"*{_CATALOG_SUFFIX}")):
        method_name = path.name[: -len(_CATALOG_SUFFIX)]
        out[method_name] = load_catalog(method_name, methods_dir=base)
    return out


# ── LLM-assisted match (with persistent cache) ────────────────────────

_DEFAULT_THRESHOLD = 0.5
_PROMPT_VERSION = "failure-match/v1"
_DEFAULT_CACHE_PATH = (
    Path(os.environ.get("NOOSPHERE_DATA_DIR", "noosphere_data"))
    / "failure_match_cache.json"
)
_CACHE_LOCK = threading.Lock()


class FailureMatch(BaseModel):
    """One mode's match decision for a given conclusion."""

    mode_name: str
    score: float
    matched: bool
    rationale: str = ""


class FailureMatchResult(BaseModel):
    """The full audit record for a (method, conclusion) match call."""

    method: str
    input_hash: str
    model_name: str
    prompt_version: str
    threshold: float
    matches: list[FailureMatch]


def _hash_inputs(
    method: str,
    conclusion_text: str,
    mode_names: Iterable[str],
    prompt_version: str,
    model_name: str,
    threshold: float,
) -> str:
    payload = json.dumps(
        {
            "method": method,
            "conclusion": conclusion_text,
            "modes": sorted(mode_names),
            "prompt_version": prompt_version,
            "model_name": model_name,
            "threshold": threshold,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_cache(cache_path: Path) -> dict[str, Any]:
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache_path: Path, data: dict[str, Any]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(cache_path)


# Default deterministic matcher: lexical overlap between the trigger
# conditions and the conclusion text. Production deployments swap this
# for an LLM matcher via the ``matcher`` parameter.
def _lexical_match_score(trigger: str, conclusion_text: str) -> float:
    def _tokens(s: str) -> set[str]:
        return {t.lower().strip(".,;:!?") for t in s.split() if len(t) > 3}

    a = _tokens(trigger)
    b = _tokens(conclusion_text)
    if not a:
        return 0.0
    return len(a & b) / max(1, len(a))


Matcher = Callable[[FailureMode, str], tuple[float, str]]


def _default_matcher(mode: FailureMode, conclusion_text: str) -> tuple[float, str]:
    score = _lexical_match_score(mode.trigger_conditions, conclusion_text)
    rationale = (
        f"lexical-overlap={score:.3f} between trigger and conclusion"
    )
    return score, rationale


def failure_modes_for(
    method: str,
    conclusion: Any,
    *,
    methods_dir: Optional[Path] = None,
    matcher: Optional[Matcher] = None,
    threshold: float = _DEFAULT_THRESHOLD,
    model_name: str = "lexical-overlap-v1",
    prompt_version: str = _PROMPT_VERSION,
    cache_path: Optional[Path] = None,
) -> FailureMatchResult:
    """Return failure modes whose trigger conditions plausibly apply.

    The match decision is keyed on a SHA-256 of (method, conclusion
    text, sorted mode names, prompt version, model, threshold). Repeat
    calls with the same inputs read from the on-disk cache and pay no
    inference cost.
    """

    catalog = load_catalog(method, methods_dir=methods_dir)
    text = _extract_conclusion_text(conclusion)
    matcher_fn = matcher or _default_matcher

    if catalog.failures == "deliberately-empty":
        return FailureMatchResult(
            method=method,
            input_hash=_hash_inputs(
                method, text, [], prompt_version, model_name, threshold
            ),
            model_name=model_name,
            prompt_version=prompt_version,
            threshold=threshold,
            matches=[],
        )

    mode_names = [m.name for m in catalog.modes]
    digest = _hash_inputs(
        method, text, mode_names, prompt_version, model_name, threshold
    )
    cache_file = cache_path or _DEFAULT_CACHE_PATH

    with _CACHE_LOCK:
        cache = _load_cache(cache_file)
        cached = cache.get(digest)
        if cached is not None:
            try:
                return FailureMatchResult.model_validate(cached)
            except ValidationError:
                pass

    matches: list[FailureMatch] = []
    for mode in catalog.modes:
        score, rationale = matcher_fn(mode, text)
        score = max(0.0, min(1.0, float(score)))
        matches.append(
            FailureMatch(
                mode_name=mode.name,
                score=score,
                matched=score >= threshold,
                rationale=rationale,
            )
        )

    result = FailureMatchResult(
        method=method,
        input_hash=digest,
        model_name=model_name,
        prompt_version=prompt_version,
        threshold=threshold,
        matches=matches,
    )

    with _CACHE_LOCK:
        cache = _load_cache(cache_file)
        cache[digest] = result.model_dump()
        _save_cache(cache_file, cache)

    return result


def matched_modes(
    result: FailureMatchResult, catalog: FailureCatalog
) -> list[FailureMode]:
    """Resolve a match result back to the FailureMode objects it picks."""

    by_name = {m.name: m for m in catalog.modes}
    return [
        by_name[m.mode_name]
        for m in result.matches
        if m.matched and m.mode_name in by_name
    ]


def merge_catalogs(
    catalogs: Iterable[FailureCatalog],
) -> dict[str, list[FailureMode]]:
    """Group all modes across catalogs by method name. Useful for
    reviewers that want priors across an ensemble of methods."""

    out: dict[str, list[FailureMode]] = {}
    for cat in catalogs:
        if cat.failures == "deliberately-empty":
            out.setdefault(cat.method, [])
            continue
        out.setdefault(cat.method, []).extend(cat.modes)
    return out


def _extract_conclusion_text(conclusion: Any) -> str:
    if conclusion is None:
        return ""
    if isinstance(conclusion, str):
        return conclusion
    for attr in ("text", "description", "claim"):
        v = getattr(conclusion, attr, None)
        if isinstance(v, str) and v:
            return v
    if isinstance(conclusion, dict):
        for key in ("text", "description", "claim"):
            v = conclusion.get(key)
            if isinstance(v, str) and v:
                return v
    return str(conclusion)


# ── Author-time tooling ────────────────────────────────────────────────

_SCAFFOLD_TEMPLATE = """\
method: {method}
modes:
  - name: example_failure_mode
    description: |
      Replace this with a real description of how the method fails.
      Two sentences minimum: name the failure, then say what makes it
      hard to detect from inside the method's normal output.
    worked_example: |
      Cite a real or constructed case where this failure was observed.
    trigger_conditions: |
      Free-text conditions that should put a reviewer on alert.
    mitigation: |
      What the firm should do when this trigger fires.
    severity: medium
    citations: []
    public: false
"""


def scaffold_catalog(method_name: str, methods_dir: Optional[Path] = None) -> Path:
    """Write a starter ``<method>.FAILURES.yaml`` if one does not exist."""

    path = catalog_path(method_name, methods_dir)
    if path.exists():
        raise FailureCatalogError(
            f"refusing to overwrite existing catalog at {path}"
        )
    path.write_text(_SCAFFOLD_TEMPLATE.format(method=method_name), encoding="utf-8")
    return path


def lint_all(methods_dir: Optional[Path] = None) -> dict[str, FailureCatalog]:
    """Validate every catalog under ``methods_dir`` and return them.
    Raises :class:`FailureCatalogError` on the first problem."""

    return load_all_catalogs(methods_dir=methods_dir)


__all__ = [
    "FailureCatalog",
    "FailureCatalogError",
    "FailureMatch",
    "FailureMatchResult",
    "FailureMode",
    "FailureModeCitation",
    "Matcher",
    "catalog_path",
    "failure_modes_for",
    "lint_all",
    "load_all_catalogs",
    "load_catalog",
    "matched_modes",
    "merge_catalogs",
    "scaffold_catalog",
]
