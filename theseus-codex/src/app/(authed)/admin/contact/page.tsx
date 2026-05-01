import Link from "next/link";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { db } from "@/lib/db";
import { canReadContactInbox } from "@/lib/roles";
import { requireTenantContext } from "@/lib/tenant";
import { toggleContactTriaged, updateContactNotes } from "./actions";

const PAGE_SIZE = 50;

type SearchParams = {
  page?: string;
  filter?: string;
};

export const dynamic = "force-dynamic";

export default async function ContactInboxPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const tenant = await requireTenantContext();
  if (!tenant) return null;
  if (!canReadContactInbox(tenant.role)) redirect("/dashboard");

  const sp = await searchParams;
  const filter = sp.filter === "untriaged" ? "untriaged" : "all";
  const page = parsePage(sp.page);
  const where = filter === "untriaged" ? { triagedAt: null } : {};
  const [submissions, total] = await Promise.all([
    db.contactSubmission.findMany({
      where,
      orderBy: { createdAt: "desc" },
      skip: (page - 1) * PAGE_SIZE,
      take: PAGE_SIZE,
    }),
    db.contactSubmission.count({ where }),
  ]);
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <main
      style={{
        maxWidth: "1080px",
        margin: "0 auto",
        padding: "3rem 2rem",
      }}
    >
      <header style={{ marginBottom: "1.6rem" }}>
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
          Inbox
        </h1>
        <p
          className="mono"
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.62rem",
            letterSpacing: "0.24em",
            margin: "0.35rem 0 0",
            textTransform: "uppercase",
          }}
        >
          Public contact submissions · {total}{" "}
          {filter === "untriaged" ? "untriaged" : "total"}
        </p>
      </header>

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "0.75rem",
          marginBottom: "1.2rem",
        }}
      >
        <FilterLink active={filter === "all"} href="/admin/contact">
          All
        </FilterLink>
        <FilterLink
          active={filter === "untriaged"}
          href="/admin/contact?filter=untriaged"
        >
          Untriaged only
        </FilterLink>
      </div>

      {submissions.length ? (
        <div style={{ display: "grid", gap: "0.8rem" }}>
          {submissions.map((submission) => (
            <details className="portal-card" key={submission.id}>
              <summary
                style={{
                  cursor: "pointer",
                  display: "grid",
                  gap: "0.65rem",
                  gridTemplateColumns:
                    "repeat(auto-fit, minmax(min(100%, 12rem), 1fr))",
                  listStyle: "none",
                }}
              >
                <span
                  className="mono"
                  style={{
                    color: "var(--parchment-dim)",
                    fontSize: "0.68rem",
                  }}
                  title={submission.createdAt.toISOString()}
                >
                  {formatTimestamp(submission.createdAt)}
                </span>
                <span style={{ minWidth: 0 }}>
                  <strong style={{ color: "var(--amber)" }}>
                    {submission.fromName}
                  </strong>
                  <br />
                  <a
                    className="mono"
                    href={`mailto:${submission.fromEmail}`}
                    style={{
                      color: "var(--parchment-dim)",
                      fontSize: "0.68rem",
                      overflowWrap: "anywhere",
                      textDecoration: "none",
                    }}
                  >
                    {submission.fromEmail}
                  </a>
                </span>
                <span
                  style={{
                    color: "var(--parchment)",
                    minWidth: 0,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {submission.subject?.trim() || truncate(submission.body, 80)}
                </span>
                <span
                  className="mono"
                  style={{
                    color: submission.triagedAt
                      ? "var(--success)"
                      : "var(--amber-dim)",
                    fontSize: "0.62rem",
                    letterSpacing: "0.14em",
                    textTransform: "uppercase",
                    whiteSpace: "nowrap",
                  }}
                >
                  {submission.triagedAt ? "Triaged" : "Untriaged"}
                </span>
              </summary>

              <div
                style={{
                  borderTop: "1px solid var(--border)",
                  display: "grid",
                  gap: "1rem",
                  marginTop: "1rem",
                  paddingTop: "1rem",
                }}
              >
                <p
                  style={{
                    color: "var(--parchment)",
                    lineHeight: 1.6,
                    margin: 0,
                    whiteSpace: "pre-wrap",
                  }}
                >
                  {submission.body}
                </p>

                <div
                  style={{
                    display: "grid",
                    gap: "0.9rem",
                    gridTemplateColumns:
                      "repeat(auto-fit, minmax(min(100%, 16rem), 1fr))",
                  }}
                >
                  <form action={toggleContactTriaged}>
                    <input name="id" type="hidden" value={submission.id} />
                    <input
                      name="triaged"
                      type="hidden"
                      value={submission.triagedAt ? "false" : "true"}
                    />
                    <button className="btn" type="submit">
                      {submission.triagedAt ? "Mark untriaged" : "Mark triaged"}
                    </button>
                    {submission.triagedAt ? (
                      <p
                        className="mono"
                        style={{
                          color: "var(--parchment-dim)",
                          fontSize: "0.65rem",
                          margin: "0.45rem 0 0",
                        }}
                      >
                        {submission.triagedAt.toISOString().slice(0, 16)}
                        {submission.triagedBy
                          ? ` by ${submission.triagedBy}`
                          : ""}
                      </p>
                    ) : null}
                  </form>

                  <form action={updateContactNotes}>
                    <input name="id" type="hidden" value={submission.id} />
                    <label
                      className="mono"
                      htmlFor={`notes-${submission.id}`}
                      style={{
                        color: "var(--parchment-dim)",
                        display: "block",
                        fontSize: "0.64rem",
                        letterSpacing: "0.14em",
                        marginBottom: "0.35rem",
                        textTransform: "uppercase",
                      }}
                    >
                      Internal note
                    </label>
                    <textarea
                      defaultValue={submission.notes ?? ""}
                      id={`notes-${submission.id}`}
                      maxLength={2000}
                      name="notes"
                      rows={3}
                    />
                    <button
                      className="btn"
                      style={{ marginTop: "0.55rem" }}
                      type="submit"
                    >
                      Save note
                    </button>
                  </form>
                </div>
              </div>
            </details>
          ))}
        </div>
      ) : (
        <div className="portal-card">
          <p style={{ color: "var(--parchment-dim)", margin: 0 }}>
            No contact submissions match this view.
          </p>
        </div>
      )}

      <Pagination filter={filter} page={page} totalPages={totalPages} />
    </main>
  );
}

