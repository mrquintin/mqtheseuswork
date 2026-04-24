# Dialectic

Dialectic is a live conversation analyzer. It listens to a discussion while it is happening, transcribes it, decomposes the transcript into claims, and surfaces contradictions, topic drift, and argumentative structure on a dashboard so that the people in the room can see the shape of what they are saying as they say it.

## What is inside

```
dialectic/
├── run.py              Entry point (launches the PyQt6 app)
├── requirements.txt
└── dialectic/
    ├── __main__.py
    ├── audio.py        sounddevice capture, VAD segmentation, ring buffer
    ├── transcriber.py  faster-whisper streaming transcription
    ├── analyzer.py     claim extraction, NLI contradiction scoring, topic tracking
    ├── interlocutor.py SP09 — consent-gated live prompts (contradiction / open thread / prediction)
    ├── tts_sidecar.py  optional local TTS (pyttsx3 / macOS say) behind DIALECTIC_TTS=1
    ├── dashboard.py    PyQt6 UI — live transcript, claim graph, contradiction panel
    └── config.py       Device, model, and threshold settings
```

## How it works

`audio.py` opens a microphone stream, runs voice-activity detection to cut the audio into speech segments, and pushes those segments into a thread-safe queue. `transcriber.py` consumes the queue with `faster-whisper` (CTranslate2-backed) and emits partial and final transcript tokens. `analyzer.py` takes finalized utterances, extracts claims (simple discourse-level segmentation with speaker attribution), embeds them with sentence-transformers MiniLM, tracks topic clusters, and runs a DeBERTa-v3 NLI head pairwise across recent claims to detect contradictions above a configurable threshold. `dashboard.py` renders all of this as a Qt interface with three panes — running transcript, live claim graph, and contradiction alerts.

The design goal is low latency (< 2s from speech to claim appearance) on a laptop GPU or Apple Silicon.

**Live interlocutor (SP09):** the main dashboard can surface short, third-person **Theseus** prompts when participants opt in per session. Modes range from silent (default) through passive overlay, conversational (+ optional TTS after a pause), and tutor (higher rate, requires an explicit acknowledgment). Every candidate passes a conservative quality gate and a per-session budget; interventions and drops are logged to JSONL with a `*_reflection.json` bundle for post-session review in the Theseus Codex.

## Usage

```
pip install -r requirements.txt
python run.py --model small.en --device mps --save-session ./sessions/
```

Saved sessions are JSON Lines: one line per finalized claim with timestamp, speaker, text, embedding, and any contradictions found. These files are the native input format for Noosphere's ingester.

## Cloud auto-sync (optional)

When both of these env vars are set, Dialectic automatically POSTs the finalized transcript (and the reflection bundle, if SP09 is enabled) to the Theseus Codex's `/api/upload` endpoint after each session stops:

```
export DIALECTIC_CLOUD_URL="https://theseus-codex.vercel.app"
export DIALECTIC_CLOUD_API_KEY="tcx_<prefix>_<secret>"    # mint at /settings/api-keys
```

Unset either to disable. Audio `.wav` files are **not** auto-uploaded — the transcript is the analytical payload, audio stays local as provenance. Upload failures are logged but never block the UI.

## Pairing with Noosphere

A Dialectic session file can be fed directly into the Noosphere engine:

```
python -m noosphere ingest --source dialectic --path ./sessions/2026-04-14.jsonl
python -m noosphere synthesize
```
