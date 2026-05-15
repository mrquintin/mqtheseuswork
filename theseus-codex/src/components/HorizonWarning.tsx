"use client";

import { useMemo, useState } from "react";

import type { HorizonCalibration, UsefulHorizon } from "@/lib/calibrationData";

/**
 * Soft horizon warning for the new-forecast form.
 *
 * When a founder is about to issue a forecast whose resolution date sits
 * beyond the firm's *empirically useful prediction horizon* for that
 * domain, this surfaces an advisory banner — "our calibration drops below
 * significance at horizons > N days for this domain — are you sure?" —
 * with a one-click acknowledge.
 *
 * It is advisory, not a gate (prompt 35 constraint): a founder may
 * knowingly issue a long-horizon forecast on a clear-eyed reading of the
 * firm's track record. Acknowledging just records that the founder saw
 * the warning; the surrounding <form> can still submit either way. The
 * acknowledge state rides along as a hidden input so the server sees it.
 *
 * This component owns the two fields that *drive* the warning — the
 * forecast's domain and its expected resolution date — so they are
 * `name`d inputs and belong to the parent form.
 *
 * Threshold logic mirrors `horizonWarningFor` in `calibrationData.ts` /
 * `horizon_calibration.horizon_warning_for` in noosphere. It is
 * re-implemented here (not imported) because `calibrationData.ts` pulls
 * in server-only modules; only the *type* crosses the boundary.
 */

const MONO = "ui-monospace, SFMono-Regular, Menlo, monospace";

function daysBetween(fromISO: string): number | null {
  if (!fromISO) return null;
  const target = new Date(`${fromISO}T00:00:00Z`);
  if (Number.isNaN(target.getTime())) return null;
  const now = Date.now();
  return (target.getTime() - now) / 86_400_000;
}

function ceilingFor(
  horizon: HorizonCalibration,
  domain: string,
): { useful: UsefulHorizon; usedDomain: boolean } {
  const perDomain = horizon.usefulHorizonByDomain[domain];
  if (perDomain) return { useful: perDomain, usedDomain: true };
  return { useful: horizon.usefulHorizon, usedDomain: false };
}

