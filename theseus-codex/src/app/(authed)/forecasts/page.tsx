import Link from "next/link";
import type { Metadata } from "next";

import { db } from "@/lib/db";
import { SITE } from "@/lib/site";
import { requireTenantContext } from "@/lib/tenant";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Theseus — Forecasts",
  description: "Forecasts hub: portfolio, operator console, and resolution audit.",
  openGraph: {
    description: "Forecasts hub: portfolio, operator console, and resolution audit.",
    siteName: "Theseus Codex",
    title: "Theseus — Forecasts",
    type: "website",
    url: `${SITE}/forecasts`,
  },
};

const VENUE_LABEL: Record<string, string> = {
  POLYMARKET: "Polymarket",
  KALSHI: "Kalshi",
};

const MISMATCH_LABEL: Record<string, string> = {
  OVERRIDE_DISAGREEMENT: "Venue disagrees with override",
  TARGET_DATE_MISMATCH: "Target-date mismatch",
};

function formatDate(value: Date | null | undefined): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(value);
}

export default async function ForecastsHubPage() {
  const tenant = await requireTenantContext();
  if (!tenant) return null;

  const [unresolvedCount, recentMismatches, recentOverrides] = await Promise.all([
    db.forecastPrediction.count({
      where: {
        organizationId: tenant.organizationId,
        status: "PUBLISHED",
        resolution: { is: null },
      },
    }),
    db.resolutionMismatch.findMany({
      where: {
        prediction: { organizationId: tenant.organizationId },
        reviewedAt: null,
      },
      orderBy: { createdAt: "desc" },
      take: 10,
      select: {
        id: true,
        predictionId: true,
        venue: true,
        venueOutcome: true,
        venueResolvedAt: true,
        kind: true,
        reason: true,
        createdAt: true,
      },
    }),
    db.resolutionOverride.findMany({
      where: { prediction: { organizationId: tenant.organizationId } },
      orderBy: { createdAt: "desc" },
      take: 10,
      select: {
        id: true,
        predictionId: true,
        outcome: true,
        resolvedAt: true,
        reason: true,
        founderId: true,
        citationUrl: true,
      },
    }),
  ]);

  return (
    <main className="mx-auto max-w-5xl space-y-10 p-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold">Forecasts</h1>
        <p className="text-sm text-muted-foreground">
          {unresolvedCount} published prediction{unresolvedCount === 1 ? "" : "s"} are still
          waiting on a resolution. The backfill driver closes this loop on a schedule;
          run it manually with{" "}
          <code className="rounded bg-muted px-1 py-0.5 text-xs">
            python -m noosphere forecasts backfill-resolutions
          </code>
          .
        </p>
        <nav className="flex gap-3 pt-2 text-sm">
          <Link className="underline" href="/forecasts/portfolio">
            Portfolio
          </Link>
          <Link className="underline" href="/forecasts/operator">
            Operator console
          </Link>
          <Link className="underline" href="/calibration">
            Public calibration
          </Link>
        </nav>
      </header>

      <section>
        <h2 className="text-lg font-semibold">
          Unresolved venue disagreements ({recentMismatches.length})
        </h2>
        <p className="text-sm text-muted-foreground">
          Each row signals either a venue/override conflict or a venue resolution
          that landed more than 7 days before the prediction&apos;s target date.
          Resolutions are <em>not</em> written for these — a human reviews and
          either records an override or marks the row reviewed.
        </p>
        {recentMismatches.length === 0 ? (
          <p className="mt-3 text-sm">No outstanding mismatches.</p>
        ) : (
          <table className="mt-3 w-full table-fixed text-sm">
            <thead>
              <tr className="text-left">
                <th className="w-32">Prediction</th>
                <th className="w-24">Venue</th>
                <th className="w-32">Kind</th>
                <th className="w-28">Venue outcome</th>
                <th className="w-40">Venue resolved at</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {recentMismatches.map((row) => (
                <tr key={row.id} className="border-t align-top">
                  <td className="truncate font-mono text-xs">{row.predictionId}</td>
                  <td>{VENUE_LABEL[row.venue] ?? row.venue}</td>
                  <td>{MISMATCH_LABEL[row.kind] ?? row.kind}</td>
                  <td>{row.venueOutcome}</td>
                  <td>{formatDate(row.venueResolvedAt)}</td>
                  <td className="break-words">{row.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section>
        <h2 className="text-lg font-semibold">
          Founder overrides ({recentOverrides.length})
        </h2>
        <p className="text-sm text-muted-foreground">
          Predictions that resolved off-venue (e.g. court rulings). Overrides
          win over the venue&apos;s reported resolution; venue disagreement is
          recorded above.
        </p>
        {recentOverrides.length === 0 ? (
          <p className="mt-3 text-sm">No overrides recorded.</p>
        ) : (
          <table className="mt-3 w-full table-fixed text-sm">
            <thead>
              <tr className="text-left">
                <th className="w-32">Prediction</th>
                <th className="w-24">Outcome</th>
                <th className="w-40">Resolved at</th>
                <th className="w-32">Founder</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {recentOverrides.map((row) => (
                <tr key={row.id} className="border-t align-top">
                  <td className="truncate font-mono text-xs">{row.predictionId}</td>
                  <td>{row.outcome}</td>
                  <td>{formatDate(row.resolvedAt)}</td>
                  <td className="truncate font-mono text-xs">{row.founderId}</td>
                  <td className="break-words">
                    {row.reason}
                    {row.citationUrl ? (
                      <>
                        {" "}
                        <a
                          className="underline"
                          href={row.citationUrl}
                          rel="noreferrer"
                          target="_blank"
                        >
                          [citation]
                        </a>
                      </>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
