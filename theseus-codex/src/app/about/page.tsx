import type { CSSProperties } from "react";
import type { Metadata } from "next";
import Link from "next/link";

import PublicHeader from "@/components/PublicHeader";
import {
  getTheseusContactEmail,
  theseusIdentity,
} from "@/content/theseusIdentity";
import { db } from "@/lib/db";
import {
  THESEUS_AXIOMS,
  THESEUS_BET_DOMAINS,
  THESEUS_LOGIC_VS_QUANT,
  THESEUS_NOT_COMMERCIAL,
  THESEUS_ONE_PARAGRAPH,
  THESEUS_PIPELINE_ASCII,
  THESEUS_TAGLINE,
} from "@/lib/copy/identity";
import ContactForm from "./ContactForm";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: theseusIdentity.aboutPage.metadataTitle,
};

type PublicMember = {
  id: string;
  name: string;
  displayName: string | null;
  roleTitle: string | null;
  bio: string | null;
  publicUrl: string | null;
};

const ABOUT_SECTIONS: ReadonlyArray<{ href: string; label: string }> = [
  { href: "#what", label: "What" },
  { href: "#principles", label: "Principles" },
  { href: "#renaissance", label: "Renaissance" },
  { href: "#axioms", label: "Axioms" },
  { href: "#not-saas", label: "Not SaaS" },
  { href: "#team", label: "Team" },
  { href: "#read", label: "Read" },
  { href: "#manifesto", label: "Manifesto" },
  { href: "#contact", label: "Contact" },
];

const sectionStyle: CSSProperties = {
  borderBottom: "1px solid var(--stroke, var(--border))",
  padding: "2rem 0",
  scrollMarginTop: "5.5rem",
};

const sectionHeadingStyle: CSSProperties = {
  color: "var(--amber)",
  fontSize: "clamp(1.25rem, 3vw, 1.75rem)",
  lineHeight: 1.2,
  margin: 0,
};

const paragraphStyle: CSSProperties = {
  color: "var(--parchment)",
  fontSize: "1.03rem",
  lineHeight: 1.65,
  margin: "0.75rem 0 0",
  maxWidth: "74ch",
};

const blockquoteStyle: CSSProperties = {
  borderLeft: "2px solid var(--amber-deep, var(--amber-dim))",
  color: "var(--parchment)",
  fontFamily: "'EB Garamond', serif",
  fontSize: "1.05rem",
  lineHeight: 1.6,
  margin: "1.1rem 0 0",
  maxWidth: "70ch",
  padding: "0.2rem 0 0.2rem 1rem",
};

const citationStyle: CSSProperties = {
  color: "var(--amber-dim)",
  display: "block",
  fontFamily: "inherit",
  fontSize: "0.78rem",
  letterSpacing: "0.08em",
  marginTop: "0.35rem",
};

export default async function AboutPage() {
  const hideMembers = shouldHideMembers();
  const members = hideMembers ? [] : await listPublicMembers();
  const contactEmail = configuredContactEmail();

  return (
    <>
      <PublicHeader authed={false} />
      <main
        className="public-container"
        style={{
          maxWidth: "960px",
          paddingBottom: "5rem",
        }}
      >
        <SectionNav />
        <WhatSection />
        <PrinciplesSection />
        <RenaissanceSection />
        <AxiomsSection />
        <NotSaasSection />
        <TeamSection hideMembers={hideMembers} members={members} />
        <ReadingGuideSection />
        <ManifestoSection />
        <ContactSection contactEmail={contactEmail} />
      </main>
    </>
  );
}

function SectionNav() {
  return (
    <nav
      aria-label={theseusIdentity.aboutPage.navAriaLabel}
      className="mono"
      style={{
        borderBottom: "1px solid var(--stroke, var(--border))",
        display: "flex",
        flexWrap: "wrap",
        gap: "0.75rem",
        paddingBottom: "1rem",
      }}
    >
      {ABOUT_SECTIONS.map((section) => (
        <Link
          href={section.href}
          key={section.href}
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.62rem",
            letterSpacing: "0.2em",
            textDecoration: "none",
            textTransform: "uppercase",
          }}
        >
          {section.label}
        </Link>
      ))}
    </nav>
  );
}

