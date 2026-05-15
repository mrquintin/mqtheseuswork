import Link from "next/link";
import { redirect } from "next/navigation";

import HorizonWarning from "@/components/HorizonWarning";
import { getFounder } from "@/lib/auth";
import { loadHorizonCalibration } from "@/lib/calibrationData";
import { canWrite } from "@/lib/roles";

/**
 * New-forecast surface — the horizon pre-check.
 *
 * Before a founder commits to issuing a forecast, this form runs the
 * horizon check from prompt 35: it loads the firm's per-domain useful
 * prediction horizon and, via <HorizonWarning>, surfaces a soft advisory
 * when the prospective resolution date sits beyond it. The warning is
 * advisory — a founder may knowingly issue a long-horizon forecast — so
 * the form never blocks; it records whether the warning was shown and
 * acknowledged.
 *
 * Issuance itself flows through the existing methods → conclusions →
 * forecast pipeline and the operator console; this page does not persist a
 * ForecastPrediction. It is the pre-flight check that makes the firm's
 * own track record impossible to issue a forecast without seeing.
 */

export const dynamic = "force-dynamic";

const MONO = "ui-monospace, SFMono-Regular, Menlo, monospace";

async function prepareForecastDraft(formData: FormData): Promise<void> {
  "use server";
  const founder = await getFounder();
  if (!founder || !canWrite(founder.role)) redirect("/dashboard");
  const warned = String(formData.get("horizonWarningShown") ?? "false") === "true";
  const acknowledged =
    String(formData.get("horizonAcknowledged") ?? "false") === "true";
  // No ForecastPrediction is written here — issuance is the operator
  // pipeline's job. We carry the horizon-check result forward so the
  // confirmation can state plainly whether the founder saw the warning.
  const params = new URLSearchParams({
    prepared: "1",
    warned: warned ? "1" : "0",
    acknowledged: acknowledged ? "1" : "0",
  });
  redirect(`/forecasts/new?${params.toString()}`);
}

type SearchParams = {
  prepared?: string;
  warned?: string;
  acknowledged?: string;
};

export default async function NewForecastPage({
  searchParams,
}: {
  searchParams?: Promise<SearchParams>;
}) {
  const founder = await getFounder();
  if (!founder) redirect("/login");
  if (!canWrite(founder.role)) redirect("/dashboard");

  const horizon = await loadHorizonCalibration();
  const params = (await searchParams) ?? {};
  const prepared = params.prepared === "1";
  const warned = params.warned === "1";
  const acknowledged = params.acknowledged === "1";

  return (
    <main
      style={{
        display: "grid",
        gap: "1rem",
        margin: "0 auto",
        maxWidth: 880,
        padding: "1.5rem 1rem 3rem",
      }}
    >
      <section>
        <p
          className="mono"
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.68rem",
            letterSpacing: "0.2em",
            margin: 0,
            textTransform: "uppercase",
          }}
        >
          Founder console / forecasts
        </p>
        <h1
          style={{
            color: "var(--amber)",
            fontFamily: "'Cinzel Decorative', 'Cinzel', serif",
            margin: "0.2rem 0 0",
          }}
        >
          New forecast — horizon pre-check
        </h1>
        <p
          style={{
            color: "var(--parchment-dim)",
            lineHeight: 1.55,
            margin: "0.45rem 0 0",
            maxWidth: "60rem",
          }}
        >
          Draft a forecast and check it against the firm&rsquo;s track
          record before issuing. If the resolution date sits beyond the
          firm&rsquo;s empirically useful prediction horizon for the domain,
          the form raises a soft warning — advisory only. Issuance itself
          runs through the operator pipeline; this surface makes the
          horizon decay impossible to miss first.
        </p>
      </section>

      {prepared ? (
        <section
          className="portal-card"
          role="status"
          style={{
            borderColor: warned
              ? "rgba(205, 151, 67, 0.55)"
              : "rgba(140, 196, 132, 0.55)",
            padding: "0.9rem 1rem",
          }}
        >
          <h2
            style={{
              color: warned ? "var(--amber)" : "var(--success)",
              fontFamily: "'Cinzel', serif",
              margin: 0,
            }}
          >
            Draft checked
          </h2>
          <p style={{ color: "var(--parchment)", lineHeight: 1.5, margin: "0.4rem 0 0" }}>
            {warned
              ? acknowledged
                ? "This forecast is beyond the firm's useful horizon for its domain — the warning was shown and acknowledged. Carry it forward to the operator pipeline with the explicit \"low confidence, long horizon\" framing."
                : "This forecast is beyond the firm's useful horizon, and the long-horizon warning was not acknowledged. You can still issue it — the warning is advisory — but reconsider the framing first."
              : "This forecast's resolution date is within the firm's useful prediction horizon for its domain. No long-horizon caveat needed."}
          </p>
        </section>
      ) : null}

      <form action={prepareForecastDraft} style={{ display: "grid", gap: "1rem" }}>
        <section className="portal-card" style={{ padding: "1rem", display: "grid", gap: "0.8rem" }}>
          <label style={{ display: "grid", gap: "0.25rem" }}>
            <span className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.72rem" }}>
              Headline
            </span>
            <input
              name="headline"
              required
              maxLength={140}
              placeholder="e.g. Polymarket: will X happen by date Y?"
              style={fieldStyle}
            />
          </label>

          <label style={{ display: "grid", gap: "0.25rem" }}>
            <span className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.72rem" }}>
              Probability of YES (0–1)
            </span>
            <input
              name="probabilityYes"
              type="number"
              required
              min={0}
              max={1}
              step={0.01}
              placeholder="0.62"
              style={{ ...fieldStyle, maxWidth: "10rem" }}
            />
          </label>

          <label style={{ display: "grid", gap: "0.25rem" }}>
            <span className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.72rem" }}>
              Reasoning
            </span>
            <textarea
              name="reasoning"
              required
              rows={5}
              placeholder="What evidence moves this probability, and why?"
              style={{ ...fieldStyle, resize: "vertical" }}
            />
          </label>
        </section>

        <HorizonWarning horizon={horizon} />

        <div style={{ display: "flex", gap: "0.8rem", justifyContent: "space-between", alignItems: "center" }}>
          <Link
            className="mono"
            href="/forecasts/operator"
            style={{ color: "var(--amber)", letterSpacing: "0.1em" }}
          >
            ← operator console
          </Link>
          <button
            type="submit"
            className="mono"
            style={{
              background: "var(--amber)",
              border: "none",
              color: "#1a1206",
              cursor: "pointer",
              fontSize: "0.8rem",
              letterSpacing: "0.08em",
              padding: "0.55rem 1.1rem",
            }}
          >
            Run horizon check
          </button>
        </div>
      </form>

      <p
        className="mono"
        style={{ color: "var(--parchment-dim)", fontSize: "0.7rem", margin: 0 }}
      >
        Full per-bucket reliability and the firm&rsquo;s useful horizon:{" "}
        <Link href="/calibration/horizon" style={{ color: "var(--amber)" }}>
          calibration scorecard → horizon
        </Link>
      </p>
    </main>
  );
}

const fieldStyle: React.CSSProperties = {
  background: "rgba(0, 0, 0, 0.25)",
  border: "1px solid rgba(205, 151, 67, 0.35)",
  color: "var(--parchment)",
  fontFamily: MONO,
  fontSize: "0.84rem",
  padding: "0.45rem 0.55rem",
  width: "100%",
};
