import type { Metadata } from "next";
import Link from "next/link";

import MethodologyIndexTable from "@/components/MethodologyIndexTable";
import { ReaderTrail } from "@/components/MethodCrossLinks";
import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";
import { buildMethodologyManifest } from "@/lib/methodologyManifest";
import { publicReviewWeekHint } from "@/lib/methodologyReviewWeek";

export const metadata: Metadata = {
  title: "Methodology",
  description:
    "Theseus's methodology explorer: methods, calibration, drift, composition, and failure modes — the firm's reasoning published for inspection and reuse.",
  openGraph: {
    title: "Theseus Methodology Explorer",
    description:
      "The reusable part of inquiry. Inspect Theseus's methods, their calibration, and where they have failed.",
    type: "website",
  },
};

export const dynamic = "force-dynamic";

/**
 * Public methodology directory — v2.
 *
 * The first version shipped the data as a table; v2 puts it in the order
 * a serious outside reader needs it. The page lands on three layers, in
 * order and clearly labelled:
 *
 *   Layer 1 — the meta-method: what the firm believes about inquiry.
 *             Never buried below the catalog.
 *   Layer 2 — the methods catalog with current status.
 *   Layer 3 — the empirical record: benchmark, calibration, tournament.
 *
 * Server-rendered: an outsider's first paint is the full hierarchy, not
 * a loading state. Client-side hydration only adds the catalog's search,
 * sort, and filter, and the optional reader trail — the layers, the
 * links, and the table content are all in the HTML.
 */
export default async function MethodologyPage() {
  const founder = await getFounder();
  const manifest = await buildMethodologyManifest();
  const reviewWeekHint = await publicReviewWeekHint();

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <a href="#methodology-index" className="public-skip-link">
        Skip to method catalog
      </a>
      <style>{skipLinkCss}</style>
      <style>{methodologyMobileCss}</style>
      <main id="methodology-main" className="public-container public-methodology-page">
        <section className="public-section" aria-labelledby="methodology-hero-title">
          <h1 id="methodology-hero-title" className="public-title">
            The reusable part of inquiry
          </h1>
          <p className="public-lede">
            Theseus publishes its conclusions, but the more durable public
            object is the discipline that produced them. This explorer is
            three layers deep, in order: what the firm believes about
            inquiry, the methods that belief produces, and the empirical
            record those methods have earned. Nothing here is private;
            everything is filtered for public visibility before it reaches
            this page.
          </p>
          <ReaderTrail />
          <p
            className="mono"
            aria-label="Methodology Review Week cadence"
            style={{
              marginTop: "1rem",
              fontSize: "0.7rem",
              letterSpacing: "0.15em",
              textTransform: "uppercase",
              color: "var(--public-muted, #888)",
            }}
          >
            {reviewWeekHint.text}
          </p>
          <p style={{ marginTop: "1.25rem" }}>
            <Link href="#methodology-index" className="mono" style={ctaLinkStyle}>
              Skip to the methods →
            </Link>
          </p>
        </section>

        {/* ---------- Layer 1 — the meta-method ---------- */}
        <section
          className="public-section"
          id="methodology-meta-method"
          aria-labelledby="methodology-meta-method-title"
        >
          <p className="mono" style={layerTagStyle}>
            Layer 1 — what the firm believes about inquiry
          </p>
          <h2 id="methodology-meta-method-title">The meta-method</h2>
          <p className="public-muted" style={{ marginTop: 0 }}>
            Before any single method, the firm holds a method for judging
            methods: five working criteria — Progressivity, Severity,
            Aim-Method Fit, Compressibility, Domain Sensitivity — applied to
            each method so a reader can see what it is, how it has
            calibrated, where it composes with other methods, and where it
            has failed. The three surfaces below are that meta-method made
            inspectable.
          </p>
          <ul style={routeGridStyle}>
            <RouteCard
              href="/methodology/criteria"
              label="Five-criterion rubric"
              body="The exact rubric the firm uses when scoring its own methods (the MQS), checked against the running scorer."
            />
            <RouteCard
              href="/methodology/composition"
              label="Composition map"
              body="How the methods build on each other — extractor → judge → synthesis — as a public-visible dependency graph."
            />
            <RouteCard
              href="/methodology/principles"
              label="Principles"
              body="The cross-domain claims the firm keeps re-deriving, conviction-weighted and linked back to the conclusions that produced them."
            />
          </ul>
        </section>

        {/* ---------- Layer 2 — the methods catalog ---------- */}
        <section
          className="public-section"
          id="methodology-index"
          aria-labelledby="methodology-index-title"
        >
          <p className="mono" style={layerTagStyle}>
            Layer 2 — the methods, with current status
          </p>
          <h2 id="methodology-index-title">The methods catalog</h2>
          <p className="public-muted" style={{ marginTop: 0 }}>
            Sortable. Filterable by domain. Status is the method's current
            standing; calibration slope is shown only for methods whose
            track record clears the firm's publish gate — below that, the
            cell is left blank instead of dressed up.
          </p>
          <MethodologyIndexTable methods={manifest.methods} />
        </section>

        {/* ---------- Layer 3 — the empirical record ---------- */}
        <section
          className="public-section"
          id="methodology-empirical-record"
          aria-labelledby="methodology-empirical-record-title"
        >
          <p className="mono" style={layerTagStyle}>
            Layer 3 — the empirical record the methods have earned
          </p>
          <h2 id="methodology-empirical-record-title">
            Benchmarks, calibration, and the tournament
          </h2>
          <p className="public-muted" style={{ marginTop: 0 }}>
            A method is only as good as its record. This layer is the
            evidence: the firm's first-run benchmark, the cross-model
            results, the adversarial tournament, and the published
            failure modes — plus the raw manifest for outside replication.
          </p>
          <ul style={routeGridStyle}>
            <RouteCard
              href="/methodology/benchmark/qh"
              label="Quintin Hypothesis benchmark"
              body="The firm's first-run benchmark — what the methods were tested against and how they scored."
            />
            <RouteCard
              href="/methodology/redteam"
              label="Red-team tournament"
              body="The adversarial tournament: methods set against each other to surface where each one breaks."
            />
            <RouteCard
              href="/methodology/replicate"
              label="Replicate the claims"
              body="The recipe for reproducing the firm's empirical claims from the published artifacts."
            />
            <RouteCard
              href="/api/public/methodology/manifest"
              label="Manifest API"
              body="A single JSON document — the same one this page reads — for outside replication."
            />
          </ul>

          <div
            id="methodology-failure-modes"
            className="public-card public-method-note"
            role="note"
            style={{ marginTop: "1.1rem" }}
          >
            <h3 style={{ marginTop: 0, fontSize: "0.95rem" }}>
              Public failure modes
            </h3>
            <p className="public-muted" style={{ marginBottom: 0 }}>
              {manifest.publicFailureModes.length} entries published across
              all methods. Each method's full catalog is reachable from its
              page; the firm holds private entries until the framing
              matures.
            </p>
          </div>
        </section>

        <section className="public-section" aria-labelledby="methodology-policy-title">
          <h2 id="methodology-policy-title">Public boundaries</h2>
          <div className="public-card public-method-note" role="note">
            <p>
              The explorer is deliberately incomplete in one respect: it does
              not expose raw deliberation, private transcript text, or
              unreviewed chain-of-thought. It exposes the method at the level
              needed for critique and reuse. Material revisions create a new
              immutable snapshot row so prior URLs do not rot.
            </p>
          </div>
        </section>
      </main>
    </>
  );
}

