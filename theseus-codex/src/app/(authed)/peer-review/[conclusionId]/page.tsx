import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { getFounder } from "@/lib/auth";
import {
  fetchPeerReviews,
  submitToRigorGate,
  toCSV,
  type Finding,
} from "@/lib/api/round3";
import DownloadButton from "@/components/DownloadButton";
import SwarmDisagreementBadge from "@/components/SwarmDisagreementBadge";
import {
  objectionSeverityColor,
  objectionSeverityRank,
  peerVerdictColor,
  severityColor,
} from "@/lib/colors";
import { callNoosphereJson } from "@/lib/pythonRuntime";
import { founderDisplayName } from "@/lib/founderDisplay";
import { requireTenantContext } from "@/lib/tenant";

type PeerReviewRecord = Awaited<ReturnType<typeof fetchPeerReviews>>[number];

interface ProviderMeta {
  provider: string | null;
  model: string | null;
  divergesWith: string[];
  swarmPartialReason: string | null;
  swarmMonoculture: boolean;
}

interface ObjectionSeverity {
  label: "low" | "medium" | "high";
  value: number;
  judgeCapped: boolean;
  stale: boolean;
}

function parseSeverity(finding: Finding): ObjectionSeverity | null {
  // The Noosphere swarm encodes severity in evidence as
  // `severity=<label>:<value>`. We don't ship a structured column for
  // it yet — the evidence string is the only stable contract.
  let label: ObjectionSeverity["label"] | null = null;
  let value = 0;
  let judgeCapped = false;
  let stale = false;
  for (const ev of finding.evidence || []) {
    if (ev.startsWith("severity=") && ev.includes(":")) {
      const [, rest] = ev.split("=", 2);
      const [labelStr, valStr] = rest.split(":", 2);
      if (labelStr === "low" || labelStr === "medium" || labelStr === "high") {
        label = labelStr;
        const n = Number(valStr);
        if (!Number.isNaN(n)) value = n;
      }
    } else if (ev === "severity_judge_capped=true") {
      judgeCapped = true;
    } else if (ev === "severity_stale=true") {
      stale = true;
    }
  }
  if (!label) return null;
  return { label, value, judgeCapped, stale };
}

function maxSeverity(findings: Finding[]): ObjectionSeverity | null {
  let best: ObjectionSeverity | null = null;
  for (const f of findings || []) {
    const sev = parseSeverity(f);
    if (!sev || sev.stale) continue;
    if (
      !best ||
      objectionSeverityRank(sev.label) > objectionSeverityRank(best.label) ||
      (sev.label === best.label && sev.value > best.value)
    ) {
      best = sev;
    }
  }
  return best;
}

function evidenceMap(findings: Finding[]): Map<string, string> {
  // Provider metadata is encoded as `key=value` strings in the
  // evidence list of swarm-generated findings. We parse it once per
  // record so the render path doesn't have to walk strings.
  const map = new Map<string, string>();
  for (const f of findings || []) {
    for (const ev of f.evidence || []) {
      const idx = ev.indexOf("=");
      if (idx <= 0) continue;
      const key = ev.slice(0, idx).trim();
      const val = ev.slice(idx + 1).trim();
      if (!map.has(key)) map.set(key, val);
    }
  }
  return map;
}

function providerMeta(record: PeerReviewRecord): ProviderMeta {
  const ev = evidenceMap(record.findings);
  const fromName = record.reviewerName.startsWith("provider:")
    ? record.reviewerName.slice("provider:".length)
    : null;
  const provider = ev.get("provider") ?? fromName ?? null;
  const divergesRaw = ev.get("disagrees_with") ?? "";
  return {
    provider,
    model: ev.get("model") ?? null,
    divergesWith: divergesRaw ? divergesRaw.split(",").filter(Boolean) : [],
    swarmPartialReason: ev.get("swarm_partial") ?? null,
    swarmMonoculture: (ev.get("swarm_monoculture") ?? "") === "true",
  };
}

function sortRecordsBySeverity(records: PeerReviewRecord[]): PeerReviewRecord[] {
  // Highest severity first; records with no scored severity sink to
  // the bottom but keep their relative order (stable sort).
  return [...records].sort((a, b) => {
    const sa = maxSeverity(a.findings);
    const sb = maxSeverity(b.findings);
    const ra = sa ? objectionSeverityRank(sa.label) : -1;
    const rb = sb ? objectionSeverityRank(sb.label) : -1;
    if (ra !== rb) return rb - ra;
    const va = sa ? sa.value : 0;
    const vb = sb ? sb.value : 0;
    return vb - va;
  });
}

