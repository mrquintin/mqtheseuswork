# Release checklist — voice recording + binary ingest fix

Before tagging a release that includes Waves 1 + 2:

## Wave 1 — ingest pipeline fix

- [ ] `ingest-from-codex` on the April 18 m4a (upload id `c6b593815bac27aee838d9035`)
      completes and writes Conclusions. Confirm `extractionMethod=faster-whisper`
      appears in the Codex dashboard for that upload.
- [ ] `ingest-from-codex` on a digital PDF completes; `extractionMethod=pypdf`.
- [ ] `ingest-from-codex` on a scanned PDF completes via the OCR fallback.
- [ ] The Codex dashboard shows a pulsing `extracting` status badge while a
      large file is being processed, then flips to `ingested` on success.
- [ ] An intentionally-failed upload (e.g. a `.zip`) surfaces a readable
      `errorMessage` with either `unsupported_mime:` or `extraction_failed:`
      prefix, and the Retry button re-runs the pipeline.
- [ ] `pytest -q noosphere/tests/test_extractors_*.py` is green on main.

## Wave 2 — Dialectic voice recording

- [ ] The Record button in the toolbar opens the modal. All four stage rows
      (trim / transcribe / title / upload) are visible before Stop is pressed.
- [ ] A 30-second recording lands as an Upload in the Codex with `textContent`
      populated by Dialectic's transcript. Confirm ingest-from-codex does NOT
      re-run Whisper on that row (the process log should show
      `extraction method=passthrough` rather than `faster-whisper`).
- [ ] Auto-title is specific, not `"Dialectic session — YYYY-MM-DD …"`. If
      every recording lands on the fallback, check `ANTHROPIC_API_KEY` in the
      environment and the Haiku model name in `AutoTitleConfig`.
- [ ] Trimmed duration is strictly less than recorded duration on at least one
      recording that contained leading/trailing silence. (Equal durations on
      continuous speech are fine.)
- [ ] Offline recording: turn wifi off, record a short clip, press Stop. The
      upload stage should emit `stage_failed("upload", …)` with a message
      containing "Retry pending uploads". A new line appears in
      `~/Library/Application Support/Theseus/Dialectic/pending_uploads.jsonl`
      (macOS) / the XDG-appropriate equivalent elsewhere. Turn wifi on, use
      "Retry pending uploads" from the menu — the upload goes through and the
      queue file is empty.
- [ ] `pytest -q dialectic/tests/` is green on main.

## Cross-cut

- [ ] `pytest -q tests/e2e/ -m e2e` is green. This runs
      `test_dialectic_to_noosphere.py` (full happy path, record → ingest) and
      `test_m4a_regression.py` (the April 2026 canary).
- [ ] `DIALECTIC_TEST_REAL_WHISPER=1 pytest -q dialectic/tests/test_modal_smoke.py`
      passes on the CI hardware; run it once before cutting a release to
      catch model-compat drift.
- [ ] `NOOSPHERE_E2E_SMOKE=1 pytest -q noosphere/tests/e2e/test_ingest_audio_smoke.py`
      passes against a real whisper install.
- [ ] `Claude_Code_Prompts/RELEASE_CHECKLIST.md` is committed.
- [ ] The five pipeline invariants in
      `dialectic/tests/test_pipeline_invariants.py` are all green and none
      are skipping. A skipped invariant is a coverage regression, not a pass.
