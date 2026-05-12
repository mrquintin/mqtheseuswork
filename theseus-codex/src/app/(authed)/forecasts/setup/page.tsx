import Link from "next/link";
import { redirect } from "next/navigation";

import { getFounder } from "@/lib/auth";
import { getOperatorSetupStatus } from "@/lib/forecastsOperatorApi";
import type {
  OperatorEnvVarStatus,
  OperatorExchangeSetup,
  OperatorSetupStatus,
} from "@/lib/forecastsTypes";
import { canWrite } from "@/lib/roles";

export const dynamic = "force-dynamic";

const STATUS_LABELS: Record<string, string> = {
  PAPER_ONLY: "Paper-only — live trading flag is off",
  LIVE_DISABLED_NO_CREDENTIALS: "Live flag on, no exchange credentials present",
  LIVE_ENABLED_AWAITING_AUTHORIZATION: "Live flag on, credentials present, awaiting per-bet authorization",
};

const BLOCKER_LABELS: Record<string, string> = {
  scheduler_status_stale_or_missing:
    "Scheduler status file is missing or older than FORECASTS_STATUS_MAX_AGE_SECONDS.",
  no_exchange_configured: "Neither Polymarket nor Kalshi credentials are configured on the server.",
  kill_switch_engaged: "The portfolio kill switch is engaged — disengage it from the operator console.",
  live_trading_flag_disabled: "FORECASTS_LIVE_TRADING_ENABLED is not 'true' in the server environment.",
  max_stake_usd_not_configured: "FORECASTS_MAX_STAKE_USD is unset or 0 — required before live orders.",
  max_daily_loss_usd_not_configured:
    "FORECASTS_MAX_DAILY_LOSS_USD is unset or 0 — required before live orders.",
};

function readinessTone(ok: boolean): string {
  return ok ? "rgba(140, 196, 132, 0.55)" : "rgba(185, 92, 92, 0.55)";
}

function readinessLabel(ok: boolean): string {
  return ok ? "READY" : "NOT READY";
}

function formatTimestamp(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toISOString().replace("T", " ").slice(0, 19) + "Z";
}

function formatUsd(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `$${value.toFixed(2)}`;
}

function EnvVarRow({ env }: { env: OperatorEnvVarStatus }) {
  return (
    <li className="mono" style={{ display: "flex", gap: "0.6rem", justifyContent: "space-between", padding: "0.15rem 0" }}>
      <span style={{ color: "var(--parchment)" }}>
        {env.name}
        {env.alternate ? (
          <span style={{ color: "var(--parchment-dim)" }}> (or {env.alternate})</span>
        ) : null}
      </span>
      <span
        style={{
          color: env.present ? "var(--success)" : "var(--ember)",
          fontWeight: 600,
        }}
      >
        {env.present ? "present" : "missing"}
      </span>
    </li>
  );
}

