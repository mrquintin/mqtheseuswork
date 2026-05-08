import type { Metadata } from "next";
import Link from "next/link";

import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";

export const metadata: Metadata = {
  title: "Methodology · five-criterion rubric",
  description:
    "The five working criteria the firm uses to score methods: Progressivity, Severity, Aim-Method Fit, Compressibility, Domain Sensitivity.",
};

type Criterion = {
  id: string;
  title: string;
  question: string;
  body: string;
  rubric: string[];
};

const CRITERIA: Criterion[] = [
  {
    id: "progressivity",
    title: "1. Progressivity",
    question:
      "Did the analysis produce a prediction, implication, or decision rule that can later be checked?",
    body:
      "A method is more useful when it generates claims that could have been wrong in observable ways. A method that only explains what is already known may be descriptively interesting, but it is weak as a guide to future action.",
    rubric: [
      "0.00 — No forecasts, no check-back date, no decision-rule phrases.",
      "0.40 — At least one decision-rule phrase, but no forecast or check-back.",
      "0.65 — Has check-back date or one forecast.",
      "0.85 — Has check-back date AND one forecast, OR ≥2 forecasts.",
      "1.00 — Has check-back date, ≥2 forecasts, AND a decision-rule phrase.",
    ],
  },
  {
    id: "severity",
    title: "2. Severity",
    question:
      "Would the procedure that produced this conclusion have caught the claim if it were false?",
    body:
      "A test is severe when it would probably have exposed the claim's weakness if the claim were false. Confirmation is cheap if the procedure would have passed many different claims. The Severity sub-score combines a deterministic floor (failure-modes recorded, dissent claims), an LLM judge, and a multiplicative drift penalty when the linked method is currently flagged.",
    rubric: [
      "Deterministic floor: min(1.0, 0.15·|failure_modes| + 0.10·|dissent|).",
      "Final = max(deterministic_floor, llm_judge_score).",
      "Hard cap at 0.35 if zero failure modes AND zero dissent.",
      "Track-record ceiling applies when calibration is thin or poor.",
      "Drift penalty (multiplicative): OK 1.00 · WARN 0.85 · ESCALATE 0.65.",
    ],
  },
  {
    id: "aim-method-fit",
    title: "3. Aim-Method Fit",
    question:
      "Is the method actually capable of answering the question being asked?",
    body:
      "A strong valuation screen is not automatically a strong product thesis. A useful education argument is not automatically a useful capital-allocation rule. The judge compares the question shape (valuation, design, prediction, description) to the method shape, with a deterministic guard that subtracts 0.10 when the topic root is missing from the declared transfer targets.",
    rubric: [
      "LLM returns a value in [0, 1].",
      "Guard: −0.10 when topic_hint is non-empty AND no transfer_target contains its root.",
    ],
  },
  {
    id: "compressibility",
    title: "4. Compressibility",
    question:
      "How many independent assumptions must hold for the conclusion to survive?",
    body:
      "An explanation that requires many special exceptions is less likely to transfer well. This does not mean simple claims are always true; it means additional assumptions should be visible and priced as risk.",
    rubric: [
      "Base = 1.0 / (1.0 + max(0, n − 1)·0.25), where n = |assumptions|.",
      "0 or 1 → 1.0 · 2 → 0.80 · 3 → 0.67 · 4 → 0.57 · 5 → 0.50.",
      "LLM may demote decorative assumptions, but effective n cannot fall below 1.",
    ],
  },
  {
    id: "domain-sensitivity",
    title: "5. Domain Sensitivity",
    question:
      "Where should this method stop being trusted, and is the current conclusion inside or outside that domain?",
    body:
      "No reasoning method is reliable everywhere. Domain Sensitivity is the multiplicative gate on the composite — a method that does not fit the domain cannot be redeemed by being severe and progressive elsewhere.",
    rubric: [
      "LLM returns a value in [0, 1].",
      "Floor: 0.10 when no failure modes are recorded (no declared boundary).",
      "Backfill default: 0.5 (uncertain, not failed) when no LLM is available.",
    ],
  },
];

const FORMULA =
  "domain_sensitivity * mean(progressivity, severity, aim_method_fit, compressibility)";

export default async function MethodologyCriteriaPage() {
  const founder = await getFounder();
  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main className="public-container public-methodology-page">
        <Link
          href="/methodology"
          className="public-muted"
          style={{ fontSize: "0.75rem" }}
        >
          ← Methodology
        </Link>
        <h1 className="public-title" style={{ marginTop: "0.5rem" }}>
          Five-criterion rubric
        </h1>
        <p className="public-muted public-lede">
          The exact rubric attached to every conclusion that has at least
          one methodology profile. The five sub-scores are the working
          criteria from the meta-method, lifted from prose into something
          the firm can compute, audit, and revise. The rubric below is the
          checked-against-code source of truth — the operator process gate
          fails if this page drifts from the running scorer.
        </p>

        <section className="public-section">
          <h2>Composite formula</h2>
          <pre
            className="mono"
            style={{
              padding: "0.85rem 1rem",
              background: "rgba(212, 160, 23, 0.08)",
              border: "1px solid var(--public-rule, #ddd)",
              borderRadius: 2,
              fontSize: "0.82rem",
              overflowX: "auto",
              margin: 0,
            }}
          >
            {FORMULA}
          </pre>
          <p className="public-muted" style={{ marginTop: "0.75rem", fontSize: "0.85rem" }}>
            Domain Sensitivity is the gate, not a weighted addend: a domain
            score of 0.5 caps the composite at 0.5 even when the other
            four are 1.0.
          </p>
        </section>

        <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {CRITERIA.map((c) => (
            <li
              key={c.id}
              id={c.id}
              className="public-card public-method-card"
              style={{ padding: "1.1rem 1.25rem", marginBottom: "1rem" }}
            >
              <h2 style={{ marginTop: 0 }}>{c.title}</h2>
              <p
                className="mono public-muted"
                style={{
                  fontSize: "0.65rem",
                  letterSpacing: "0.18em",
                  textTransform: "uppercase",
                  marginTop: "-0.25rem",
                  marginBottom: "0.6rem",
                }}
              >
                Operational question
              </p>
              <p style={{ marginTop: 0, fontStyle: "italic" }}>{c.question}</p>
              <p>{c.body}</p>
              <h3
                className="mono public-muted"
                style={{
                  fontSize: "0.65rem",
                  letterSpacing: "0.18em",
                  textTransform: "uppercase",
                  marginTop: "0.85rem",
                  marginBottom: "0.4rem",
                }}
              >
                Rubric
              </h3>
              <ul style={{ margin: 0, paddingLeft: "1.1rem" }}>
                {c.rubric.map((line, i) => (
                  <li key={i} style={{ fontSize: "0.9rem", lineHeight: 1.5 }}>
                    {line}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>

        <section className="public-section">
          <h2>Public display rule</h2>
          <p>
            The composite MQS is rendered publicly only when (1) the
            conclusion is published and (2) the score is fresher than the
            conclusion's last edit. A stale MQS is never shown.
          </p>
        </section>
      </main>
    </>
  );
}