function WhatSection() {
  return (
    <section id="what" style={{ ...sectionStyle, paddingTop: "2.25rem" }}>
      <p
        className="mono"
        style={{
          color: "var(--amber-dim)",
          fontSize: "0.7rem",
          letterSpacing: "0.3em",
          margin: 0,
          textTransform: "uppercase",
        }}
      >
        {THESEUS_TAGLINE}
      </p>
      <h1 className="public-title" style={{ marginTop: "0.4rem" }}>
        What Theseus is
      </h1>
      <p style={paragraphStyle}>{THESEUS_ONE_PARAGRAPH}</p>
      <pre
        aria-label="Theseus pipeline diagram"
        className="mono"
        style={{
          background: "rgba(232, 225, 211, 0.035)",
          border: "1px solid rgba(232, 225, 211, 0.14)",
          borderRadius: "6px",
          color: "var(--parchment)",
          fontSize: "0.82rem",
          lineHeight: 1.55,
          margin: "1.2rem 0 0",
          overflowX: "auto",
          padding: "1.1rem 1.2rem",
          whiteSpace: "pre",
        }}
      >
{THESEUS_PIPELINE_ASCII}
      </pre>
    </section>
  );
}

function PrinciplesSection() {
  return (
    <section id="principles" style={sectionStyle}>
      <h2 style={sectionHeadingStyle}>Why principles, not data</h2>
      <p style={paragraphStyle}>
        A principle is a logical pattern abstracted from a text. It is
        the stable shape underneath an argument, expressible in a sentence
        or two, applicable to situations the original author never saw.
        Data has patterns too; quantitative firms extract them and trade
        them. Principles are the next layer up: patterns that organise
        many possible data series, rather than patterns inside one.
      </p>
      <p style={paragraphStyle}>
        Theseus reads a curated corpus the way Renaissance reads price
        tape. The synthesizer is the trainer; the principle is the fitted
        artifact; the algorithm is the live executor. When the algorithm
        fires on a fresh observation, the conclusion is just the
        principle applied — which is also why it can be argued with,
        replayed, and graded against what reality does next.
      </p>
      <blockquote style={blockquoteStyle}>
        “The Good… is the cause of knowledge and truth, and you may think
        of it as known.”
        <cite style={citationStyle}>— Plato, Republic 508e</cite>
      </blockquote>
      <p style={paragraphStyle}>
        The Platonic idea is the working metaphor: the principle is the
        Form, the live observation is the shadow, and the algorithm is
        the discipline of moving correctly between them.
      </p>
    </section>
  );
}

function RenaissanceSection() {
  return (
    <section id="renaissance" style={sectionStyle}>
      <h2 style={sectionHeadingStyle}>The Renaissance comparison</h2>
      <p style={paragraphStyle}>{THESEUS_LOGIC_VS_QUANT}</p>
      <p style={paragraphStyle}>
        Renaissance Technologies did not invent statistical learning;
        they industrialised one application of it. Theseus is not
        inventing logic; we are industrialising one application of it.
        The bet, when it comes, is the output of a machine — operating
        on logic instead of numbers. The bet is polymorphic across the
        domains where logic can be applied profitably:{" "}
        {THESEUS_BET_DOMAINS.join(", ")}.
      </p>
      <blockquote style={blockquoteStyle}>
        “To write between the lines.”
        <cite style={citationStyle}>
          — Leo Strauss, Persecution and the Art of Writing (1952)
        </cite>
      </blockquote>
      <p style={paragraphStyle}>
        The Strauss frame matters because principles often hide in the
        gap between what a text says and what it cannot say. The
        synthesizer is built to read both — the surface argument and the
        constraint that shaped it. The onion-futures example from the
        meeting: a quant sees price oscillation, but a reader who has
        worked through the corporate filings, the legislative record,
        and the speculator's incentives reads <em>why</em> — and that{" "}
        <em>why</em> is what the algorithm is trying to capture.
      </p>
    </section>
  );
}

function AxiomsSection() {
  return (
    <section id="axioms" style={sectionStyle}>
      <h2 style={sectionHeadingStyle}>
        {theseusIdentity.aboutPage.axiomsHeading}
      </h2>
      <ol
        style={{
          display: "grid",
          gap: "0.85rem",
          listStylePosition: "inside",
          margin: "1rem 0 0",
          padding: 0,
        }}
      >
        {THESEUS_AXIOMS.map((axiom) => (
          <li
            key={axiom.name}
            style={{
              background: "rgba(232, 225, 211, 0.035)",
              border: "1px solid rgba(232, 225, 211, 0.12)",
              borderRadius: "6px",
              color: "var(--parchment)",
              lineHeight: 1.55,
              padding: "1rem",
            }}
          >
            <strong style={{ color: "var(--amber)" }}>{axiom.name}.</strong>{" "}
            <span className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.7rem", letterSpacing: "0.16em", textTransform: "uppercase" }}>
              {axiom.summary}
            </span>{" "}
            {axiom.elaboration}
          </li>
        ))}
      </ol>
    </section>
  );
}

