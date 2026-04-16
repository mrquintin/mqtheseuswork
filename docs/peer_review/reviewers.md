# Peer Review Roles

| Role | Prior | Known Blindspots | Tools |
|------|-------|-------------------|-------|
| methodological | Was the right method, at a defensible version, applied to the right input? | May over-penalize novel methods; cannot assess method application quality | `methods.REGISTRY`, method calibration reports |
| evidential | Does each cited chunk actually support what the conclusion claims? | Cannot verify evidence outside corpus; NLI may miss domain patterns | retrieval + `nli_scorer` |
| statistical | Is the uncertainty honestly quantified? Is sample size sufficient? | Frequentist thresholds may not suit Bayesian workflows; cannot detect p-hacking | calibration data, evaluation metrics |
| adv_literature | Does external literature contain counter-evidence not engaged with? | Limited to indexed literature; cannot assess counter-evidence quality | `literature.external_claim_match`, external battery data |
| replication | Can I re-derive this conclusion from the stated inputs alone? | Cannot detect semantic equivalence; single-attempt replication | method registry invocation, cascade traversal |
| rhetorical | Is the argument rhetorically clean or does it smuggle moves past the reader? | Keyword heuristics miss sophisticated maneuvers; may flag legitimate emphasis | LLM |
| humility | Are unresolved points and open questions faithfully surfaced? | May penalize well-supported confident conclusions; keyword detection limits | LLM + corpus retrieval |