function FilterLink({
  active,
  children,
  href,
}: {
  active: boolean;
  children: ReactNode;
  href: string;
}) {
  return (
    <Link
      className="btn"
      href={href}
      style={{
        background: active ? "var(--amber-dim)" : "transparent",
        color: active ? "var(--stone)" : "var(--amber)",
        textDecoration: "none",
      }}
    >
      {children}
    </Link>
  );
}

function Pagination({
  filter,
  page,
  totalPages,
}: {
  filter: "all" | "untriaged";
  page: number;
  totalPages: number;
}) {
  if (totalPages <= 1) return null;

  return (
    <nav
      aria-label="Contact inbox pagination"
      style={{
        alignItems: "center",
        display: "flex",
        gap: "0.75rem",
        justifyContent: "space-between",
        marginTop: "1.25rem",
      }}
    >
      <PageLink disabled={page <= 1} href={pageHref(filter, page - 1)}>
        Previous
      </PageLink>
      <span
        className="mono"
        style={{ color: "var(--parchment-dim)", fontSize: "0.72rem" }}
      >
        Page {page} of {totalPages}
      </span>
      <PageLink
        disabled={page >= totalPages}
        href={pageHref(filter, page + 1)}
      >
        Next
      </PageLink>
    </nav>
  );
}

function PageLink({
  children,
  disabled,
  href,
}: {
  children: ReactNode;
  disabled: boolean;
  href: string;
}) {
  if (disabled) {
    return (
      <span
        className="btn"
        style={{
          borderColor: "var(--amber-deep)",
          color: "var(--parchment-dim)",
          cursor: "default",
        }}
      >
        {children}
      </span>
    );
  }

  return (
    <Link className="btn" href={href} style={{ textDecoration: "none" }}>
      {children}
    </Link>
  );
}

function pageHref(filter: "all" | "untriaged", page: number): string {
  const params = new URLSearchParams();
  if (filter === "untriaged") params.set("filter", filter);
  if (page > 1) params.set("page", String(page));
  const query = params.toString();
  return query ? `/admin/contact?${query}` : "/admin/contact";
}

function parsePage(value: string | undefined): number {
  const page = Number.parseInt(value || "1", 10);
  return Number.isFinite(page) && page > 0 ? page : 1;
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
