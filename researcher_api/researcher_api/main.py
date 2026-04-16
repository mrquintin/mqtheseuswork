"""
Theseus Researcher API — FastAPI application (SP07).

Capability-only: researchers supply text; no firm or cross-tenant data is read.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Annotated, Any

def _repo_root() -> Path:
    """Monorepo root for bundled docs; set THESEUS_REPO_ROOT in container installs."""
    env = os.environ.get("THESEUS_REPO_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2]


_REPO_ROOT = _repo_root()
_NOOSPHERE = _REPO_ROOT / "noosphere"
if _NOOSPHERE.is_dir():
    sys.path.insert(0, str(_NOOSPHERE))

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field, model_validator

from researcher_api import __version__
from researcher_api.audit import append_audit, body_fingerprint
from researcher_api.claims_util import synthetic_claim
from researcher_api.config import (
    allow_coherence_judge,
    api_git_sha,
    lookup_api_key,
    rate_limit_per_hour,
)
from researcher_api.problem import Problem
from researcher_api.rate_limit import check_rate_limit
from researcher_api.scoring_hosted import prob_mid_row, score_prediction_rows

_API_PREFIX = "/v1"


def _problem_response(p: Problem) -> JSONResponse:
    return JSONResponse(
        status_code=p.status,
        content=jsonable_encoder(p.model_dump(exclude_none=True)),
        media_type="application/problem+json",
    )


app = FastAPI(
    title="Theseus Researcher API",
    version=__version__,
    description="Methodology subset for external investigators. See /docs and docs/researcher-api/.",
    openapi_tags=[
        {"name": "extract", "description": "Claim extraction from plain text"},
        {"name": "coherence", "description": "Six-layer coherence on two claim strings"},
        {"name": "embed", "description": "Embedding vectors (researcher texts)"},
        {"name": "predict-score", "description": "Brier / log-loss / bins on supplied predictions"},
        {"name": "replay", "description": "Time-machine replay (stub in v1)"},
        {"name": "methods", "description": "Method notes and version metadata"},
        {"name": "register", "description": "Researcher signup (planned)"},
        {"name": "security", "description": "Coordinated disclosure policy"},
        {"name": "round3", "description": "Round-3 read-only endpoints for UIs"},
    ],
)

from researcher_api.routes.round3 import router as round3_router  # noqa: E402

app.include_router(round3_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    p = Problem(
        title="Validation error",
        status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=str(exc.errors()),
        instance=str(request.url),
    )
    return _problem_response(p)


@app.exception_handler(HTTPException)
async def http_exc_handler(request: Request, exc: HTTPException) -> JSONResponse:
    det = exc.detail
    title = det if isinstance(det, str) else "HTTP error"
    p = Problem(
        title=title,
        status=int(exc.status_code),
        detail=str(det),
        instance=str(request.url),
    )
    return _problem_response(p)


class ApiKeyUser(BaseModel):
    label: str
    sandbox_tenant_id: str
    secret: str


def require_api_key(x_api_key: str | None) -> ApiKeyUser:
    if not x_api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing X-API-Key header")
    rec = lookup_api_key(x_api_key.strip())
    if rec is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
    return ApiKeyUser(label=rec.label, sandbox_tenant_id=rec.sandbox_tenant_id, secret=rec.secret)


def get_api_user(request: Request) -> ApiKeyUser:
    return require_api_key(request.headers.get("X-API-Key"))


def _attach_version_headers(response: Response) -> None:
    response.headers["X-Theseus-API-Version"] = __version__
    response.headers["X-Theseus-Git-SHA"] = api_git_sha()
    response.headers["X-Theseus-LLM-Disclaimer"] = "structured-only"


async def _gate_rate_limit(request: Request, user: ApiKeyUser) -> None:
    route = request.scope.get("path", "")
    ok, retry = check_rate_limit(
        api_key=user.secret, route=route, limit_per_hour=rate_limit_per_hour()
    )
    if not ok:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Rate limit exceeded; retry after {retry}s",
            headers={"Retry-After": str(retry)},
        )


# ── Request bodies ───────────────────────────────────────────────────────────


class ExtractClaimsBody(BaseModel):
    text: str = Field(min_length=1, max_length=120_000)


class CoherenceBody(BaseModel):
    claim_a: str = Field(min_length=1, max_length=16_000)
    claim_b: str = Field(min_length=1, max_length=16_000)
    layers: list[str] | None = Field(
        default=None,
        description="Optional subset hint; judge layer only if server enables RESEARCHER_API_COHERENCE_JUDGE=1",
    )


class EmbedBody(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _text_lengths(self) -> EmbedBody:
        for t in self.texts:
            if len(t) > 8000:
                raise ValueError("each text must be <= 8000 characters")
        return self


class PredictRow(BaseModel):
    prob_low: float = Field(ge=0.0, le=1.0)
    prob_high: float = Field(ge=0.0, le=1.0)
    outcome: int = Field(ge=0, le=1)

    def mid(self) -> float:
        lo, hi = self.prob_low, self.prob_high
        if lo > hi:
            lo, hi = hi, lo
        return prob_mid_row(lo, hi)


class PredictScoreBody(BaseModel):
    predictions: list[PredictRow] = Field(min_length=1, max_length=10_000)


class ReplayBody(BaseModel):
    corpus_note: str = Field(default="", max_length=2000)
    as_of: str = Field(description="ISO date YYYY-MM-DD", pattern=r"^\d{4}-\d{2}-\d{2}$")


# ── Lazy embedder ───────────────────────────────────────────────────────────

_embedder: Any = None


def _get_embedder() -> Any:
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer

        from noosphere.config import get_settings

        s = get_settings()
        _embedder = SentenceTransformer(s.embedding_model_name, device=s.embedding_device)
    return _embedder


# ── Routes ──────────────────────────────────────────────────────────────────


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/security", tags=["security"])
def security_policy() -> PlainTextResponse:
    """Coordinated disclosure policy (SP08); Markdown served as text/plain."""
    path = _REPO_ROOT / "docs" / "researcher-api" / "SECURITY.md"
    if not path.is_file():
        return PlainTextResponse("Security policy not bundled in this deployment.\n", status_code=404)
    return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="text/plain; charset=utf-8")


@app.post(f"{_API_PREFIX}/extract-claims", tags=["extract"])
async def extract_claims(
    request: Request,
    response: Response,
    body: ExtractClaimsBody,
    user: Annotated[ApiKeyUser, Depends(get_api_user)],
) -> dict[str, Any]:
    await _gate_rate_limit(request, user)
    t0 = time.perf_counter()
    raw = await request.body()
    try:
        from noosphere.claim_extractor import ClaimExtractor
        from noosphere.models import Chunk

        ch = Chunk(
            id="api-chunk",
            artifact_id="api-artifact",
            start_offset=0,
            end_offset=len(body.text),
            text=body.text,
            metadata={"sandbox_tenant": user.sandbox_tenant_id},
        )
        ext = ClaimExtractor(store=None)
        claims = ext.extract(ch, episode_id="researcher-api", episode_date=None)
        out = [c.model_dump(mode="json") for c in claims]
        cost = 2.0
        response.headers["X-Theseus-Cost-Units"] = str(cost)
        _attach_version_headers(response)
        append_audit(
            api_key_label=user.label,
            sandbox_tenant_id=user.sandbox_tenant_id,
            route=request.url.path,
            request_sha256=body_fingerprint(raw),
            latency_ms=(time.perf_counter() - t0) * 1000,
            cost_units=cost,
            ok=True,
            status_code=200,
        )
        return {
            "claims": out,
            "sandbox_tenant_id": user.sandbox_tenant_id,
            "llm_used": True,
            "llm_disclaimer": "Extraction is LLM-generated and must be verified by the researcher.",
        }
    except Exception as e:
        cost = 0.5
        response.headers["X-Theseus-Cost-Units"] = str(cost)
        _attach_version_headers(response)
        append_audit(
            api_key_label=user.label,
            sandbox_tenant_id=user.sandbox_tenant_id,
            route=request.url.path,
            request_sha256=body_fingerprint(raw),
            latency_ms=(time.perf_counter() - t0) * 1000,
            cost_units=cost,
            ok=False,
            status_code=500,
        )
        raise HTTPException(500, str(e)) from e


@app.post(f"{_API_PREFIX}/coherence", tags=["coherence"])
async def coherence(
    request: Request,
    response: Response,
    body: CoherenceBody,
    user: Annotated[ApiKeyUser, Depends(get_api_user)],
) -> dict[str, Any]:
    await _gate_rate_limit(request, user)
    t0 = time.perf_counter()
    raw = await request.body()
    use_judge = bool(
        allow_coherence_judge()
        and body.layers
        and any(str(x).lower() == "judge" for x in body.layers)
    )
    try:
        from noosphere.coherence.aggregator import CoherenceAggregator
        from noosphere.coherence.nli import StubNLIScorer
        from noosphere.models import CoherenceVerdict

        a = synthetic_claim(body.claim_a, slot="A")
        b = synthetic_claim(body.claim_b, slot="B")
        agg = CoherenceAggregator(
            skip_llm_judge=not use_judge,
            skip_probabilistic_llm=True,
            nli=StubNLIScorer(verdict=CoherenceVerdict.UNRESOLVED),
        )
        res = agg.evaluate_pair(a, b, store=None)
        payload = res.payload.model_dump(mode="json")
        judge_note = None
        if res.judge_packet is not None:
            judge_note = {
                "verdict": res.judge_packet.verdict.value,
                "confidence": float(res.judge_packet.confidence),
                "llm_disclaimer": "Judge output is LLM-generated structured adjudication only.",
            }
        cost = 8.0 if use_judge else 5.0
        response.headers["X-Theseus-Cost-Units"] = str(cost)
        _attach_version_headers(response)
        append_audit(
            api_key_label=user.label,
            sandbox_tenant_id=user.sandbox_tenant_id,
            route=request.url.path,
            request_sha256=body_fingerprint(raw),
            latency_ms=(time.perf_counter() - t0) * 1000,
            cost_units=cost,
            ok=True,
            status_code=200,
        )
        return {
            "six_layer": payload.get("prior_scores"),
            "final_verdict": payload.get("final_verdict"),
            "aggregator_verdict": payload.get("aggregator_verdict"),
            "sandbox_tenant_id": user.sandbox_tenant_id,
            "judge": judge_note,
            "layers_requested": body.layers or [],
            "llm_components": {"judge_enabled": use_judge, "probabilistic_llm": False},
        }
    except Exception as e:
        append_audit(
            api_key_label=user.label,
            sandbox_tenant_id=user.sandbox_tenant_id,
            route=request.url.path,
            request_sha256=body_fingerprint(raw),
            latency_ms=(time.perf_counter() - t0) * 1000,
            cost_units=1.0,
            ok=False,
            status_code=500,
        )
        raise HTTPException(500, str(e)) from e


@app.post(f"{_API_PREFIX}/embed", tags=["embed"])
async def embed_vectors(
    request: Request,
    response: Response,
    body: EmbedBody,
    user: Annotated[ApiKeyUser, Depends(get_api_user)],
) -> dict[str, Any]:
    await _gate_rate_limit(request, user)
    t0 = time.perf_counter()
    raw = await request.body()
    model = _get_embedder()
    vecs = model.encode(body.texts, convert_to_numpy=True)
    rows = vecs.tolist()
    cost = 0.1 * len(body.texts)
    response.headers["X-Theseus-Cost-Units"] = str(cost)
    _attach_version_headers(response)
    append_audit(
        api_key_label=user.label,
        sandbox_tenant_id=user.sandbox_tenant_id,
        route=request.url.path,
        request_sha256=body_fingerprint(raw),
        latency_ms=(time.perf_counter() - t0) * 1000,
        cost_units=cost,
        ok=True,
        status_code=200,
    )
    return {
        "embeddings": rows,
        "sandbox_tenant_id": user.sandbox_tenant_id,
        "llm_used": False,
    }


@app.post(f"{_API_PREFIX}/predict-score", tags=["predict-score"])
async def predict_score(
    request: Request,
    response: Response,
    body: PredictScoreBody,
    user: Annotated[ApiKeyUser, Depends(get_api_user)],
) -> dict[str, Any]:
    await _gate_rate_limit(request, user)
    t0 = time.perf_counter()
    raw = await request.body()
    rows = [(r.mid(), r.outcome) for r in body.predictions]
    metrics = score_prediction_rows(rows)
    cost = 0.5
    response.headers["X-Theseus-Cost-Units"] = str(cost)
    _attach_version_headers(response)
    append_audit(
        api_key_label=user.label,
        sandbox_tenant_id=user.sandbox_tenant_id,
        route=request.url.path,
        request_sha256=body_fingerprint(raw),
        latency_ms=(time.perf_counter() - t0) * 1000,
        cost_units=cost,
        ok=True,
        status_code=200,
    )
    return {
        "metrics": metrics,
        "sandbox_tenant_id": user.sandbox_tenant_id,
        "llm_used": False,
    }


@app.post(f"{_API_PREFIX}/replay", tags=["replay"])
async def replay_stub(
    request: Request,
    response: Response,
    body: ReplayBody,
    user: Annotated[ApiKeyUser, Depends(get_api_user)],
) -> dict[str, Any]:
    await _gate_rate_limit(request, user)
    t0 = time.perf_counter()
    raw = await request.body()
    cost = 0.0
    response.headers["X-Theseus-Cost-Units"] = str(cost)
    _attach_version_headers(response)
    append_audit(
        api_key_label=user.label,
        sandbox_tenant_id=user.sandbox_tenant_id,
        route=request.url.path,
        request_sha256=body_fingerprint(raw),
        latency_ms=(time.perf_counter() - t0) * 1000,
        cost_units=cost,
        ok=True,
        status_code=200,
    )
    return {
        "as_of": body.as_of,
        "conclusions": [],
        "warnings": [
            "v1 replay endpoint is a stub: full temporal replay requires the Noosphere store and graph; "
            "run `python -m noosphere as-of … synthesize` locally for dry-run parity.",
        ],
        "sandbox_tenant_id": user.sandbox_tenant_id,
        "corpus_note": body.corpus_note,
        "llm_used": False,
    }


@app.get(f"{_API_PREFIX}/methods/{{method_name}}", tags=["methods"])
async def method_note(
    request: Request,
    response: Response,
    method_name: str,
    user: Annotated[ApiKeyUser, Depends(get_api_user)],
) -> dict[str, Any]:
    await _gate_rate_limit(request, user)
    t0 = time.perf_counter()
    raw = b""
    safe = method_name.replace("/", "_").replace("..", "_")
    path = _REPO_ROOT / "docs" / "api-methods" / f"{safe}.md"
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown method: {method_name}")
    text = path.read_text(encoding="utf-8")
    cost = 0.0
    response.headers["X-Theseus-Cost-Units"] = str(cost)
    _attach_version_headers(response)
    append_audit(
        api_key_label=user.label,
        sandbox_tenant_id=user.sandbox_tenant_id,
        route=request.url.path,
        request_sha256=body_fingerprint(raw),
        latency_ms=(time.perf_counter() - t0) * 1000,
        cost_units=cost,
        ok=True,
        status_code=200,
    )
    return {
        "method": method_name,
        "markdown": text,
        "sandbox_tenant_id": user.sandbox_tenant_id,
        "llm_used": False,
    }


@app.post(f"{_API_PREFIX}/register", tags=["register"])
async def register_stub() -> JSONResponse:
    """Self-service keys: not enabled in this skeleton (contact operator)."""
    p = Problem(
        type="https://theseus.local/problems/not-implemented",
        title="Not implemented",
        status=501,
        detail="Researcher self-service signup is not wired in this build. Contact the Theseus operators for a sandbox API key.",
    )
    return _problem_response(p)