function ExchangeCard({ name, exchange }: { name: string; exchange: OperatorExchangeSetup }) {
  return (
    <section
      className="portal-card"
      style={{
        borderColor: exchange.configured
          ? "rgba(140, 196, 132, 0.55)"
          : "rgba(205, 151, 67, 0.45)",
        padding: "1rem",
      }}
    >
      <header style={{ alignItems: "baseline", display: "flex", gap: "0.8rem", justifyContent: "space-between" }}>
        <h2 style={{ color: "var(--amber)", fontFamily: "'Cinzel', serif", margin: 0 }}>{name}</h2>
        <span
          className="mono"
          style={{
            color: exchange.configured ? "var(--success)" : "var(--ember)",
            fontSize: "0.72rem",
            fontWeight: 600,
            letterSpacing: "0.15em",
          }}
        >
          {exchange.configured ? "CONFIGURED" : "NOT CONFIGURED"}
        </span>
      </header>
      <p className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.68rem", margin: "0.35rem 0 0" }}>
        Required environment variables must be set on the server. The keys themselves are never returned by this page.
      </p>
      <div style={{ marginTop: "0.6rem" }}>
        <p className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.66rem", letterSpacing: "0.2em", margin: 0, textTransform: "uppercase" }}>
          Required
        </p>
        <ul style={{ listStyle: "none", margin: "0.3rem 0 0", padding: 0 }}>
          {exchange.required_env_vars.map((env) => (
            <EnvVarRow key={env.name} env={env} />
          ))}
        </ul>
      </div>
      {exchange.optional_env_vars.length ? (
        <div style={{ marginTop: "0.6rem" }}>
          <p className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.66rem", letterSpacing: "0.2em", margin: 0, textTransform: "uppercase" }}>
            Optional
          </p>
          <ul style={{ listStyle: "none", margin: "0.3rem 0 0", padding: 0 }}>
            {exchange.optional_env_vars.map((env) => (
              <EnvVarRow key={env.name} env={env} />
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function ReadinessTile({ label, ok, hint }: { label: string; ok: boolean; hint: string }) {
  return (
    <div
      className="portal-card"
      style={{ borderColor: readinessTone(ok), padding: "0.9rem" }}
    >
      <p className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.64rem", letterSpacing: "0.2em", margin: 0, textTransform: "uppercase" }}>
        {label}
      </p>
      <p
        style={{
          color: ok ? "var(--success)" : "var(--ember)",
          fontFamily: "'Cinzel', serif",
          fontSize: "1.1rem",
          fontWeight: 600,
          margin: "0.25rem 0 0",
        }}
      >
        {readinessLabel(ok)}
      </p>
      <p style={{ color: "var(--parchment-dim)", fontSize: "0.78rem", lineHeight: 1.45, margin: "0.35rem 0 0" }}>
        {hint}
      </p>
    </div>
  );
}

function SetupBody({ status }: { status: OperatorSetupStatus }) {
  const blockers = status.readiness.blockers;
  return (
    <>
      <section>
        <p className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.68rem", letterSpacing: "0.2em", margin: 0, textTransform: "uppercase" }}>
          Founder operator console / setup
        </p>
        <h1 style={{ color: "var(--amber)", fontFamily: "'Cinzel Decorative', 'Cinzel', serif", margin: "0.2rem 0 0" }}>
          Founder-alpha setup
        </h1>
        <p style={{ color: "var(--parchment-dim)", lineHeight: 1.5, margin: "0.45rem 0 0", maxWidth: "62rem" }}>
          Prediction-market portfolio readiness for Polymarket and Kalshi. This page reads server configuration only —
          no key material is fetched, displayed, or stored by Theseus Codex. Live order submission still requires
          per-bet authorization and a clear kill switch.
        </p>
        <p className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.72rem", margin: "0.5rem 0 0" }}>
          Trading mode: <strong style={{ color: "var(--amber)" }}>{status.trading_mode}</strong>
          {STATUS_LABELS[status.trading_mode] ? ` — ${STATUS_LABELS[status.trading_mode]}` : ""}
        </p>
      </section>

      <section style={{ display: "grid", gap: "0.8rem", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
        <ReadinessTile
          label="Monitoring active"
          ok={status.readiness.monitoring_active}
          hint={
            status.readiness.monitoring_active
              ? `Scheduler last ingest ${formatTimestamp(status.scheduler.last_ingest_ts)}`
              : "Scheduler status file is missing or stale — start the scheduler container."
          }
        />
        <ReadinessTile
          label="Ready for live candidates"
          ok={status.readiness.ready_for_live_candidates}
          hint={
            status.readiness.ready_for_live_candidates
              ? "An exchange is configured, the scheduler is fresh, and the kill switch is clear."
              : "Live-candidate emission requires at least one configured exchange and a fresh scheduler."
          }
        />
        <ReadinessTile
          label="Ready for live orders"
          ok={status.readiness.ready_for_live_orders}
          hint={
            status.readiness.ready_for_live_orders
              ? "All safety prerequisites pass. Per-bet operator confirmation still required at submission."
              : "Live orders are blocked until risk limits, the live flag, and credentials are all in place."
          }
        />
      </section>

      {blockers.length ? (
        <section
          className="portal-card"
          style={{ borderColor: "rgba(185, 92, 92, 0.55)", padding: "0.9rem" }}
        >
          <h2 style={{ color: "var(--ember)", fontFamily: "'Cinzel', serif", margin: 0 }}>Blockers</h2>
          <ul style={{ color: "var(--parchment)", margin: "0.5rem 0 0", paddingLeft: "1.2rem" }}>
            {blockers.map((code) => (
              <li key={code} style={{ marginBottom: "0.25rem" }}>
                {BLOCKER_LABELS[code] ?? code}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section style={{ display: "grid", gap: "1rem", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))" }}>
        <ExchangeCard name="Polymarket" exchange={status.exchanges.polymarket} />
        <ExchangeCard name="Kalshi" exchange={status.exchanges.kalshi} />
      </section>

      <section
        className="portal-card"
        style={{ padding: "1rem" }}
      >
        <h2 style={{ color: "var(--amber)", fontFamily: "'Cinzel', serif", margin: 0 }}>Bankroll & risk limits</h2>
        <p className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.68rem", margin: "0.25rem 0 0" }}>
          Live submission gates read these caps from the server environment. Zero or unset means the gate refuses.
        </p>
        <ul style={{ listStyle: "none", margin: "0.6rem 0 0", padding: 0 }}>
          <li className="mono" style={{ display: "flex", justifyContent: "space-between", padding: "0.15rem 0" }}>
            <span>FORECASTS_LIVE_TRADING_ENABLED</span>
            <span style={{ color: status.live_trading_enabled ? "var(--success)" : "var(--ember)" }}>
              {status.live_trading_enabled ? "true" : "not true"}
            </span>
          </li>
          <li className="mono" style={{ display: "flex", justifyContent: "space-between", padding: "0.15rem 0" }}>
            <span>FORECASTS_MAX_STAKE_USD</span>
            <span style={{ color: status.risk_limits.max_stake_configured ? "var(--success)" : "var(--ember)" }}>
              {formatUsd(status.risk_limits.max_stake_usd)}
            </span>
          </li>
          <li className="mono" style={{ display: "flex", justifyContent: "space-between", padding: "0.15rem 0" }}>
            <span>FORECASTS_MAX_DAILY_LOSS_USD</span>
            <span style={{ color: status.risk_limits.max_daily_loss_configured ? "var(--success)" : "var(--ember)" }}>
              {formatUsd(status.risk_limits.max_daily_loss_usd)}
            </span>
          </li>
          <li className="mono" style={{ display: "flex", justifyContent: "space-between", padding: "0.15rem 0" }}>
            <span>FORECASTS_KILL_SWITCH_AUTO_THRESHOLD_USD</span>
            <span style={{ color: "var(--parchment)" }}>
              {formatUsd(status.risk_limits.kill_switch_auto_threshold_usd)}
            </span>
          </li>
        </ul>
      </section>

      <section
        className="portal-card"
        style={{ padding: "1rem" }}
      >
        <h2 style={{ color: "var(--amber)", fontFamily: "'Cinzel', serif", margin: 0 }}>Scheduler & kill switch</h2>
        <ul style={{ listStyle: "none", margin: "0.6rem 0 0", padding: 0 }}>
          <li className="mono" style={{ display: "flex", justifyContent: "space-between", padding: "0.15rem 0" }}>
            <span>Status file</span>
            <span style={{ color: status.scheduler.present ? "var(--success)" : "var(--ember)" }}>
              {status.scheduler.present ? "present" : "missing"}
            </span>
          </li>
          <li className="mono" style={{ display: "flex", justifyContent: "space-between", padding: "0.15rem 0" }}>
            <span>Path</span>
            <span style={{ color: "var(--parchment-dim)", overflowWrap: "anywhere" }}>
              {status.scheduler.status_path}
            </span>
          </li>
          <li className="mono" style={{ display: "flex", justifyContent: "space-between", padding: "0.15rem 0" }}>
            <span>Last ingest</span>
            <span style={{ color: status.scheduler.fresh ? "var(--success)" : "var(--ember)" }}>
              {formatTimestamp(status.scheduler.last_ingest_ts)}
              {status.scheduler.age_seconds !== null ? ` (${Math.round(status.scheduler.age_seconds)}s ago)` : ""}
            </span>
          </li>
          <li className="mono" style={{ display: "flex", justifyContent: "space-between", padding: "0.15rem 0" }}>
            <span>Last forecast generation</span>
            <span style={{ color: "var(--parchment)" }}>{formatTimestamp(status.scheduler.last_generate_ts)}</span>
          </li>
          <li className="mono" style={{ display: "flex", justifyContent: "space-between", padding: "0.15rem 0" }}>
            <span>Last live submission</span>
            <span style={{ color: "var(--parchment)" }}>
              {formatTimestamp(status.scheduler.last_live_submission_ts)}
            </span>
          </li>
          <li className="mono" style={{ display: "flex", justifyContent: "space-between", padding: "0.15rem 0" }}>
            <span>Kill switch</span>
            <span style={{ color: status.kill_switch.engaged ? "var(--ember)" : "var(--success)" }}>
              {status.kill_switch.engaged ? `engaged: ${status.kill_switch.reason ?? "unknown"}` : "clear"}
            </span>
          </li>
          <li className="mono" style={{ display: "flex", justifyContent: "space-between", padding: "0.15rem 0" }}>
            <span>Live balance</span>
            <span style={{ color: "var(--parchment)" }}>{formatUsd(status.kill_switch.live_balance_usd)}</span>
          </li>
          <li className="mono" style={{ display: "flex", justifyContent: "space-between", padding: "0.15rem 0" }}>
            <span>Daily loss today</span>
            <span style={{ color: "var(--parchment)" }}>{formatUsd(status.kill_switch.daily_loss_usd)}</span>
          </li>
        </ul>
      </section>

      <section
        className="portal-card"
        style={{ padding: "1rem" }}
      >
        <h2 style={{ color: "var(--amber)", fontFamily: "'Cinzel', serif", margin: 0 }}>How to configure</h2>
        <ol style={{ color: "var(--parchment)", lineHeight: 1.55, margin: "0.5rem 0 0", paddingLeft: "1.4rem" }}>
          <li>
            Place the required environment variables in the server environment (not in Theseus Codex DB, never in chat
            or support channels). Local dev: a <code>.env</code> file at the repo root; production: the deployment
            secret store (e.g. Docker compose env, hosted secret manager).
          </li>
          <li>
            Polymarket needs <code>POLYMARKET_PRIVATE_KEY</code> (an EVM private key controlling a funded
            Polymarket-CLOB wallet). Optionally set <code>POLYMARKET_FUNDER_ADDRESS</code> if using a proxy wallet.
          </li>
          <li>
            Kalshi needs <code>KALSHI_API_KEY_ID</code> and the RSA PEM body in
            <code> KALSHI_API_PRIVATE_KEY</code> (or the legacy <code>KALSHI_PRIVATE_KEY_PEM</code>). For one-line
            env files, encode newlines as literal <code>\n</code> — the loader decodes them.
          </li>
          <li>
            Restart the API and scheduler containers; this page only reflects environment variables visible to the API
            process. The scheduler must be running for &ldquo;Monitoring active&rdquo; to flip on.
          </li>
          <li>
            Set <code>FORECASTS_MAX_STAKE_USD</code> and <code>FORECASTS_MAX_DAILY_LOSS_USD</code> before flipping
            <code> FORECASTS_LIVE_TRADING_ENABLED=true</code>. Both are read by the safety gates at submit time.
          </li>
          <li>
            Once all three readiness tiles are green, return to the operator console to authorize individual live
            candidates and confirm bets per-bet. The kill switch overrides everything.
          </li>
        </ol>
        <p style={{ color: "var(--parchment-dim)", fontSize: "0.8rem", lineHeight: 1.5, margin: "0.6rem 0 0" }}>
          Detailed instructions live in{" "}
          <code>docs/operations/Forecasts_Portfolio_Setup.md</code>. Never paste a private key into a screenshot, a
          shared doc, a support thread, or a chat tool.
        </p>
      </section>

      <section style={{ display: "flex", gap: "0.8rem", justifyContent: "space-between" }}>
        <Link className="mono" href="/forecasts/operator" style={{ color: "var(--amber)", letterSpacing: "0.1em" }}>
          ← back to operator console
        </Link>
        <span className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.7rem" }}>
          Checked at {formatTimestamp(status.checked_at)}
        </span>
      </section>
    </>
  );
}

export default async function ForecastsSetupPage() {
  const founder = await getFounder();
  if (!founder) redirect("/login");
  if (!canWrite(founder.role)) redirect("/dashboard");

  let status: OperatorSetupStatus | null = null;
  let error: string | null = null;
  try {
    status = await getOperatorSetupStatus();
  } catch (err) {
    error = err instanceof Error ? err.message : String(err);
  }

  return (
    <main style={{ display: "grid", gap: "1rem", margin: "0 auto", maxWidth: 1100, padding: "1.5rem 1rem 3rem" }}>
      {status ? (
        <SetupBody status={status} />
      ) : (
        <section
          className="portal-card"
          role="alert"
          style={{ borderColor: "rgba(185, 92, 92, 0.55)", padding: "1rem" }}
        >
          <h1 style={{ color: "var(--ember)", fontFamily: "'Cinzel', serif", margin: 0 }}>
            Setup status unavailable
          </h1>
          <p style={{ color: "var(--parchment)", lineHeight: 1.5, margin: "0.5rem 0 0" }}>
            The forecasts operator API did not return a setup status. Confirm{" "}
            <code>FORECASTS_OPERATOR_SECRET</code> and <code>FORECASTS_API_URL</code> are set on the Codex server and
            that the API is reachable.
          </p>
          {error ? (
            <pre
              className="mono"
              style={{ color: "var(--parchment-dim)", fontSize: "0.72rem", marginTop: "0.6rem", whiteSpace: "pre-wrap" }}
            >
              {error}
            </pre>
          ) : null}
          <p style={{ marginTop: "0.6rem" }}>
            <Link className="mono" href="/forecasts/operator" style={{ color: "var(--amber)" }}>
              ← back to operator console
            </Link>
          </p>
        </section>
      )}
    </main>
  );
}
