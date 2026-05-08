import Link from "next/link";
import type { CSSProperties } from "react";

import { markPublicResponseSeen } from "./actions";
import { db } from "@/lib/db";
import { parsePublicationPayload } from "@/lib/conclusionsRead";
import { requireTenantContext } from "@/lib/tenant";

export const dynamic = "force-dynamic";

type ResponseRow = {
  id: string;
  kind: string;
  body: string;
  citationUrl: string;
  submitterEmail: string;
  orcid: string;
  pseudonymous: boolean;
  status: string;
  createdAt: Date;
  seenAt: Date | null;
  published: {
    slug: string;
    version: number;
    payloadJson: string;
  };
};

export default async function ResponsesInboxPage() {
  const tenant = await requireTenantContext();
  if (!tenant) return null;

  const responses = (await db.publicResponse.findMany({
    where: { organizationId: tenant.organizationId },
    orderBy: { createdAt: "desc" },
    take: 100,
    include: {
      published: {
        select: {
          slug: true,
          version: true,
          payloadJson: true,
        },
      },
    },
  })) as ResponseRow[];

  const unseenCount = responses.filter((response) => !response.seenAt).length;

  return (
    <main
      style={{
        maxWidth: "1180px",
        margin: "0 auto",
        padding: "3rem 2rem",
      }}
    >
      <header style={{ marginBottom: "1.4rem" }}>
        <h1
          style={{
            fontFamily: "'Cinzel Decorative', 'Cinzel', serif",
            fontSize: "1.8rem",
            letterSpacing: "0.18em",
            color: "var(--amber)",
            textShadow: "var(--glow-md)",
            margin: 0,
          }}
        >
          Responses
        </h1>
        <p
          className="mono"
          style={{
            alignItems: "center",
            color: "var(--amber-dim)",
            display: "inline-flex",
            fontSize: "0.62rem",
            gap: "0.5rem",
            letterSpacing: "0.24em",
            margin: "0.35rem 0 0",
            textTransform: "uppercase",
          }}
        >
          Structured public responses - {responses.length} total
          {unseenCount ? (
            <span
              style={{
                alignItems: "center",
                display: "inline-flex",
                gap: "0.35rem",
              }}
            >
              <span aria-hidden className="currents-pulse" />
              {unseenCount} unseen
            </span>
          ) : null}
        </p>
      </header>

      {responses.length ? (
        <div style={{ overflowX: "auto" }}>
          <table
            style={{
              borderCollapse: "collapse",
              color: "var(--parchment)",
              minWidth: "980px",
              width: "100%",
            }}
          >
            <thead>
              <tr>
                {["Date", "Respondent", "Kind", "Conclusion", "Body excerpt", "Seen"].map((label) => (
                  <th
                    className="mono"
                    key={label}
                    scope="col"
                    style={{
                      borderBottom: "1px solid var(--border)",
                      color: "var(--amber-dim)",
                      fontSize: "0.62rem",
                      letterSpacing: "0.16em",
                      padding: "0.7rem 0.8rem",
                      textAlign: "left",
                      textTransform: "uppercase",
                    }}
                  >
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {responses.map((response) => {
                const title = conclusionTitle(response);
                return (
                  <tr key={response.id}>
                    <td style={cellStyle} title={response.createdAt.toISOString()}>
                      <span className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.68rem" }}>
                        {formatTimestamp(response.createdAt)}
                      </span>
                    </td>
                    <td style={cellStyle}>{respondentLabel(response)}</td>
                    <td style={cellStyle}>
                      <span className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.68rem" }}>
                        {response.kind}
                      </span>
                    </td>
                    <td style={{ ...cellStyle, maxWidth: "16rem" }}>
                      <Link
                        href={`/c/${encodeURIComponent(response.published.slug)}/v/${response.published.version}`}
                        style={{
                          color: "var(--amber)",
                          textDecoration: "none",
                        }}
                      >
                        {title}
                      </Link>
                    </td>
                    <td style={{ ...cellStyle, maxWidth: "24rem" }}>
                      <details>
                        <summary style={{ cursor: "pointer" }}>
                          {truncate(response.body, 150)}
                        </summary>
                        <p
                          style={{
                            color: "var(--parchment)",
                            lineHeight: 1.55,
                            margin: "0.65rem 0 0",
                            whiteSpace: "pre-wrap",
                          }}
                        >
                          {response.body}
                        </p>
                        {response.citationUrl ? (
                          <a
                            className="mono"
                            href={response.citationUrl}
                            rel="noreferrer"
                            target="_blank"
                            style={{
                              color: "var(--amber-dim)",
                              display: "inline-block",
                              fontSize: "0.65rem",
                              marginTop: "0.5rem",
                              overflowWrap: "anywhere",
                              textDecoration: "none",
                            }}
                          >
                            {response.citationUrl}
                          </a>
                        ) : null}
                      </details>
                    </td>
                    <td style={cellStyle}>
                      <form action={markPublicResponseSeen}>
                        <input name="id" type="hidden" value={response.id} />
                        <input name="seen" type="hidden" value={response.seenAt ? "true" : "false"} />
                        <button className="btn" type="submit">
                          {response.seenAt ? "Mark unseen" : "Mark seen"}
                        </button>
                        {response.seenAt ? (
                          <p
                            className="mono"
                            style={{
                              color: "var(--success)",
                              fontSize: "0.62rem",
                              margin: "0.45rem 0 0",
                            }}
                          >
                            {response.seenAt.toISOString().slice(0, 16)}
                          </p>
                        ) : null}
                      </form>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="portal-card">
          <p style={{ color: "var(--parchment-dim)", margin: 0 }}>
            No structured public responses have arrived yet.
          </p>
        </div>
      )}
    </main>
  );
}

const cellStyle = {
  borderBottom: "1px solid var(--border)",
  padding: "0.85rem 0.8rem",
  verticalAlign: "top",
} satisfies CSSProperties;

function conclusionTitle(response: ResponseRow): string {
  return parsePublicationPayload({
    payloadJson: response.published.payloadJson,
    slug: response.published.slug,
  }).conclusionText;
}

function respondentLabel(response: ResponseRow): string {
  if (response.pseudonymous) {
    return response.orcid
      ? `Pseudonymous - ORCID ${response.orcid}`
      : "Pseudonymous";
  }
  return response.orcid
    ? `${response.submitterEmail} - ORCID ${response.orcid}`
    : response.submitterEmail;
}

function truncate(value: string, maxLength: number): string {
  const flat = value.replace(/\s+/g, " ").trim();
  if (flat.length <= maxLength) return flat;
  return `${flat.slice(0, maxLength - 1)}...`;
}

function formatTimestamp(value: Date): string {
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(value);
}
