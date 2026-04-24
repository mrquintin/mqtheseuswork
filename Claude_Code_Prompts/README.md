# Round 8 — Binary-upload ingest fix + Dialectic voice recording

11 prompts, two waves.

## Why this round exists

A founder uploaded `The Purpose of The School: Theseus Discussion April 18, 2026.m4a` (194.8 MB) to the Codex and got:

> `Local ingest-from-codex failed: Upload c6b593815bac27aee838d9035 has no textContent. Binary (audio/PDF) uploads aren't supported by this command yet — use the Codex's Supabase Storage flow + a separate transcript command when that's wired up.`

Wave 1 fixes that specific failure and hardens the ingest pipeline against the whole class of "binary file with no pre-extracted text" errors. Wave 2 adds a first-class voice-recording path inside Dialectic so founders don't have to think about upload formats at all — they press Record, speak, press Stop, and a titled, trimmed, transcribed session lands in the Codex.

## Two waves

### Wave 1 — Fix the bug, harden the ingest (prompts 01–05)

| # | File | Target | Summary |
|---|------|--------|---------|
| 01 | `01_ingest_mime_dispatcher.txt` | `noosphere/extractors/` | MIME-dispatched extraction; text extractor + audio/PDF stubs |
| 02 | `02_ingest_audio_transcription.txt` | `noosphere/extractors/audio_extractor.py` | faster-whisper primary, OpenAI Whisper fallback for chunking > 25 MB |
| 03 | `03_ingest_pdf_extraction.txt` | `noosphere/extractors/pdf_extractor.py` | pypdf primary, optional ocrmypdf fallback for scanned PDFs |
| 04 | `04_ingest_processing_state_ui.txt` | `theseus-codex/src/` | Dashboard status pulse, error detail, retry button |
| 05 | `05_ingest_tests_and_smoke.txt` | `noosphere/tests/` | Regression for the m4a, MIME matrix, status-transition assert, gated real-whisper smoke |

Dependencies within Wave 1:

```
01 (dispatcher skeleton)
 ├── 02 (audio extractor fills stub)  ─┐
 ├── 03 (pdf extractor fills stub)     ├─→ 04 (UI surfaces the new statuses) ─→ 05 (tests)
 └── (01 also adds Upload.errorMessage)┘
```

### Wave 2 — Dialectic voice recording (prompts 06–11)

| # | File | Target | Summary |
|---|------|--------|---------|
| 06 | `06_dialectic_record_session_ui.txt` | `dialectic/recording_modal.py` + `recording_pipeline.py` | Record button + modal; pipeline with 4 stubbed stages |
| 07 | `07_dialectic_batch_transcription.txt` | `dialectic/batch_transcriber.py` | Post-recording faster-whisper with a Theseus-biased initial_prompt |
| 08 | `08_dialectic_auto_trim_vad.txt` | `dialectic/auto_trim.py` | Silero VAD hysteresis + crossfade concat |
| 09 | `09_dialectic_auto_title.txt` | `dialectic/auto_title.py` | Claude Haiku title generation with deterministic fallback |
| 10 | `10_dialectic_auto_upload.txt` | `dialectic/codex_upload.py` + Codex API | Prepare → signed PUT → finalize + offline queue |
| 11 | `11_e2e_voice_to_noosphere.txt` | `tests/e2e/` | Dialectic → Codex → Noosphere e2e + five invariants |

Dependencies within Wave 2:

```
06 (pipeline scaffold + stubs)
 ├── 07 (transcribe stage)
 ├── 08 (trim stage)           ─┐
 ├── 09 (title stage; needs 07)  ├─→ 10 (upload; needs trimmed audio, transcript, title) ─→ 11 (e2e)
 └─────────────────────────────┘
```

## Execution order

Wave 1 first, then Wave 2. Wave 2's upload path pre-attaches a transcript so it does not strictly require Wave 1, but running them out of order leaves the direct-m4a-upload bug open between shipping Wave 2 and shipping Wave 1. Wave 1 is the canary; ship it first.

Inside each wave, the prompts are numbered for sequential execution. The `run_prompts.sh` script runs them in order with `--wave 1` / `--wave 2` / no flag for all of them.

## Design invariants enforced by prompt 11

1. Pipeline stages run in order: `trim → transcribe → title → upload`.
2. The upload is always on the trimmed .wav, never the raw capture.
3. The title is never empty or `None`. The deterministic fallback is always available.
4. Upload failure queues the recording for retry; the user's audio is never lost to a flaky connection.
5. `textContent` sent to the Codex is byte-identical to the transcript Dialectic generated.

## Secrets referenced

- `OPENAI_API_KEY` — optional; used by the OpenAI Whisper fallback for files > 25 MB when `faster-whisper` is unavailable.
- `ANTHROPIC_API_KEY` — used by `auto_title.py` (prompt 09). If missing, title falls back to the deterministic format.
- `DIALECTIC_CLOUD_URL`, `DIALECTIC_CLOUD_API_KEY` — the Codex endpoint + API key Dialectic uploads to. Already in place from prior rounds.
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_AUDIO_BUCKET` — already configured for the Codex's audio upload path.

## Post-authoring audit notes

Two places where this round deliberately leaves surface area for a later iteration:

- **Trimming is acoustic, not semantic.** "Auto-trim to relevant content" is interpreted as silence + dead-air removal. Topic-drift trimming needs an LLM pass and is out of scope.
- **Title generation is single-shot.** If a founder disagrees with the generated title, they rename it from the dashboard. There is no retry-from-UI or A/B title option; the deterministic fallback is the only non-LLM path.

Both are honest choices with ops upside (deterministic, auditable) and a clear follow-up path (add `semantic_trim_prompt.md` + a second LLM stage) if a future session calls for it.
