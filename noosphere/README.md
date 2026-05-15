# Noosphere — The Brain of the Firm

A computational system for extracting, representing, and reasoning from the intellectual capital of Theseus's founders, built on the Embedding Geometry Conjecture and the 6-layer Coherence Architecture.

## Architecture

The pipeline is unchanged from Round 17, but Round 19 grouped the
top-level modules into a layered hierarchy. The dataflow now reads:

```
Weekly 4-Hour Podcast Transcript
            │
            ▼
┌──────────────────────────┐
│   TRANSCRIPT INGESTER    │  Segment → Diarize → Extract claims
│   (ingester.py)          │  Output: Atomic propositions with speaker attribution
└───────────┬──────────────┘
            │
            ▼
┌──────────────────────────┐
│   PRINCIPLE EXTRACTOR    │  Cluster claims → Identify principles → Rank by conviction
│   (extractor.py)         │  Output: Candidate principles with evidence chains
└───────────┬──────────────┘
            │
            ▼
┌──────────────────────────┐
│   COHERENCE ENGINE       │  6-layer validation (consistency, argumentation,
│   (coherence.py)         │  probabilistic, embedding geometry, information theory, LLM)
│                          │  Output: Coherence scores, contradiction flags
└───────────┬──────────────┘
            │
            ▼
┌──────────────────────────┐
│   ONTOLOGICAL GRAPH      │  Principles as nodes, relationships as edges
│   (ontology.py)          │  Embedding-space positions, temporal metadata
│                          │  Output: Navigable knowledge graph
└───────────┬──────────────┘
            │
            ▼
┌──────────────────────────┐
│   INFERENCE ENGINE       │  Query → Retrieve relevant principles → Reason
│   (inference.py)         │  from first principles → Generate aligned analysis
│                          │  Output: Firm-aligned predictions and recommendations
└───────────┬──────────────┘
            │
            ▼
┌──────────────────────────┐
│   TEMPORAL TRACKER       │  Track principle emergence, drift, strengthening
│   (temporal.py)          │  Detect ideological evolution across episodes
│                          │  Output: Evolution reports, conviction trajectories
└──────────────────────────┘
```

### Module layering (Round 19)

```
                 ┌───────────────────────────────┐
                 │   noosphere.cli   (leaf)      │   Typer + Click, runbook entry
                 └──────────────┬────────────────┘
                                │
        ┌───────────────┬───────┴────────┬──────────────┬──────────────┐
        ▼               ▼                ▼              ▼              ▼
 ┌─────────────┐  ┌─────────────┐  ┌────────────┐  ┌───────────┐  ┌──────────┐
 │ benchmarks  │  │ currents /  │  │ forecasts  │  │ literature│  │  docgen  │
 └──────┬──────┘  │ dialectic   │  └─────┬──────┘  └─────┬─────┘  └────┬─────┘
        │         └──────┬──────┘        │               │             │
        └────────────────┴──────┬────────┴───────────────┴─────────────┘
                                ▼
                ┌───────────────────────────────┐
                │   noosphere.inquiry           │   coherence, evaluation,
                │   noosphere.temporal          │   peer_review, redteam, mitigations
                └──────────────┬────────────────┘
                                │
                ┌───────────────▼────────────────┐
                │   noosphere.methods            │   registry, composition, every method
                └──────────────┬────────────────┘
                                │
                ┌───────────────▼────────────────┐
                │   noosphere.io                 │   storage_client, codex_bridge,
                │                                │   ingester, ingest_artifacts
                └──────────────┬────────────────┘
                                │
                ┌───────────────▼────────────────┐
                │   noosphere.core   (leaf)     │   models, store, ledger,
                │                                │   orchestrator, observability,
                │                                │   ids, config
                └────────────────────────────────┘
```