function groupByProvider(
  records: PeerReviewRecord[],
): { provider: string; records: PeerReviewRecord[] }[] {
  const groups = new Map<string, PeerReviewRecord[]>();
  for (const r of records) {
    const meta = providerMeta(r);
    const key = meta.provider ?? "heuristic";
    const arr = groups.get(key) ?? [];
    arr.push(r);
    groups.set(key, arr);
  }
  return Array.from(groups.entries()).map(([provider, records]) => ({
    provider,
    records,
  }));
}

export default async function PeerReviewPage({
  params,
  searchParams,
}: {
  params: Promise<{ conclusionId: string }>;
  searchParams: Promise<{ ledger?: string }>;
}) {
  // Tenant context is required here for two reasons: it verifies the
  // caller is still authenticated (same effect as the previous
  // `getFounder()` call), AND it hands us the `organizationId` we need
  // to forward into the tenant-scoped SQL below. `requireTenantContext`
  // calls `getFounder()` under the hood, so this is one round-trip, not
  // two.
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login");

  const { conclusionId } = await params;
  const sp = await searchParams;
  const reviews = await fetchPeerReviews(tenant.organizationId, conclusionId);

  const csvData = toCSV(
    reviews.map((r) => ({
      id: r.id,
      reviewerName: r.reviewerName,
      verdict: r.verdict,
      commentary: r.commentary,
      createdAt: r.createdAt,
    })),
  );

  async function runReview() {
    "use server";
    // Server action runs on the server; calling underlying helpers
    // directly avoids (a) a pointless HTTP round-trip to ourselves,
    // (b) the cookie-forwarding problem that broke auth on the old
    // self-fetch path, and (c) the PORTAL_API_BASE env dependency
    // that only worked on localhost.
    const founder = await getFounder();
    if (!founder) redirect("/login");

    const gate = await submitToRigorGate("peer_review.run", founderDisplayName(founder));
    if (!gate.approved) {
      redirect(
        `/peer-review/${conclusionId}?ledger=${encodeURIComponent(
          `rejected:${gate.reason || "rigor gate"}`,
        )}`,
      );
    }

    await callNoosphereJson(
      ["peer-review", "--conclusion-id", conclusionId],
      "Peer review run failed",
    );
    revalidatePath(`/peer-review/${conclusionId}`);
    redirect(`/peer-review/${conclusionId}?ledger=${gate.ledgerEntryId || "done"}`);
  }

  return (
    <main style={{ maxWidth: "960px", margin: "0 auto", padding: "3rem 2rem" }}>
      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          color: "var(--gold)",
          letterSpacing: "0.08em",
        }}
      >
        Peer review
      </h1>
      <p style={{ color: "var(--parchment-dim)", marginBottom: "0.5rem", fontSize: "0.9rem" }}>
        Reviews for conclusion{" "}
        <code style={{ color: "var(--gold-dim)" }}>{conclusionId.slice(0, 12)}…</code>
      </p>
      <div
        style={{
          fontSize: "0.75rem",
          color: "var(--parchment-dim)",
          marginBottom: "1rem",
          maxWidth: "44em",
          lineHeight: 1.6,
        }}
      >
        Automated reviewers assess this conclusion across methodological,
        evidential, and rhetorical dimensions.{" "}
        <span style={{ color: "var(--gold)" }}>Endorse</span> = conclusion
        stands,{" "}
        <span style={{ color: "var(--ember)" }}>Challenge</span> = issues
        found,{" "}
        <span style={{ color: "var(--parchment-dim)" }}>Abstain</span> =
        insufficient data to judge. Different from the{" "}
        <a href="/q/review" style={{ color: "var(--gold-dim)" }}>
          coherence review queue
        </a>
        , which evaluates pairs of claims rather than individual conclusions.
      </div>

      {sp.ledger && (
        <div
          className="portal-card"
          style={{
            padding: "0.6rem 1rem",
            marginBottom: "1rem",
            borderLeft: "3px solid var(--gold)",
            fontSize: "0.8rem",
            color: "var(--gold)",
          }}
        >
          Review recorded. Ledger entry: {sp.ledger}
        </div>
      )}

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem", flexWrap: "wrap" }}>
        <form action={runReview}>
          <button type="submit" className="btn-solid" style={{ fontSize: "0.65rem" }}>
            Run peer review
          </button>
        </form>
        <DownloadButton
          data={csvData}
          filename={`peer-review-${conclusionId.slice(0, 8)}.csv`}
          mime="text/csv"
          label="Download CSV"
          className="btn"
          style={{ fontSize: "0.65rem" }}
        />
        <DownloadButton
          data={JSON.stringify(reviews, null, 2)}
          filename={`peer-review-${conclusionId.slice(0, 8)}.json`}
          mime="application/json"
          label="Download JSON"
          className="btn"
          style={{ fontSize: "0.65rem" }}
        />
      </div>

      {reviews.length === 0 ? (
        <div className="portal-card" style={{ padding: "1rem 1.25rem", color: "var(--parchment-dim)" }}>
          No peer reviews recorded for this conclusion. Click &quot;Run peer review&quot; to trigger one.
        </div>
      ) : (
        <ProviderGroups records={reviews} />
      )}
    </main>
  );
}

