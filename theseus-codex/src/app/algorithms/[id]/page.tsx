import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import CalibrationSpark from "@/components/algorithms/CalibrationSpark";
import InvocationTable from "@/components/algorithms/InvocationTable";
import LiveInputValuePill from "@/components/algorithms/LiveInputValuePill";
import ReasoningTraceList from "@/components/algorithms/ReasoningTraceList";
import TriggerPredicatePlain from "@/components/algorithms/TriggerPredicatePlain";
import PublicHeader from "@/components/PublicHeader";
import { db } from "@/lib/db";
import { getFounder } from "@/lib/auth";
import {
  calibrationSeries,
  getPublicAlgorithm,
  isOperatorEntered,
  listInvocationsForAlgorithm,
} from "@/lib/algorithmsPublicApi";
import { latestCalibrationSnapshot } from "@/lib/algorithmsCalibrationApi";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const founder = await getFounder().catch(() => null);
  const organizationId =
    founder?.organizationId ??
    process.env.PUBLIC_ORGANIZATION_ID ??
    process.env.DEFAULT_ORGANIZATION_ID ??
    "";
  if (!organizationId) return { title: "Algorithm · Theseus" };
  const row = await getPublicAlgorithm(organizationId, id);
  if (!row) return { title: "Algorithm · Theseus" };
  return {
    title: `${row.name} · algorithm · Theseus`,
    description: row.description.slice(0, 200),
  };
}

async function loadPrincipleTexts(ids: string[]): Promise<Record<string, string>> {
  if (ids.length === 0) return {};
  try {
    const rows = (await db.principle.findMany({
      where: { id: { in: ids } },
      select: { id: true, text: true },
    })) as Array<{ id: string; text: string }>;
    return Object.fromEntries(rows.map((r) => [r.id, r.text]));
  } catch {
    return {};
  }
}

