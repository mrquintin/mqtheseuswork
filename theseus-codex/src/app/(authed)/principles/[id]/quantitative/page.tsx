import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { revalidatePath } from "next/cache";

import { getFounder } from "@/lib/auth";
import { getPrinciple } from "@/lib/principlesApi";
import {
  approveFormalisation,
  FormalisationInvariantError,
  getFormalisationForPrinciple,
  rejectFormalisation,
} from "@/lib/quantitativeFormalisationApi";
import type {
  DataSourceSpec,
  MetricSpec,
  StatisticalTestSpec,
} from "@/lib/quantitativeFormalisationApi";
import { requireTenantContext } from "@/lib/tenant";

export const dynamic = "force-dynamic";

type Params = { id: string };

/**
 * Founder triage page for the quantitative-formalisation spec layer.
 *
 * Workflow: the drafter (noosphere.quantitative.drafter) proposes one
 * formalisation per principle. This page shows the principle text and
 * the drafter's proposal side-by-side, with an edit pane and three
 * actions:
 *
 *   accept — founder approves (after optional edits). The
 *            invariant checks are enforced server-side too: APPROVED
 *            requires a non-empty null hypothesis and ≥1 metric/test.
 *   reject — drop the proposal with a recorded reason; status → RETIRED.
 *   edit   — implicit; the accept handler reads back the edited fields.
 *
 * The drafter may also have refused (`UNFORMALISABLE`); the page
 * shows the reason and offers reject-with-note as the canonical
 * close-out.
 */