function ProviderGroups({ records }: { records: PeerReviewRecord[] }) {
  const groups = groupByProvider(records);
  // The swarm-level flags are repeated on every multi-provider record;
  // we read them once off the first record that carries them.
  const swarmFlags = records.reduce<{
    monoculture: boolean;
    partialReason: string | null;
  }>(
    (acc, r) => {
      const meta = providerMeta(r);
      if (meta.swarmMonoculture) acc.monoculture = true;
      if (meta.swarmPartialReason && !acc.partialReason) {
        acc.partialReason = meta.swarmPartialReason;
      }
      return acc;
    },
    { monoculture: false, partialReason: null },
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      {(swarmFlags.monoculture || swarmFlags.partialReason) && (
        <div
          className="portal-card"
          style={{
            padding: "0.6rem 1rem",
            display: "flex",
            gap: "0.5rem",
            alignItems: "center",
            flexWrap: "wrap",
            fontSize: "0.7rem",
            color: "var(--parchment-dim)",
          }}
        >
          {swarmFlags.monoculture && (
            <SwarmDisagreementBadge tone="monoculture" />
          )}
          {swarmFlags.partialReason && (
            <SwarmDisagreementBadge
              tone="partial"
              partialReason={swarmFlags.partialReason}
            />
          )}
          <span>
            Treat this swarm output as informational only — diversity or
            completeness guarantees do not hold.
          </span>
        </div>
      )}

      {groups.map((g) => (
        <ProviderGroup key={g.provider} provider={g.provider} records={g.records} />
      ))}
    </div>
  );
}

