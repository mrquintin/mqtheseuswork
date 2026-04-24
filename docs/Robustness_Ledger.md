# Theseus / Noosphere — Robustness Ledger (SP08)

**Version:** 1 (source document; regenerate PDF via `scripts/build_robustness_ledger_pdf.sh` when Pandoc is installed).  
**Attack suite:** `noosphere.redteam.ATTACK_SUITE_VERSION` (run `python -m noosphere redteam taxonomy`).

This ledger records **attack classes**, **who can mount them**, **what breaks if they succeed**, and **what we actually shipped vs accepted residual risk**. Hiding unmitigated surfaces is forbidden; credibility comes from specificity.

---

## 1. Ingestion — prompt injection in transcripts

- **Threat model:** Anyone who can place text into a transcript, JSONL session, or VTT cue (malicious guest, compromised upload path).
- **Worst case:** Extractors, classifiers, or downstream prompts inherit attacker instructions and systematically mis-rank claims.
- **Mitigations shipped:** Regex/heuristic scanner + quarantine flags on `Claim` (`ingestion_quarantine`, `ingestion_guard_signals`); VTT chunks carry the same signals in `Chunk.metadata`; embeddings use Unicode-normalized text before encoding (`normalize_for_embedding`).
- **Not mitigated (residual):** Sophisticated paraphrases and novel jailbreak tropes not matching heuristics; multilingual obfuscation. Planned: fine-tuned classifier + human review queue metrics.
- **Code:** `noosphere/mitigations/ingestion_guard.py`, `ingest_artifacts.py`, `ingester.py`.

## 2. Ingestion — polluted / hidden PDF text

- **Threat model:** PDF publisher with invisible text layers contradicting visible pages.
- **Worst case:** Silent claim pollution in literature-backed workflows.
- **Mitigations shipped:** None automated in-engine today.
- **Residual:** **Accepted risk** until PDF pipeline adds rendering cross-checks; treat untrusted PDFs like untrusted code.

## 3. Ingestion — metadata spoofing

- **Threat model:** Uploader controls filenames, markdown front-matter, or loose JSON fields.
- **Worst case:** Wrong dates/authorship bias temporal replay and attribution.
- **Mitigations shipped:** Policy hooks only (`Artifact` provenance fields); dialectic `effective_at` requires explicit human attestation flag before future ingestion wires it through (`dialectic_may_set_effective_at`).
- **Residual:** **Planned** cryptographic signing of artifact bundles + operator verification.

## 4. Embedding — adversarial Unicode / homoglyph pressure

- **Threat model:** Author inserts zero-width joiners to perturb vectors while preserving human reading.
- **Worst case:** Neighborhood retrieval and geometry layers drift for targeted claims.
- **Mitigations shipped:** Strip + NFC normalize before embedding; quarantine when zero-width density crosses a low threshold.
- **Residual:** Subtle homoglyphs without ZW characters; requires model-level robustness research.

## 5. Coherence — NLI blind spots

- **Threat model:** Researcher who crafts entailment-resistant pairs.
- **Worst case:** Incorrect COHERE/CONTRADICT vs human adjudication.
- **Mitigations shipped:** Gold regression tests (`noosphere/tests/test_coherence_eval.py`), stub/real NLI swap under configuration.
- **Residual:** **Accepted risk** — NLI is a heuristic; we version-pin and re-evaluate on upgrades.

## 6. Coherence — LLM judge social engineering

- **Threat model:** Model hallucinates prior-layer numbers to justify an override.
- **Worst case:** Judge flips aggregate verdict without real grounding.
- **Mitigations shipped:** Structured JSON schema + citation phrase checks (existing) **plus** numeric cross-check that every `cited_prior_score.value` matches automation within tolerance (`judge_cited_scores_match_prior`); mismatch rejects the judge packet.
- **Residual:** Arms-race shaped; judge may still argue in prose while matching numbers — mitigated as “managed,” not “solved.”

## 7. Calibration — interval gaming

- **Threat model:** Many ultra-narrow probability intervals to game headline scores.
- **Mitigations shipped:** `calibration_rows_look_gamed` statistical flag for batch review.
- **Residual:** Small-N honest narrow forecasts; combine with human audit before blocking writes in production.

## 8. Calibration — gold-set poisoning

- **Threat model:** Insider mislabels gold rows.
- **Mitigations shipped:** Canonical fingerprint helper for signed bundles (`gold_bundle_canonical_fingerprint`); operational requirement is human approval (process, not automatic block).
- **Residual:** **Accepted risk** without organizational controls.

## 9. Citation — fabricated Voice quotes

- **Threat model:** Editor pastes quote not present in corpus.
- **Mitigations shipped:** Token-overlap gate `fuzzy_quote_plausible` (low recall, cheap filter) + existing shadow citation policy for Voice writes.
- **Residual:** Paraphrases that share tokens but distort meaning — still needs human reading.

## 10. Temporal — backdating

- **Threat model:** JSONL producer asserts historical `effective_at` without evidence.
- **Mitigations shipped:** Policy function `dialectic_may_set_effective_at` — only explicit `effective_at_human_attested: true` may unlock future ingestion of back-dated rows.
- **Residual:** Clock skew and trusted timestamp sources — operational PKI/TSA out of scope here.

## 11. Multi-tenant — cache or aggregate leakage

- **Threat model:** Shared embedding cache or observability aggregates deanonymize tenants.
- **Mitigations shipped:** Structured audit hook `log_cross_tenant_boundary_check` for boundary instrumentation.
- **Residual:** **Planned** per-tenant caches, RLS, DP noise on aggregates — see `deploy/sql/postgres_rls_example.sql` and Operations Manual tenancy notes.

---

## Release discipline

1. On every coherence, ingestion, embedding, or calibration change: run `python -m noosphere redteam run` in CI.
2. Update this Markdown when attack status changes; mint PDF for external partners who require a static artifact.
3. File tickets for any **accepted_risk** item you intend to graduate to **shipped**.