function NotSaasSection() {
  return (
    <section id="not-saas" style={sectionStyle}>
      <h2 style={sectionHeadingStyle}>Why we are not commercialising this</h2>
      <p style={paragraphStyle}>{THESEUS_NOT_COMMERCIAL}</p>
      <p style={paragraphStyle}>
        A SaaS distribution would force a single workflow on every buyer
        and would expose the corpus, the principle library, and the
        algorithm internals to anyone with a credit card. The machine is
        valuable in proportion to how much of the firm's specific
        reading has been encoded into it; selling shells of that would
        commodify the surface and erode the edge. We invest with the
        machine. We do not sell access to it.
      </p>
      <blockquote style={blockquoteStyle}>
        “What appears to humanity as the history of capitalism is an
        invasion from the future by an artificial intelligent space that
        must assemble itself entirely from its enemy's resources.”
        <cite style={citationStyle}>
          — Nick Land, Fanged Noumena (2011)
        </cite>
      </blockquote>
      <p style={paragraphStyle}>
        The Land frame is the warning: a machine that assembles itself
        from its enemy's resources only retains its edge while the
        machine itself is not the resource. The corpus, the synthesizer,
        the principle library, and the algorithm registry are the
        machine. They stay inside.
      </p>
    </section>
  );
}

function TeamSection({
  hideMembers,
  members,
}: {
  hideMembers: boolean;
  members: PublicMember[];
}) {
  return (
    <section id="team" style={sectionStyle}>
      <h2 style={sectionHeadingStyle}>The team</h2>
      {hideMembers ? (
        <p style={paragraphStyle}>{theseusIdentity.members.hiddenMessage}</p>
      ) : members.length ? (
        <div
          style={{
            display: "grid",
            gap: "0.9rem",
            gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
            marginTop: "1rem",
          }}
        >
          {members.map((member) => (
            <article
              key={member.id}
              style={{
                background: "rgba(232, 225, 211, 0.035)",
                border: "1px solid rgba(232, 225, 211, 0.14)",
                borderRadius: "6px",
                padding: "1rem",
              }}
            >
              <h3
                style={{
                  color: "var(--amber)",
                  fontSize: "1.05rem",
                  lineHeight: 1.25,
                  margin: 0,
                }}
              >
                {member.displayName?.trim() || member.name}
              </h3>
              {member.roleTitle?.trim() ? (
                <p
                  className="mono"
                  style={{
                    color: "var(--amber-dim)",
                    fontSize: "0.62rem",
                    letterSpacing: "0.16em",
                    margin: "0.35rem 0 0",
                    textTransform: "uppercase",
                  }}
                >
                  {member.roleTitle}
                </p>
              ) : null}
              <p
                style={{
                  color: "var(--parchment-dim)",
                  fontSize: "0.95rem",
                  lineHeight: 1.55,
                  margin: "0.7rem 0 0",
                }}
              >
                {member.bio}
              </p>
              {member.publicUrl ? (
                <Link
                  className="mono"
                  href={member.publicUrl}
                  rel="noreferrer"
                  style={{
                    color: "var(--amber)",
                    display: "inline-flex",
                    fontSize: "0.62rem",
                    letterSpacing: "0.16em",
                    marginTop: "0.75rem",
                    textDecoration: "none",
                    textTransform: "uppercase",
                  }}
                  target="_blank"
                >
                  {formatPublicUrlLabel(member.publicUrl)}
                </Link>
              ) : null}
            </article>
          ))}
        </div>
      ) : (
        <p style={paragraphStyle}>{theseusIdentity.members.emptyMessage}</p>
      )}
    </section>
  );
}

