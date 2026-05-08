import type { Metadata } from "next";
import Link from "next/link";

import MethodologyIndexTable from "@/components/MethodologyIndexTable";
import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";
import { buildMethodologyManifest } from "@/lib/methodologyManifest";

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
 * Public methodology directory.
 *
 * Server-rendered: an outsider's first paint is the full method index,
 * not a loading state. Client-side hydration only adds search,
 * sorting, and filtering — the table content itself is in the HTML.
 */
export default async function MethodologyPage() {
  const founder = await getFounder();
  const manifest = await buildMethodologyManifest();

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <a href="#methodology-index" className="public-skip-link">
        Skip to method index
      </a>
      <style>{skipLinkCss}</style>
      <main id="methodology-main" className="public-container public-methodology-page">
        <section className="public-section" aria-labelledby="methodology-hero-title">
          <h1 id="methodology-hero-title" className="public-title">
            The reusable part of inquiry
          </h1>
          <p className="public-lede">
            Theseus publishes its conclusions, but the more durable public
            object is the discipline that produced them. The meta-method is
            five working criteria — Progressivity, Severity, Aim-Method Fit,
            Compressibility, Domain Sensitivity — applied to each method so a
            reader can see what the method is, how it has calibrated, where
            it composes with other methods, and where it has failed. Nothing
            here is private; everything is filtered for public visibility
            before it reaches this page.
          </p>
          <p style={{ marginTop: "1.25rem" }}>
            <Link
              href="#methodology-index"
              className="mono"
              style={{
                display: "inline-block",
                padding: "0.55rem 1.1rem",
                border: "1px solid var(--amber, #d4a017)",
                color: "var(--amber, #d4a017)",
                textDecoration: "none",
                fontSize: "0.68rem",
                letterSpacing: "0.22em",
                textTransform: "uppercase",
              }}
            >
              Explore the methods →
            </Link>
          </p>
        </section>

        <section className="public-section" aria-labelledby="methodology-routes-title">
          <h2 id="methodology-routes-title">Where to start</h2>
          <ul
            style={{
              listStyle: "none",
              padding: 0,
              margin: 0,
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
              gap: "0.9rem",
            }}
          >
            <RouteCard
              href="/methodology/criteria"
              label="Five-criterion rubric"
              body="The exact rubric the firm uses when scoring its own methods (the MQS)."
            />
            <RouteCard
              href="/methodology/composition"
              label="Composition map"
              body="How the methods build on each other — extractor → judge → synthesis."
            />
            <RouteCard
              href="#methodology-failure-modes"
              label="Public failure modes"
              body="Catalog entries the firm is willing to publish about how its methods break."
            />
            <RouteCard
              href="/api/public/methodology/manifest"
              label="Manifest API"
              body="A single JSON document — the same one this page reads — for outside replication."
            />
          </ul>
        </section>

        <section
          className="public-section"
          id="methodology-index"
          aria-labelledby="methodology-index-title"
        >
          <h2 id="methodology-index-title">Method index</h2>
          <p className="public-muted" style={{ marginTop: 0 }}>
            Sortable. Filterable by domain. Calibration slope is shown only
            for methods whose track record clears the firm's publish gate;
            below that, the cell is left blank instead of dressed up.
          </p>
          <MethodologyIndexTable methods={manifest.methods} />
        </section>

        <section
          className="public-section"
          id="methodology-failure-modes"
          aria-labelledby="methodology-failure-modes-title"
        >
          <h2 id="methodology-failure-modes-title">Public failure modes</h2>
          <p className="public-muted">
            {manifest.publicFailureModes.length} entries published across all
            methods. Each method's full catalog is reachable from its
            page; the firm holds private entries until the framing matures.
          </p>
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
