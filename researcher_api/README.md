# Theseus Researcher API (SP07)

Documented, rate-limited HTTP surface for **outside investigators**: claim extraction, coherence, embeddings, calibration scoring, and (stub) replay — on **researcher-supplied text only**. No access to firm tenants or internal stores.

## Run (development)

From the **monorepo root** (so `noosphere` is importable):

```bash
cd researcher_api
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export PYTHONPATH="$(pwd)/../noosphere${PYTHONPATH:+:$PYTHONPATH}"
export RESEARCHER_API_KEYS="demo:sandbox-demo:sk-demo-researcher-key-0001"
export THESEUS_GIT_SHA="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
uvicorn researcher_api.main:app --reload --host 0.0.0.0 --port 8088
```

- OpenAPI: http://127.0.0.1:8088/docs  
- Alternate Redoc: http://127.0.0.1:8088/redoc  

Send `X-API-Key: sk-demo-researcher-key-0001` on every request.

## Deploy

See `deploy/docker/researcher-api/Dockerfile`. The service is **separate** from the Theseus Codex.

## Policies & citation

- `docs/researcher-api/ACCEPTABLE_USE.md`  
- `docs/researcher-api/PRIVACY.md`  
- `docs/researcher-api/CITATION.bib` (Zenodo DOI placeholder until minted)