function ReadingGuideSection() {
  const surfaces = [
    {
      href: "/currents",
      title: "Currents",
      body: "Live signals — usually X posts — that crossed the firm's significance and relevance floors, with the principle-derived opinion in response.",
    },
    {
      href: "/forecasts",
      title: "Forecasts",
      body: "Prediction-market questions the firm has taken a position on. Each forecast carries the implied bet and is graded on settlement.",
    },
    {
      href: "/memos",
      title: "Memos",
      body: "Investment memos the firm has chosen to publish. The full 10-section format: TL;DR, governing principles, observed inputs, reasoning chain, implied bet, provenance.",
    },
    {
      href: "/algorithms",
      title: "Algorithms",
      body: "Every logical algorithm currently running, its source principles, its recent invocations, and its calibration record.",
    },
    {
      href: "/principles",
      title: "Principles",
      body: "The corpus-derived principle library. Each principle links back to the texts it was extracted from and the algorithms it underwrites.",
    },
    {
      href: "/knowledge-graph",
      title: "Knowledge graph",
      body: "The full graph: principles, algorithms, invocations, memos, sources. The same graph the synthesizer reasons over, made browsable.",
    },
  ];
  return (
    <section id="read" style={sectionStyle}>
      <h2 style={sectionHeadingStyle}>How to read the public surfaces</h2>
      <p style={paragraphStyle}>
        Each public surface shows one cut of the same machine.
      </p>
      <div
        style={{
          display: "grid",
          gap: "0.85rem",
          gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
          marginTop: "1rem",
        }}
      >
        {surfaces.map((surface) => (
          <Link
            href={surface.href}
            key={surface.href}
            style={{
              background: "rgba(232, 225, 211, 0.035)",
              border: "1px solid rgba(232, 225, 211, 0.14)",
              borderRadius: "6px",
              color: "inherit",
              display: "block",
              padding: "1rem",
              textDecoration: "none",
            }}
          >
            <strong
              style={{
                color: "var(--amber)",
                display: "block",
                fontFamily: "'Cinzel', serif",
                letterSpacing: "0.03em",
                marginBottom: "0.5rem",
              }}
            >
              {surface.title}
            </strong>
            <span
              style={{
                color: "var(--parchment-dim)",
                display: "block",
                fontSize: "0.94rem",
                lineHeight: 1.5,
              }}
            >
              {surface.body}
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}

function ManifestoSection() {
  const paragraphs = theseusIdentity.manifesto.body.split(/\n{2,}/);

  return (
    <section id="manifesto" style={sectionStyle}>
      <h2 style={sectionHeadingStyle}>{theseusIdentity.manifesto.title}</h2>
      {paragraphs.map((paragraph) => (
        <p key={paragraph} style={paragraphStyle}>
          {paragraph}
        </p>
      ))}
      <FurtherReading />
    </section>
  );
}

function FurtherReading() {
  return (
    <div
      style={{
        marginTop: "1.35rem",
      }}
    >
      <h3
        className="mono"
        style={{
          color: "var(--amber-dim)",
          fontSize: "0.68rem",
          letterSpacing: "0.22em",
          margin: "0 0 0.7rem",
          textTransform: "uppercase",
        }}
      >
        {theseusIdentity.furtherReading.heading}
      </h3>
      <ul
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "0.75rem",
          listStyle: "none",
          margin: 0,
          padding: 0,
        }}
      >
        {theseusIdentity.furtherReading.items.map((item) => {
          const external = item.href.startsWith("http");
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                rel={external ? "noreferrer" : undefined}
                style={{
                  border: "1px solid var(--amber-deep)",
                  borderRadius: "4px",
                  color: "var(--amber)",
                  display: "inline-flex",
                  fontSize: "0.9rem",
                  lineHeight: 1.35,
                  padding: "0.5rem 0.7rem",
                  textDecoration: "none",
                }}
                target={external ? "_blank" : undefined}
              >
                {item.title}
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function ContactSection({ contactEmail }: { contactEmail: string }) {
  const form = theseusIdentity.contactSection.form;

  return (
    <section id="contact" style={{ ...sectionStyle, borderBottom: 0 }}>
      <h2 style={sectionHeadingStyle}>{theseusIdentity.contactSection.heading}</h2>
      <p style={paragraphStyle}>
        {theseusIdentity.contactSection.line}{" "}
        <a
          href={`mailto:${contactEmail}`}
          style={{
            color: "var(--amber)",
            textDecoration: "underline",
            textDecorationThickness: "0.08em",
            textUnderlineOffset: "0.16em",
          }}
        >
          {contactEmail}
        </a>
        .
      </p>
      <ContactForm
        contactEmail={contactEmail}
        disclosure={theseusIdentity.contactSection.disclosure}
        form={form}
      />
    </section>
  );
}

async function listPublicMembers(): Promise<PublicMember[]> {
  try {
    const rows = await db.founder.findMany({
      where: {
        role: { in: ["admin", "founder"] },
        bio: { not: null },
      },
      orderBy: [{ createdAt: "asc" }, { name: "asc" }],
      select: {
        id: true,
        name: true,
        displayName: true,
        roleTitle: true,
        bio: true,
        publicUrl: true,
      },
    });

    return rows
      .filter((member) => Boolean(member.bio?.trim()))
      .map((member) => ({
        ...member,
        publicUrl: normalizedPublicUrl(member.publicUrl),
      }));
  } catch (error) {
    console.error("about_members_query_failed", error);
    return [];
  }
}

function configuredContactEmail(): string {
  return getTheseusContactEmail();
}

function shouldHideMembers(): boolean {
  return process.env.NEXT_PUBLIC_ABOUT_HIDE_MEMBERS === "true";
}

function normalizedPublicUrl(value: string | null): string | null {
  const trimmed = value?.trim();
  if (!trimmed) return null;

  try {
    const url = new URL(trimmed);
    if (url.protocol !== "https:" && url.protocol !== "http:") return null;
    return url.toString();
  } catch {
    return null;
  }
}

function formatPublicUrlLabel(value: string): string {
  try {
    const url = new URL(value);
    return url.hostname.replace(/^www\./, "") || theseusIdentity.members.linkLabel;
  } catch {
    return theseusIdentity.members.linkLabel;
  }
}