function ProviderGroup({
  provider,
  records,
}: {
  provider: string;
  records: PeerReviewRecord[];
}) {
  const isHeuristic = provider === "heuristic";
  const label = isHeuristic ? "Heuristic reviewers" : `Provider · ${provider}`;
  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      <header
        style={{
          fontFamily: "'Cinzel', serif",
          fontSize: "0.75rem",
          letterSpacing: "0.12em",
          color: "var(--gold-dim)",
          textTransform: "uppercase",
        }}
      >
        {label}
      </header>
      <ul
        style={{
          listStyle: "none",
          padding: 0,
          margin: 0,
          display: "flex",
          flexDirection: "column",
          gap: "0.5rem",
        }}
      >
        {sortRecordsBySeverity(records).map((r) => {
          const meta = providerMeta(r);
          const sev = maxSeverity(r.findings);
          return (
            <li key={r.id} className="portal-card" style={{ padding: "1rem 1.25rem" }}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  flexWrap: "wrap",
                  gap: "0.5rem",
                  alignItems: "center",
                }}
              >
                <span style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                  <span style={{ fontSize: "0.75rem", color: "var(--parchment)" }}>
                    {r.reviewerName}
                  </span>
                  {meta.model && (
                    <span style={{ fontSize: "0.6rem", color: "var(--parchment-dim)" }}>
                      {meta.model}
                    </span>
                  )}
                  <SwarmDisagreementBadge divergesWith={meta.divergesWith} />
                  {sev && <SeverityChip severity={sev} />}
                </span>
                <span
                  style={{
                    fontSize: "0.65rem",
                    color: peerVerdictColor(r.verdict),
                    textTransform: "uppercase",
                  }}
                >
                  {r.verdict}
                </span>
              </div>
              <p style={{ marginTop: "0.5rem", color: "var(--parchment)", fontSize: "0.85rem" }}>
                {r.commentary}
              </p>
              <FindingsBlock findings={r.findings} />
              <div style={{ marginTop: "0.25rem", fontSize: "0.65rem", color: "var(--parchment-dim)" }}>
                {r.createdAt ? r.createdAt.slice(0, 16) : ""}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function SeverityChip({ severity }: { severity: ObjectionSeverity }) {
  const color = objectionSeverityColor(severity.label);
  return (
    <span
      title={
        `Objection severity ${severity.label} (${severity.value.toFixed(2)})` +
        (severity.judgeCapped ? " · judge estimate capped by structural ceiling" : "") +
        (severity.stale ? " · stale (conclusion revised)" : "")
      }
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.25rem",
        fontSize: "0.55rem",
        letterSpacing: "0.1em",
        textTransform: "uppercase",
        padding: "0.1rem 0.4rem",
        border: `1px solid ${color}`,
        color,
        opacity: severity.stale ? 0.5 : 1,
      }}
    >
      <span
        aria-hidden
        style={{
          width: `${Math.max(8, Math.min(40, severity.value * 40))}px`,
          height: "3px",
          background: color,
          display: "inline-block",
        }}
      />
      sev {severity.label}
      {severity.judgeCapped && <span title="judge capped">·c</span>}
    </span>
  );
}

function SeverityBar({ severity }: { severity: ObjectionSeverity }) {
  const color = objectionSeverityColor(severity.label);
  return (
    <div
      style={{
        marginTop: "0.25rem",
        display: "flex",
        alignItems: "center",
        gap: "0.4rem",
      }}
    >
      <div
        style={{
          flex: "1 1 auto",
          height: "4px",
          background: "var(--ink-soft, rgba(255,255,255,0.08))",
          borderRadius: "2px",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${Math.round(severity.value * 100)}%`,
            height: "100%",
            background: color,
            opacity: severity.stale ? 0.4 : 1,
          }}
        />
      </div>
      <span
        style={{
          fontSize: "0.55rem",
          color,
          textTransform: "uppercase",
          letterSpacing: "0.1em",
          minWidth: "5em",
          textAlign: "right",
        }}
      >
        {severity.label} {severity.value.toFixed(2)}
        {severity.stale ? " (stale)" : ""}
      </span>
    </div>
  );
}

function FindingsBlock({ findings }: { findings: Finding[] }) {
  if (!findings || findings.length === 0) return null;
  // Sort the findings inside the queue by severity. Findings without a
  // scored severity sink to the bottom but retain insertion order.
  const sorted = [...findings].sort((a, b) => {
    const sa = parseSeverity(a);
    const sb = parseSeverity(b);
    const ra = sa ? objectionSeverityRank(sa.label) : -1;
    const rb = sb ? objectionSeverityRank(sb.label) : -1;
    if (ra !== rb) return rb - ra;
    return (sb?.value ?? 0) - (sa?.value ?? 0);
  });
  const hasBlocker = findings.some((f) => f.severity === "blocker");
  return (
    <details style={{ marginTop: "0.5rem" }}>
      <summary
        style={{
          cursor: "pointer",
          fontSize: "0.7rem",
          color: "var(--parchment-dim)",
          letterSpacing: "0.08em",
        }}
      >
        {findings.length} finding{findings.length > 1 ? "s" : ""}
        {hasBlocker && " (includes blockers)"}
      </summary>
      <div style={{ marginTop: "0.35rem", display: "flex", flexDirection: "column", gap: "0.25rem" }}>
        {sorted.map((f, i) => {
          const sev = parseSeverity(f);
          return (
            <div
              key={i}
              style={{
                padding: "0.4rem 0.75rem",
                borderLeft: `2px solid ${severityColor(f.severity)}`,
                fontSize: "0.75rem",
              }}
            >
              <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                <span
                  style={{
                    color: severityColor(f.severity),
                    textTransform: "uppercase",
                    fontSize: "0.6rem",
                    letterSpacing: "0.1em",
                  }}
                >
                  {f.severity}
                </span>
                <span style={{ color: "var(--parchment-dim)", fontSize: "0.6rem" }}>
                  {f.category}
                </span>
              </div>
              <p style={{ color: "var(--parchment)", margin: "0.2rem 0" }}>{f.detail}</p>
              {sev && <SeverityBar severity={sev} />}
              {f.suggestedAction && (
                <p style={{ color: "var(--gold-dim)", fontSize: "0.7rem", fontStyle: "italic", margin: 0 }}>
                  Suggested: {f.suggestedAction}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </details>
  );
}
