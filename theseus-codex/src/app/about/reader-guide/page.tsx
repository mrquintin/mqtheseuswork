import type { Metadata } from "next";
import Link from "next/link";

import PublicHeader from "@/components/PublicHeader";
import ReaderTour from "@/components/ReaderTour";
import SubscribeForm from "@/components/SubscribeForm";
import { getFounder } from "@/lib/auth";
import {
  FAST_PATH_STEP_IDS,
  READER_GUIDE_STEPS,
  fastPathReadingMinutes,
  totalReadingMinutes,
  type ReaderGuideStep,
} from "@/lib/readerTour";

/**
 * Reader guide — the path for an outside reader.
 *
 * A serious researcher or financier landing on the site needs a route
 * from "what is this firm?" to "I understand what they claim and how I
 * would test it." This page is that route and nothing more: a seven-stop
 * reading map that indexes surfaces which already exist. It does not
 * restate the methodology explorer, the benchmark, or the replication
 * harness — it points at them, says how long each takes to read, and
 * gets out of the way.
 *
 * Every step is annotated with a reading time so a reader can pick the
 * depth they want; the fast path (steps 1, 3, 4, 5) is the shortest
 * route to the claim-and-test understanding. The optional "tour me"
 * overlay walks the same stops with a one-line note on each.
 */

export const dynamic = "force-dynamic";

const PAGE_DESCRIPTION =
  "A 30-minute reading map for outside readers: what Theseus claims, the criteria it holds itself to, the evidence it has published, and how to challenge or replicate it.";

export const metadata: Metadata = {
  title: "Reader guide · how to read Theseus",
  description: PAGE_DESCRIPTION,
  openGraph: {
    title: "Reader guide — how to read Theseus",
    description: PAGE_DESCRIPTION,
    type: "article",
  },
  twitter: {
    card: "summary",
    title: "Reader guide — how to read Theseus",
    description: PAGE_DESCRIPTION,
  },
};

export default async function ReaderGuidePage() {
  const founder = await getFounder();
  const total = totalReadingMinutes();
  const fast = fastPathReadingMinutes();

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main className="public-container public-methodology-page" id="reader-guide-main">
        <section className="public-section">
          <p className="mono" style={eyebrowStyle}>
            <Link href="/about">About</Link>
            <span aria-hidden> · </span>
            <span>Reader guide</span>
          </p>
          <h1 className="public-title">How to read Theseus</h1>
          <p className="public-lede">
            This is a reading map, not a summary. It will not tell you what
            Theseus concluded — the conclusions are on the surfaces themselves.
            It tells you the order to read those surfaces in so that, within
            roughly half an hour, you can say what the firm claims and how you
            would test it. Seven stops, each one pointing at a page that
            already exists, each annotated with how long that page takes.
          </p>

          <div className="public-card public-method-note" role="note" style={{ marginTop: "1.1rem" }}>
            <p style={{ margin: 0 }}>
              <strong>Full path:</strong> {total} minutes, all seven stops.{" "}
              <strong>Fast path:</strong> {fast} minutes — steps{" "}
              {FAST_PATH_STEP_IDS.map((id) => stepNumber(id)).join(", ")}, the
              shortest route to the claim and the test. Pick the depth you want;
              nothing here gates on reading all of it.
            </p>
          </div>

          <div style={{ marginTop: "1.25rem" }}>
            <ReaderTour />
          </div>
        </section>

        <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {READER_GUIDE_STEPS.map((step) => (
            <StepCard key={step.id} step={step} />
          ))}
        </ol>

        <section className="public-section" id="subscribe">
          <h2>Subscribe</h2>
          <p className="public-muted" style={{ marginTop: 0 }}>
            The last stop on the map. Following the firm is optional and changes
            nothing about your access — every surface in this guide is public.
          </p>
          <SubscribeForm
            intro="Get a digest when the firm publishes new theses, revisions, or retractions. Double opt-in, one-click unsubscribe, no tracking pixels."
            target={{ scope: "firm" }}
            title="Follow the firm"
          />
        </section>

        <section className="public-section">
          <h2>What this guide is not</h2>
          <div className="public-card public-method-note" role="note">
            <p style={{ margin: 0 }}>
              The guide indexes; it does not replace. It carries no conclusion,
              no score, and no claim the underlying surfaces do not already make
              for themselves. If a step's summary and the page it points at ever
              disagree, the page is correct. A printable version of this same
              map is kept at <code>docs/Reader_Guide.pdf</code> for readers and
              journalists who want it on paper.
            </p>
          </div>
        </section>
      </main>
    </>
  );
}

function StepCard({ step }: { step: ReaderGuideStep }) {
  return (
    <li
      className="public-card public-method-card"
      id={`step-${step.id}`}
      style={{ padding: "1.1rem 1.25rem", marginBottom: "1rem" }}
    >
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "0.75rem",
          justifyContent: "space-between",
          alignItems: "baseline",
        }}
      >
        <p className="mono public-muted" style={stepEyebrowStyle}>
          {step.eyebrow}
        </p>
        <p className="mono" style={readingTimeStyle} data-testid={`reading-time-${step.id}`}>
          {step.readingMinutes} min read
        </p>
      </div>
      <h2 style={{ margin: "0.15rem 0 0" }}>{step.title}</h2>
      <p style={{ marginBottom: "0.6rem" }}>{step.summary}</p>
      <ul style={linkRowStyle}>
        {step.links.map((link) => (
          <li key={link.href}>
            <Link
              href={link.href}
              rel={link.external ? "noreferrer" : undefined}
              style={linkChipStyle}
              target={link.external ? "_blank" : undefined}
            >
              {link.label} →
            </Link>
          </li>
        ))}
      </ul>
    </li>
  );
}

function stepNumber(id: string): number {
  const step = READER_GUIDE_STEPS.find((candidate) => candidate.id === id);
  return step ? step.index : 0;
}

const eyebrowStyle: React.CSSProperties = {
  fontSize: "0.6rem",
  letterSpacing: "0.22em",
  textTransform: "uppercase",
  color: "var(--public-muted, #888)",
};

const stepEyebrowStyle: React.CSSProperties = {
  fontSize: "0.62rem",
  letterSpacing: "0.2em",
  textTransform: "uppercase",
  margin: 0,
};

const readingTimeStyle: React.CSSProperties = {
  fontSize: "0.62rem",
  letterSpacing: "0.16em",
  textTransform: "uppercase",
  color: "var(--amber, #d4a017)",
  margin: 0,
};

const linkRowStyle: React.CSSProperties = {
  listStyle: "none",
  padding: 0,
  margin: 0,
  display: "flex",
  flexWrap: "wrap",
  gap: "0.5rem",
};

const linkChipStyle: React.CSSProperties = {
  display: "inline-block",
  fontSize: "0.78rem",
  letterSpacing: "0.04em",
  padding: "0.4rem 0.7rem",
  border: "1px solid var(--public-rule, #ddd)",
  borderRadius: 2,
  color: "var(--amber, #d4a017)",
  textDecoration: "none",
};