Every facade package (``core``, ``inquiry``, ``io``, ``cli``) re-exports
from the existing flat modules so this rollout is non-breaking. The full
contract is documented in
[``docs/architecture/Noosphere_Module_Map.md``](../docs/architecture/Noosphere_Module_Map.md)
and enforced in CI by ``lint-imports --config noosphere/.import-linter``;
``noosphere/tests/test_module_hierarchy.py`` re-runs the same check from
pytest.

Preferred import paths going forward:

```python
from noosphere.core import Store, OntologyGraph, NoosphereOrchestrator, get_logger
from noosphere.inquiry import coherence, evaluation, peer_review
from noosphere.io import codex_bridge, storage_client
from noosphere.cli import app as typer_app, cli as click_cli
```

Legacy paths (``noosphere.store``, ``noosphere.coherence``, …) continue
to work; they become deprecation shims when the implementations are
physically relocated in a follow-up prompt.

## Key Design Decisions

1. **Atomic Propositions, Not Summaries.** The unit of analysis is the individual claim, not a paragraph summary. Summaries destroy the logical structure needed for coherence analysis.

2. **Embeddings + Difference Vectors.** Raw cosine similarity is insufficient (the Cosine Paradox). We use difference vector sparsity and learned contradiction directions per the validated Embedding Geometry Conjecture.

3. **Graph, Not Vector Store.** A vector store treats every entry as independent. A graph preserves the logical relationships (supports, contradicts, refines, instantiates) that make the coherence engine possible.

4. **Conviction Weighting.** Not all claims are equal. Frequency, emphasis, argumentative centrality, and speaker authority all contribute to a principle's weight in the graph.

5. **Temporal Indexing.** Every node carries a timestamp. The same principle stated in episode 1 and episode 50 has its conviction score updated, not duplicated.

## Installing with audio support

Audio uploads (``.m4a``, ``.mp3``, ``.wav``, etc.) are transcribed
locally via `faster-whisper` (CTranslate2 backend) by default, with an
OpenAI Whisper API fallback when the local model is unavailable.

```bash
# text + PDF only — the lean default
pip install -e .

# add local audio transcription (faster-whisper + mutagen)
pip install -e ".[audio]"

# add the cloud fallback too
pip install -e ".[audio,whisper-openai]"
```

Override the local model via `NOOSPHERE_WHISPER_MODEL` (default
`small.en`). Force the cloud path — e.g. to debug Whisper API parity —
with `NOOSPHERE_FORCE_OPENAI_WHISPER=1` (requires `OPENAI_API_KEY`).

## Installing with PDF support

Digitally produced PDFs (the overwhelming majority of what founders
upload — papers, chapters, Otter.ai re-exports) are handled by
`pypdf`, a pure-Python parser with no system dependencies:

```bash
pip install -e ".[pdf]"
```

Scanned-image PDFs have to be run through OCR. That path is gated on
an env flag because OCR requires `ocrmypdf` (which in turn requires
tesseract + ghostscript) and can take ~10× longer than a pypdf pass:

```bash
# macOS
brew install ocrmypdf
# Debian/Ubuntu
sudo apt install ocrmypdf

export NOOSPHERE_ENABLE_OCR=1
```

Without the flag, scanned PDFs fail fast with an `ExtractionFailed`
message telling the operator how to enable OCR or supply a
pre-extracted `.txt` instead.

## Usage

```bash
cd noosphere
pip install -r requirements.txt

# Ingest a transcript
python -m noosphere.cli ingest transcript.txt --episode 1 --date 2026-01-05

# View the principle graph
python -m noosphere.cli graph --format json

# Query the inference engine
python -m noosphere.cli ask "Should we invest in companies with network effects?"

# Run coherence analysis
python -m noosphere.cli coherence --report

# View temporal evolution
python -m noosphere.cli evolution --principle "first principles thinking"
```

## Dependencies

- sentence-transformers (SBERT embeddings)
- numpy, scipy, scikit-learn (geometric analysis)
- networkx (knowledge graph)
- anthropic (Claude API for extraction and inference)
- spacy (NLP pipeline)
- z3-solver (formal consistency checking)