export default function HorizonWarning({ horizon }: { horizon: HorizonCalibration }) {
  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const [domain, setDomain] = useState<string>(horizon.domains[0] ?? "");
  const [resolutionDate, setResolutionDate] = useState<string>("");
  const [acknowledged, setAcknowledged] = useState<boolean>(false);

  const horizonDays = daysBetween(resolutionDate);
  const { useful, usedDomain } = ceilingFor(horizon, domain);
  const ceiling = useful.beatsChanceAtEveryHorizon ? null : useful.horizonDays;
  const shouldWarn =
    ceiling !== null && horizonDays !== null && horizonDays > ceiling;

  // Reset the acknowledgement whenever the warning's premise changes, so a
  // founder cannot acknowledge a 30-day forecast and silently carry that
  // acknowledgement onto a 2-year one.
  const ackKey = `${domain}|${shouldWarn ? ceiling : "none"}`;
  const [ackKeySeen, setAckKeySeen] = useState<string>(ackKey);
  if (ackKeySeen !== ackKey) {
    setAckKeySeen(ackKey);
    setAcknowledged(false);
  }

  const scopeLabel = usedDomain && domain ? `for ${domain}` : "firm-wide";

  return (
    <fieldset
      className="portal-card"
      style={{ border: "1px solid rgba(205, 151, 67, 0.45)", padding: "1rem", margin: 0 }}
    >
      <legend
        className="mono"
        style={{
          color: "var(--amber-dim)",
          fontSize: "0.66rem",
          letterSpacing: "0.2em",
          padding: "0 0.4rem",
          textTransform: "uppercase",
        }}
      >
        Resolution horizon
      </legend>

      <div style={{ display: "grid", gap: "0.8rem", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
        <label style={{ display: "grid", gap: "0.25rem" }}>
          <span className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.72rem" }}>
            Domain
          </span>
          {horizon.domains.length > 0 ? (
            <select
              name="domain"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              style={inputStyle}
            >
              {horizon.domains.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
              {!horizon.domains.includes(domain) && domain ? (
                <option value={domain}>{domain}</option>
              ) : null}
            </select>
          ) : (
            <input
              name="domain"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              placeholder="e.g. forecasting"
              style={inputStyle}
            />
          )}
        </label>

        <label style={{ display: "grid", gap: "0.25rem" }}>
          <span className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.72rem" }}>
            Expected resolution date
          </span>
          <input
            type="date"
            name="resolutionDate"
            min={today}
            value={resolutionDate}
            onChange={(e) => setResolutionDate(e.target.value)}
            style={inputStyle}
          />
        </label>
      </div>

      <p
        className="mono"
        style={{ color: "var(--parchment-dim)", fontSize: "0.7rem", margin: "0.6rem 0 0" }}
      >
        {horizonDays !== null
          ? `horizon ≈ ${Math.max(0, Math.round(horizonDays))} days · `
          : ""}
        useful horizon {scopeLabel}:{" "}
        {ceiling === null
          ? useful.beatsChanceAtEveryHorizon
            ? "no decay observed"
            : "not yet established"
          : `${ceiling.toFixed(0)} days`}
      </p>

      {/* Advisory soft warning — never blocks the surrounding form. */}
      {shouldWarn && !acknowledged ? (
        <div
          role="alert"
          style={{
            border: "1px solid rgba(205, 151, 67, 0.65)",
            background: "rgba(205, 151, 67, 0.12)",
            marginTop: "0.8rem",
            padding: "0.8rem 0.9rem",
          }}
        >
          <p style={{ color: "var(--amber)", fontWeight: 600, margin: 0 }}>
            Long-horizon forecast
          </p>
          <p
            style={{
              color: "var(--parchment)",
              fontSize: "0.84rem",
              lineHeight: 1.5,
              margin: "0.35rem 0 0",
            }}
          >
            Our calibration drops below significance at horizons &gt;{" "}
            <strong>{ceiling!.toFixed(0)} days</strong> {scopeLabel} — are you
            sure? Beyond this horizon, issue the forecast with the explicit{" "}
            <em>&ldquo;low confidence, long horizon&rdquo;</em> framing. This is
            advisory: the firm&rsquo;s track record is on the{" "}
            <a href="/calibration/horizon" style={{ color: "var(--amber)" }}>
              horizon scorecard
            </a>
            .
          </p>
          <button
            type="button"
            onClick={() => setAcknowledged(true)}
            className="mono"
            style={{
              background: "var(--amber)",
              border: "none",
              color: "#1a1206",
              cursor: "pointer",
              fontSize: "0.74rem",
              letterSpacing: "0.08em",
              marginTop: "0.6rem",
              padding: "0.4rem 0.8rem",
            }}
          >
            Acknowledge &amp; continue
          </button>
        </div>
      ) : null}

      {shouldWarn && acknowledged ? (
        <p
          className="mono"
          role="status"
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.74rem",
            margin: "0.8rem 0 0",
          }}
        >
          ✓ Long-horizon warning acknowledged — calibration drops below
          significance past {ceiling!.toFixed(0)} days {scopeLabel}.
        </p>
      ) : null}

      {/* The surrounding <form> submits this; the server records whether
          the founder saw and acknowledged the long-horizon warning. */}
      <input
        type="hidden"
        name="horizonWarningShown"
        value={shouldWarn ? "true" : "false"}
      />
      <input
        type="hidden"
        name="horizonAcknowledged"
        value={shouldWarn && acknowledged ? "true" : "false"}
      />
    </fieldset>
  );
}

const inputStyle: React.CSSProperties = {
  background: "rgba(0, 0, 0, 0.25)",
  border: "1px solid rgba(205, 151, 67, 0.35)",
  color: "var(--parchment)",
  fontFamily: MONO,
  fontSize: "0.82rem",
  padding: "0.4rem 0.5rem",
};
