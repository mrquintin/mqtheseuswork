import type { CSSProperties } from "react";
import type { Metadata } from "next";
import Link from "next/link";

import PublicHeader from "@/components/PublicHeader";
import {
  getTheseusContactEmail,
  theseusIdentity,
} from "@/content/theseusIdentity";
import { db } from "@/lib/db";
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
        <AxiomsSection />
        <ManifestoSection />
        <MembersSection hideMembers={hideMembers} members={members} />
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
      {theseusIdentity.aboutPage.sections.map((section) => (
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
      <h1 className="public-title">{theseusIdentity.aboutPage.whatHeading}</h1>
      <p style={paragraphStyle}>{theseusIdentity.whatIsTheseus.p1}</p>
      <p style={paragraphStyle}>{theseusIdentity.whatIsTheseus.p2}</p>
      <p style={paragraphStyle}>
        {theseusIdentity.intellectualCapitalDefinition}
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
        {theseusIdentity.axioms.map((axiom) => (
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
            {axiom.elaboration}
          </li>
        ))}
      </ol>
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

function MembersSection({
  hideMembers,
  members,
}: {
  hideMembers: boolean;
  members: PublicMember[];
}) {
  return (
    <section id="members" style={sectionStyle}>
      <h2 style={sectionHeadingStyle}>{theseusIdentity.members.heading}</h2>
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