export default async function AlgorithmDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const founder = await getFounder().catch(() => null);
  const organizationId =
    founder?.organizationId ??
    process.env.PUBLIC_ORGANIZATION_ID ??
    process.env.DEFAULT_ORGANIZATION_ID ??
    "";
  if (!organizationId) notFound();

  const algorithm = await getPublicAlgorithm(organizationId, id);
  if (!algorithm) notFound();

  const invocations = await listInvocationsForAlgorithm(id, 20);
  const allInvocations = await listInvocationsForAlgorithm(id, 500);
  const calibration = calibrationSeries(allInvocations);
  const latestSnapshot = await latestCalibrationSnapshot(id);
  const principleTexts = await loadPrincipleTexts(algorithm.sourcePrincipleIds);

  const betLog = allInvocations.filter((inv) => inv.betImplied !== null);

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main
        id="algorithm-detail-main"
        className="public-container public-methodology-page"
        data-testid="algorithm-detail"
        data-algorithm-id={algorithm.id}
      >
        <nav
          aria-label="breadcrumb"
          style={{
            fontSize: "0.7rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--public-muted, #888)",
            marginBottom: "1rem",
          }}
        >
          <Link href="/algorithms" style={{ color: "inherit", textDecoration: "none" }}>
            ← all algorithms
          </Link>
        </nav>

        <section className="public-section" aria-labelledby="algorithm-hero-title">
          <header
            style={{
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
              gap: "1rem",
              flexWrap: "wrap",
            }}
          >
            <h1 id="algorithm-hero-title" className="public-title" style={{ margin: 0 }}>
              {algorithm.name}
            </h1>
            <span
              data-testid="algorithm-status-pill"
              className="mono"
              style={{
                padding: "0.22rem 0.65rem",
                border: `1px solid ${
                  algorithm.status === "ACTIVE"
                    ? "var(--amber, #d4a017)"
                    : algorithm.status === "PAUSED"
                      ? "var(--ember, #c0584a)"
                      : "var(--public-muted, #888)"
                }`,
                color:
                  algorithm.status === "ACTIVE"
                    ? "var(--amber, #d4a017)"
                    : algorithm.status === "PAUSED"
                      ? "var(--ember, #c0584a)"
                      : "var(--public-muted, #888)",
                fontSize: "0.65rem",
                letterSpacing: "0.22em",
                textTransform: "uppercase",
              }}
            >
              {algorithm.status.toLowerCase()}
            </span>
          </header>
          {algorithm.description ? (
            <p className="public-lede" style={{ marginTop: "1rem" }}>
              {algorithm.description}
            </p>
          ) : null}
          {algorithm.retiredReason ? (
            <p
              data-testid="retired-reason"
              style={{ color: "var(--ember, #c0584a)", marginTop: "0.5rem" }}
            >
              Retired — {algorithm.retiredReason}
            </p>
          ) : null}
          <div
            style={{
              marginTop: "1rem",
              display: "flex",
              gap: "0.5rem",
              flexWrap: "wrap",
            }}
          >
            {algorithm.sourcePrincipleIds.map((pid) => (
              <Link
                key={pid}
                href={`/principles/${pid}`}
                data-testid="principle-pill"
                style={{
                  padding: "0.25rem 0.65rem",
                  border: "1px solid var(--public-muted, #888)",
                  color: "var(--public-muted, #aaa)",
                  textDecoration: "none",
                  fontSize: "0.65rem",
                  letterSpacing: "0.16em",
                  textTransform: "uppercase",
                  fontFamily: "'JetBrains Mono', monospace",
                }}
              >
                {principleTexts[pid]
                  ? `${principleTexts[pid].slice(0, 60)}${principleTexts[pid].length > 60 ? "…" : ""}`
                  : pid.slice(0, 12)}
              </Link>
            ))}
          </div>
        </section>

        <section className="public-section" aria-labelledby="how-it-works-title">
          <h2 id="how-it-works-title">How this algorithm works</h2>
          <ReasoningTraceList
            chain={algorithm.reasoningChain}
            principleTextsById={principleTexts}
          />
        </section>

        <section className="public-section" aria-labelledby="inputs-title">
          <h2 id="inputs-title">Inputs it watches</h2>
          {algorithm.inputs.length === 0 ? (
            <p style={{ color: "var(--public-muted, #888)" }}>No declared inputs.</p>
          ) : (
            <ul
              data-testid="inputs-list"
              style={{
                listStyle: "none",
                padding: 0,
                margin: 0,
                display: "flex",
                flexDirection: "column",
                gap: "0.55rem",
              }}
            >
              {algorithm.inputs.map((inp) => (
                <li
                  key={inp.name}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "0.25rem",
                    padding: "0.65rem 0.85rem",
                    border: "1px solid var(--border, #333)",
                    borderRadius: 3,
                    background: "var(--stone-light, #1d1d1d)",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.6rem",
                      flexWrap: "wrap",
                    }}
                  >
                    <code
                      style={{
                        fontFamily: "'JetBrains Mono', monospace",
                        color: "var(--text, #eee)",
                        fontSize: "0.85rem",
                      }}
                    >
                      {inp.name}
                    </code>
                    <span style={{ color: "var(--public-muted, #888)", fontSize: "0.75rem" }}>
                      {inp.type}
                      {inp.units ? ` (${inp.units})` : ""}
                    </span>
                    <LiveInputValuePill
                      algorithmId={algorithm.id}
                      inputName={inp.name}
                      observabilitySource={inp.observability_source}
                    />
                    {isOperatorEntered(inp) ? (
                      <span
                        data-testid="operator-input-badge"
                        className="mono"
                        style={{
                          padding: "0.1rem 0.4rem",
                          border: "1px solid var(--amber, #d4a017)",
                          color: "var(--amber, #d4a017)",
                          fontSize: "0.55rem",
                          letterSpacing: "0.18em",
                          textTransform: "uppercase",
                        }}
                      >
                        operator input
                      </span>
                    ) : null}
                  </div>
                  {inp.description ? (
                    <p
                      style={{
                        margin: 0,
                        fontFamily: "'EB Garamond', serif",
                        fontSize: "0.92rem",
                        color: "var(--public-muted, #aaa)",
                      }}
                    >
                      {inp.description}
                    </p>
                  ) : null}
                  {inp.observability_source ? (
                    <p
                      style={{
                        margin: 0,
                        fontFamily: "'JetBrains Mono', monospace",
                        fontSize: "0.7rem",
                        color: "var(--public-muted, #888)",
                      }}
                    >
                      source: {inp.observability_source}
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="public-section" aria-labelledby="trigger-title">
          <h2 id="trigger-title">Trigger condition</h2>
          <TriggerPredicatePlain predicate={algorithm.triggerPredicate} />
        </section>

        <section className="public-section" aria-labelledby="calibration-title">
          <h2 id="calibration-title">Calibration over time</h2>
          {latestSnapshot ? (
            <div
              data-testid="calibration-snapshot"
              style={{
                marginBottom: "0.85rem",
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
                gap: "0.5rem",
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: "0.75rem",
                color: "var(--public-muted, #ccc)",
              }}
            >
              <SnapshotStat
                label="accuracy"
                value={latestSnapshot.accuracy}
                fmt={(v) => `${Math.round(v * 100)}%`}
              />
              <SnapshotStat
                label="mean Brier"
                value={latestSnapshot.meanBrier}
                fmt={(v) => v.toFixed(3)}
              />
              <SnapshotStat
                label="directional"
                value={latestSnapshot.directionalAccuracy}
                fmt={(v) => `${Math.round(v * 100)}%`}
              />
              <SnapshotStat
                label="band drift"
                value={latestSnapshot.confidenceCalibrationDrift}
                fmt={(v) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}`}
              />
              <SnapshotStat
                label="last 30d"
                value={latestSnapshot.last30dAccuracy}
                fmt={(v) => `${Math.round(v * 100)}%`}
              />
              <SnapshotStat
                label="resolved"
                value={latestSnapshot.resolvedInvocations}
                fmt={(v) => `${v} / ${latestSnapshot.totalInvocations}`}
              />
            </div>
          ) : null}
          {calibration.length === 0 ? (
            <p style={{ color: "var(--public-muted, #888)" }}>
              No resolved invocations yet — calibration trace appears once
              outcomes start landing.
            </p>
          ) : (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "1rem",
                flexWrap: "wrap",
              }}
            >
              <CalibrationSpark series={calibration} width={280} height={64} />
              <p
                style={{
                  margin: 0,
                  color: "var(--public-muted, #aaa)",
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: "0.75rem",
                }}
              >
                cumulative correctness ratio across {calibration.length}{" "}
                resolution{calibration.length === 1 ? "" : "s"}
                {algorithm.hitRate.ratio !== null ? (
                  <>
                    {" "}· current {Math.round(algorithm.hitRate.ratio * 100)}%
                  </>
                ) : null}
              </p>
            </div>
          )}
        </section>

        <section className="public-section" aria-labelledby="invocations-title">
          <h2 id="invocations-title">Latest invocations</h2>
          <InvocationTable algorithmId={algorithm.id} invocations={invocations} />
        </section>

        <section className="public-section" aria-labelledby="bet-log-title">
          <h2 id="bet-log-title">Bet log</h2>
          {betLog.length === 0 ? (
            <p style={{ color: "var(--public-muted, #888)" }}>
              No bets implied by this algorithm so far. When an invocation
              implies one, it lands here with the firm's decision.
            </p>
          ) : (
            <ul
              data-testid="bet-log"
              style={{
                listStyle: "none",
                padding: 0,
                margin: 0,
                display: "flex",
                flexDirection: "column",
                gap: "0.5rem",
              }}
            >
              {betLog.map((inv) => (
                <li
                  key={inv.id}
                  style={{
                    border: "1px solid var(--border, #333)",
                    borderRadius: 3,
                    padding: "0.65rem 0.85rem",
                    background: "var(--stone-light, #1d1d1d)",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      gap: "0.65rem",
                      alignItems: "baseline",
                      flexWrap: "wrap",
                    }}
                  >
                    <Link
                      href={`/algorithms/${algorithm.id}/invocations/${inv.id}`}
                      style={{ color: "var(--amber, #d4a017)", textDecoration: "none" }}
                    >
                      {inv.invokedAt.toISOString().slice(0, 10)}
                    </Link>
                    <span style={{ color: "var(--text, #eee)" }}>
                      {inv.betImplied?.direction} {inv.betImplied?.instrument}{" "}
                      <span style={{ color: "var(--public-muted, #888)" }}>
                        @ {inv.betImplied?.venue || "—"}
                      </span>
                    </span>
                    {inv.betImplied?.sizingHint ? (
                      <span style={{ color: "var(--public-muted, #aaa)", fontSize: "0.8rem" }}>
                        {inv.betImplied.sizingHint}
                      </span>
                    ) : null}
                    <span
                      style={{
                        marginLeft: "auto",
                        color: inv.correctness === "CORRECT"
                          ? "rgba(160, 211, 170, 0.95)"
                          : inv.correctness === "INCORRECT"
                            ? "var(--ember, #c0584a)"
                            : "var(--public-muted, #888)",
                        fontSize: "0.7rem",
                        letterSpacing: "0.18em",
                        textTransform: "uppercase",
                      }}
                    >
                      {inv.correctness ?? "unresolved"}
                    </span>
                  </div>
                  {inv.betImplied?.rationale ? (
                    <p
                      style={{
                        margin: "0.4rem 0 0",
                        fontFamily: "'EB Garamond', serif",
                        fontSize: "0.95rem",
                        color: "var(--public-muted, #ccc)",
                      }}
                    >
                      {inv.betImplied.rationale}
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
          <p
            style={{
              marginTop: "0.75rem",
              color: "var(--public-muted, #888)",
              fontSize: "0.7rem",
              fontStyle: "italic",
            }}
          >
            Live-money positions are operator-only. Public surface shows paper
            implications and graded outcomes.
          </p>
        </section>
      </main>
    </>
  );
}

function SnapshotStat({
  label,
  value,
  fmt,
}: {
  label: string;
  value: number | null;
  fmt: (v: number) => string;
}) {
  return (
    <div
      data-testid={`snapshot-stat-${label.replace(/\s+/g, "-")}`}
      style={{
        padding: "0.45rem 0.65rem",
        border: "1px solid var(--border, #333)",
        borderRadius: 3,
        background: "var(--stone-light, #1d1d1d)",
      }}
    >
      <div
        style={{
          fontSize: "0.6rem",
          letterSpacing: "0.16em",
          textTransform: "uppercase",
          color: "var(--public-muted, #888)",
        }}
      >
        {label}
      </div>
      <div style={{ color: "var(--text, #eee)" }}>
        {value === null || value === undefined ? "—" : fmt(value)}
      </div>
    </div>
  );
}