export default async function PrincipleQuantitativePage({
  params,
}: {
  params: Promise<Params>;
}) {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login");
  const { id } = await params;
  const principle = await getPrinciple(tenant.organizationId, id);
  if (!principle) notFound();

  const formalisation = await getFormalisationForPrinciple(
    tenant.organizationId,
    id,
  );

  async function accept(formData: FormData) {
    "use server";
    const founder = await getFounder();
    if (!founder) redirect("/login");
    if (!formalisation) return;
    const nullHypothesis = String(formData.get("nullHypothesis") ?? "").trim();
    const decisionThresholdsRaw = String(
      formData.get("decisionThresholds") ?? "",
    );
    const decisionThresholds = decisionThresholdsRaw
      .split("\n")
      .map((t) => t.trim())
      .filter(Boolean);
    const metrics = parseTextareaJson<MetricSpec>(formData.get("metrics"));
    const tests = parseTextareaJson<StatisticalTestSpec>(formData.get("tests"));
    const dataSources = parseTextareaJson<DataSourceSpec>(
      formData.get("dataSources"),
    );
    try {
      await approveFormalisation(
        founder.organizationId,
        formalisation.id,
        founder.id,
        {
          nullHypothesis,
          metrics,
          tests,
          dataSources,
          decisionThresholds,
        },
      );
    } catch (e) {
      if (e instanceof FormalisationInvariantError) {
        // Surface inline; the page re-renders with current data.
        return;
      }
      throw e;
    }
    revalidatePath(`/principles/${id}/quantitative`);
    revalidatePath(`/principles/${id}`);
    revalidatePath(`/principles/${id}/triage`);
    redirect(`/principles/${id}/triage`);
  }

  async function reject(formData: FormData) {
    "use server";
    const founder = await getFounder();
    if (!founder) redirect("/login");
    if (!formalisation) return;
    const reason = String(formData.get("reason") ?? "").trim();
    await rejectFormalisation(
      founder.organizationId,
      formalisation.id,
      founder.id,
      reason,
    );
    revalidatePath(`/principles/${id}/quantitative`);
    redirect(`/principles/${id}/triage`);
  }

  return (
    <main
      style={{
        maxWidth: "960px",
        margin: "0 auto",
        padding: "2.5rem 2rem",
      }}
    >
      <p style={{ marginBottom: "1.25rem" }}>
        <Link
          href={`/principles/${id}/triage`}
          className="mono"
          style={{
            fontSize: "0.65rem",
            letterSpacing: "0.24em",
            textTransform: "uppercase",
            color: "var(--amber-dim)",
            textDecoration: "none",
          }}
        >
          ← back to triage
        </Link>
      </p>

      <header style={{ marginBottom: "1.5rem" }}>
        <h1
          style={{
            fontFamily: "'Cinzel', serif",
            color: "var(--amber)",
            letterSpacing: "0.1em",
            fontSize: "1.4rem",
            margin: 0,
          }}
        >
          Quantitative formalisation
        </h1>
        <p
          style={{
            fontFamily: "'EB Garamond', serif",
            fontSize: "1.1rem",
            marginTop: "0.6rem",
          }}
        >
          {principle.text}
        </p>
        <p
          className="mono"
          style={{
            marginTop: "0.5rem",
            fontSize: "0.6rem",
            letterSpacing: "0.22em",
            textTransform: "uppercase",
            color: "var(--parchment-dim)",
          }}
        >
          status · {formalisation?.status ?? "no draft"}
          {formalisation?.drafterModel
            ? ` · drafted by ${formalisation.drafterModel}`
            : ""}
        </p>
      </header>

      {!formalisation ? (
        <section className="portal-card" style={{ padding: "1.25rem 1.4rem" }}>
          <p>
            No drafter proposal yet. Run the quantitative-formalisation
            drafter against this principle (see
            <code> noosphere.quantitative.drafter </code>) and reload.
          </p>
        </section>
      ) : formalisation.status === "UNFORMALISABLE" ? (
        <section className="portal-card" style={{ padding: "1.25rem 1.4rem" }}>
          <h2
            className="mono"
            style={{
              fontSize: "0.7rem",
              letterSpacing: "0.22em",
              textTransform: "uppercase",
              color: "var(--ember, #c0392b)",
              margin: 0,
              marginBottom: "0.5rem",
            }}
          >
            Drafter refused
          </h2>
          <p style={{ marginBottom: "0.75rem" }}>
            <strong>Reason:</strong>{" "}
            {formalisation.unformalisableReason ?? "(no reason recorded)"}
          </p>
          <p style={{ color: "var(--parchment-dim)", marginBottom: "1rem" }}>
            Refusals are a first-class outcome — the drafter is not
            allowed to fabricate data sources. You can close this row
            (status → RETIRED) with a note, or rewrite the principle so
            it admits a metric and re-run the drafter.
          </p>
          <form action={reject} style={{ display: "flex", gap: "0.6rem" }}>
            <input
              type="text"
              name="reason"
              placeholder="Note (optional)"
              style={{
                flex: 1,
                padding: "0.5rem 0.75rem",
                background: "transparent",
                border: "1px solid var(--border)",
                color: "var(--parchment)",
              }}
            />
            <button
              type="submit"
              className="mono"
              style={{
                padding: "0.45rem 0.9rem",
                border: "1px solid var(--ember, #c0392b)",
                color: "var(--ember, #c0392b)",
                background: "transparent",
                fontSize: "0.6rem",
                letterSpacing: "0.22em",
                textTransform: "uppercase",
                cursor: "pointer",
              }}
            >
              Close (retire)
            </button>
          </form>
        </section>
      ) : (
        <>
          {formalisation.drafterNotes ? (
            <p
              style={{
                color: "var(--parchment-dim)",
                marginBottom: "1rem",
                fontStyle: "italic",
              }}
            >
              Drafter note: {formalisation.drafterNotes}
            </p>
          ) : null}

          <form
            action={accept}
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "1rem",
              marginBottom: "1rem",
            }}
          >
            <section
              className="portal-card"
              style={{ padding: "1.25rem 1.4rem" }}
            >
              <h2
                className="mono"
                style={{
                  fontSize: "0.7rem",
                  letterSpacing: "0.22em",
                  textTransform: "uppercase",
                  color: "var(--amber-dim)",
                  margin: 0,
                  marginBottom: "0.6rem",
                }}
              >
                Null hypothesis · what would be true if principle is FALSE
              </h2>
              <textarea
                name="nullHypothesis"
                required
                rows={2}
                defaultValue={formalisation.nullHypothesis}
                style={textareaStyle}
              />
            </section>

            <section
              className="portal-card"
              style={{ padding: "1.25rem 1.4rem" }}
            >
              <h2
                className="mono"
                style={{
                  fontSize: "0.7rem",
                  letterSpacing: "0.22em",
                  textTransform: "uppercase",
                  color: "var(--amber-dim)",
                  margin: 0,
                  marginBottom: "0.6rem",
                }}
              >
                Metrics (JSON list of {`{name, definition, unit, source_dataset, update_cadence}`})
              </h2>
              <textarea
                name="metrics"
                rows={Math.max(8, formalisation.metrics.length * 4)}
                defaultValue={JSON.stringify(formalisation.metrics, null, 2)}
                style={textareaStyle}
              />
            </section>

            <section
              className="portal-card"
              style={{ padding: "1.25rem 1.4rem" }}
            >
              <h2
                className="mono"
                style={{
                  fontSize: "0.7rem",
                  letterSpacing: "0.22em",
                  textTransform: "uppercase",
                  color: "var(--amber-dim)",
                  margin: 0,
                  marginBottom: "0.6rem",
                }}
              >
                Statistical tests (JSON list)
              </h2>
              <textarea
                name="tests"
                rows={Math.max(8, formalisation.tests.length * 4)}
                defaultValue={JSON.stringify(formalisation.tests, null, 2)}
                style={textareaStyle}
              />
            </section>

            <section
              className="portal-card"
              style={{ padding: "1.25rem 1.4rem" }}
            >
              <h2
                className="mono"
                style={{
                  fontSize: "0.7rem",
                  letterSpacing: "0.22em",
                  textTransform: "uppercase",
                  color: "var(--amber-dim)",
                  margin: 0,
                  marginBottom: "0.6rem",
                }}
              >
                Data sources (JSON list)
              </h2>
              <textarea
                name="dataSources"
                rows={Math.max(6, formalisation.dataSources.length * 4)}
                defaultValue={JSON.stringify(
                  formalisation.dataSources,
                  null,
                  2,
                )}
                style={textareaStyle}
              />
            </section>

            <section
              className="portal-card"
              style={{ padding: "1.25rem 1.4rem" }}
            >
              <h2
                className="mono"
                style={{
                  fontSize: "0.7rem",
                  letterSpacing: "0.22em",
                  textTransform: "uppercase",
                  color: "var(--amber-dim)",
                  margin: 0,
                  marginBottom: "0.6rem",
                }}
              >
                Decision thresholds · one per line
              </h2>
              <textarea
                name="decisionThresholds"
                rows={Math.max(4, formalisation.decisionThresholds.length + 1)}
                defaultValue={formalisation.decisionThresholds.join("\n")}
                style={textareaStyle}
                placeholder="if R^2 < 0.05 across 3 windows → principle weakens"
              />
            </section>

            <button
              type="submit"
              className="mono"
              style={{
                alignSelf: "flex-start",
                padding: "0.55rem 1.1rem",
                border: "1px solid var(--amber)",
                color: "var(--amber)",
                background: "transparent",
                fontSize: "0.65rem",
                letterSpacing: "0.22em",
                textTransform: "uppercase",
                cursor: "pointer",
              }}
            >
              Approve formalisation
            </button>
          </form>

          <section
            className="portal-card"
            style={{ padding: "1.25rem 1.4rem" }}
          >
            <h2
              className="mono"
              style={{
                fontSize: "0.7rem",
                letterSpacing: "0.22em",
                textTransform: "uppercase",
                color: "var(--amber-dim)",
                margin: 0,
                marginBottom: "0.6rem",
              }}
            >
              Reject this draft
            </h2>
            <form action={reject} style={{ display: "flex", gap: "0.6rem" }}>
              <input
                type="text"
                name="reason"
                placeholder="Why this draft is not acceptable"
                required
                style={{
                  flex: 1,
                  padding: "0.5rem 0.75rem",
                  background: "transparent",
                  border: "1px solid var(--border)",
                  color: "var(--parchment)",
                }}
              />
              <button
                type="submit"
                className="mono"
                style={{
                  padding: "0.45rem 0.9rem",
                  border: "1px solid var(--ember, #c0392b)",
                  color: "var(--ember, #c0392b)",
                  background: "transparent",
                  fontSize: "0.6rem",
                  letterSpacing: "0.22em",
                  textTransform: "uppercase",
                  cursor: "pointer",
                }}
              >
                Reject
              </button>
            </form>
          </section>
        </>
      )}
    </main>
  );
}

const textareaStyle: React.CSSProperties = {
  width: "100%",
  fontFamily: "'JetBrains Mono', ui-monospace, monospace",
  fontSize: "0.85rem",
  padding: "0.6rem 0.75rem",
  background: "transparent",
  border: "1px solid var(--border)",
  color: "var(--parchment)",
  resize: "vertical",
};

function parseTextareaJson<T>(value: FormDataEntryValue | null): T[] {
  if (typeof value !== "string") return [];
  const trimmed = value.trim();
  if (!trimmed) return [];
  try {
    const parsed = JSON.parse(trimmed);
    if (!Array.isArray(parsed)) return [];
    return parsed as T[];
  } catch {
    return [];
  }
}