const ctaLinkStyle: React.CSSProperties = {
  display: "inline-block",
  padding: "0.55rem 1.1rem",
  border: "1px solid var(--amber, #d4a017)",
  color: "var(--amber, #d4a017)",
  textDecoration: "none",
  fontSize: "0.68rem",
  letterSpacing: "0.22em",
  textTransform: "uppercase",
};

const layerTagStyle: React.CSSProperties = {
  fontSize: "0.62rem",
  letterSpacing: "0.22em",
  textTransform: "uppercase",
  color: "var(--amber, #d4a017)",
  margin: "0 0 0.25rem",
};

const routeGridStyle: React.CSSProperties = {
  listStyle: "none",
  padding: 0,
  margin: "1rem 0 0",
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
  gap: "0.9rem",
};

function RouteCard({
  href,
  label,
  body,
}: {
  href: string;
  label: string;
  body: string;
}) {
  return (
    <li>
      <Link
        href={href}
        className="public-card public-method-card"
        style={{
          display: "block",
          textDecoration: "none",
          padding: "1rem 1.1rem",
          color: "inherit",
        }}
      >
        <div
          className="mono"
          style={{
            fontSize: "0.6rem",
            letterSpacing: "0.22em",
            textTransform: "uppercase",
            color: "var(--public-muted, #888)",
            marginBottom: "0.4rem",
          }}
        >
          {label}
        </div>
        <div style={{ fontSize: "0.92rem", lineHeight: 1.4 }}>{body}</div>
      </Link>
    </li>
  );
}

/**
 * Mobile methods catalog. The eight-column index table is unreadable
 * below ~700px — it either overflows the viewport or crushes every
 * column to a few characters. Under 720px the table reflows to one
 * bordered card per method: the header row is dropped and each cell
 * carries its column name inline via `data-label`. The desktop table
 * markup is untouched, so wide layouts do not regress.
 */
const methodologyMobileCss = `
@media (max-width: 720px) {
  .public-methodology-page .public-table thead {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
  }
  .public-methodology-page .public-table,
  .public-methodology-page .public-table tbody,
  .public-methodology-page .public-table tr,
  .public-methodology-page .public-table td {
    display: block;
    width: 100%;
  }
  .public-methodology-page .public-table-row {
    border: 1px solid var(--public-rule, #ddd);
    border-radius: 3px;
    margin: 0.7rem 0;
    padding: 0.35rem 0.7rem;
  }
  .public-methodology-page .public-table-row td {
    padding: 0.32rem 0 !important;
    border-top: 1px solid var(--public-rule, #eee);
    display: flex;
    gap: 0.9rem;
    align-items: baseline;
    justify-content: space-between;
    white-space: normal !important;
    max-width: none !important;
  }
  .public-methodology-page .public-table-row td:first-child {
    border-top: 0;
  }
  .public-methodology-page .public-table-row td::before {
    content: attr(data-label);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.6rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--public-muted, #888);
    flex: 0 0 auto;
  }
}
`;

const skipLinkCss = `
.public-skip-link {
  position: absolute;
  left: -9999px;
  top: 0;
  background: var(--amber, #d4a017);
  color: #000;
  padding: 0.5rem 0.85rem;
  z-index: 100;
}
.public-skip-link:focus {
  left: 1rem;
  top: 1rem;
  outline: 2px solid #000;
}
`;
