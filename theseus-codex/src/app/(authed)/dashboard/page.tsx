import Link from "next/link";
import ConfidenceTierSigil from "@/components/ConfidenceTierSigil";
import SculptureBackdrop from "@/components/SculptureBackdrop";
import RetryProcessingButton from "@/components/RetryProcessingButton";
import AutoProcessStatusBanner from "@/components/AutoProcessStatusBanner";
import PublishToggle from "@/components/PublishToggle";
import { db } from "@/lib/db";
import { requireTenantContext } from "@/lib/tenant";

/**
 * Dashboard — landing page after login.
 *
 * Patron sculpture: **Hercules (Louvre)**, rendered huge and dim on the
 * right side of the page. A viewer sees Hercules and the UI content
 * simultaneously — the strength and discipline of the firm, and its
 * current intellectual metabolism.
 */

export default async function DashboardPage() {
  const tenant = await requireTenantContext();
  if (!tenant) {
    return null;
  }

  const uploads = await db.upload.findMany({
    where: {
      organizationId: tenant.organizationId,
      deletedAt: null,
      // Same rule as the library: you always see your own rows, but
      // peers' private rows are hidden from you. Without this filter
      // the dashboard would happily show "12 recent contributions"
      // including peers' private uploads that `/library` hides, which
      // would be a leak.
      OR: [
        { visibility: { not: "private" } },
        { founderId: tenant.founderId },
      ],
    },
    orderBy: { createdAt: "desc" },
    take: 12,
    include: { founder: { select: { name: true } } },
  });

  // Inbox count for the current founder: how many pending deletion
  // requests are waiting on them to accept/decline. Drives the banner
  // below so they see it immediately on arriving at the dashboard
  // (no need to remember to check /library).
  const pendingRequestCount = await db.deletionRequest.count({
    where: {
      status: "pending",
      upload: {
        organizationId: tenant.organizationId,
        founderId: tenant.founderId,
        deletedAt: null,
      },
    },
  });

  const conclusions = await db.conclusion.findMany({
    where: { organizationId: tenant.organizationId },
    orderBy: { createdAt: "desc" },
    take: 8,
  });

  const drifts = await db.driftEvent.findMany({
    where: { organizationId: tenant.organizationId },
    orderBy: { observedAt: "desc" },
    take: 6,
  });

  const activeUploads =
    uploads.filter((u) => u.status === "processing" || u.status === "pending").length +
    uploads.filter((u) => u.status === "queued_offline").length * 0.5;

  const statusBadge = (status: string) => {
    const cls: Record<string, string> = {
      pending: "badge-pending",
      processing: "badge-processing",
      queued_offline: "badge-pending",
      ingested: "badge-ingested",
      failed: "badge-failed",
    };
    return `badge ${cls[status] || "badge-pending"}`;
  };

  return (
    <div style={{ position: "relative", overflow: "hidden", minHeight: "80vh" }}>
      <SculptureBackdrop src="/sculptures/hercules.mesh.bin" side="right" />

      <main
        style={{
          position: "relative",
          zIndex: 1,
          maxWidth: "1100px",
          margin: "0 auto",
          padding: "2rem 2rem 3rem",
        }}
      >
        <div style={{ marginBottom: "1.5rem" }}>
          <h1
            style={{
              fontFamily: "'Cinzel Decorative', 'Cinzel', serif",
              fontSize: "2rem",
              letterSpacing: "0.18em",
              color: "var(--amber)",
              textShadow: "var(--glow-md)",
              margin: 0,
            }}
          >
            Forum
          </h1>
          <p
            className="mono"
            style={{
              fontSize: "0.62rem",
              letterSpacing: "0.28em",
              textTransform: "uppercase",
              color: "var(--amber-dim)",
              marginTop: "0.25rem",
              marginBottom: 0,
            }}
          >
            Hercules, Louvre · Fortitudine et disciplina
          </p>
          <p
            style={{
              fontFamily: "'EB Garamond', serif",
              fontStyle: "italic",
              fontSize: "1rem",
              color: "var(--parchment-dim)",
              marginTop: "0.45rem",
              marginBottom: 0,
              maxWidth: "44em",
              lineHeight: 1.55,
            }}
          >
            {activeUploads > 0
              ? `${Math.ceil(activeUploads)} contribution${activeUploads > 1.5 ? "s" : ""} in motion.`
              : "The labours rest; the firm listens."}
          </p>
        </div>

        <AutoProcessStatusBanner />

        {pendingRequestCount > 0 ? (
          <Link
            href="/library#requests"
            style={{ textDecoration: "none", display: "block" }}
          >
            <div
              className="portal-card"
              style={{
                border: "1px solid var(--amber)",
                background:
                  "linear-gradient(180deg, rgba(212,160,23,0.10), rgba(212,160,23,0.03))",
                padding: "0.9rem 1.1rem",
                marginBottom: "1.5rem",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: "1rem",
                transition: "border-color 0.2s ease",
              }}
            >
              <span
                className="mono"
                style={{
                  color: "var(--amber)",
                  fontSize: "0.62rem",
                  letterSpacing: "0.28em",
                  textTransform: "uppercase",
                }}
              >
                ⚠ {pendingRequestCount} deletion request
                {pendingRequestCount === 1 ? "" : "s"} awaiting your decision
              </span>
              <span
                className="mono"
                style={{
                  color: "var(--amber-dim)",
                  fontSize: "0.6rem",
                  letterSpacing: "0.22em",
                  textTransform: "uppercase",
                }}
              >
                Review →
              </span>
            </div>
          </Link>
        ) : null}

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            alignItems: "center",
            marginBottom: "1.25rem",
            gap: "0.75rem",
          }}
        >
          <Link href="/library" className="btn">
            Library
          </Link>
          <Link href="/upload" className="btn-solid btn">
            Upload
          </Link>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "1.5rem",
          }}
        >
          <section
            className="ascii-frame"
            data-label={`UPLOADS · ${toRoman(uploads.length) || "0"}`}
          >
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {uploads.length === 0 ? (
                <LatinEmpty
                  latin="Scriba exspectat."
                  english="The scribe awaits — nothing uploaded yet."
                />
              ) : (
                uploads.map((u) => (
                  <div key={u.id} className="portal-card" style={{ padding: "0.9rem 1rem" }}>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        gap: "1rem",
                        alignItems: "flex-start",
                      }}
                    >
                      <div style={{ minWidth: 0 }}>
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "0.45rem",
                            overflow: "hidden",
                          }}
                        >
                          <span
                            style={{
                              fontFamily: "'EB Garamond', serif",
                              color: "var(--parchment)",
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {u.title}
                          </span>
                          {u.visibility === "private" ? (
                            <span
                              className="mono"
                              title="Private — only you see this row. Noosphere still analyses it."
                              style={{
                                fontSize: "0.5rem",
                                letterSpacing: "0.22em",
                                textTransform: "uppercase",
                                color: "var(--amber)",
                                border: "1px solid var(--amber-dim)",
                                padding: "0.08rem 0.38rem",
                                borderRadius: "2px",
                                flexShrink: 0,
                              }}
                            >
                              Private
                            </span>
                          ) : null}
                        </div>
                        <div
                          className="mono"
                          style={{
                            fontSize: "0.65rem",
                            color: "var(--parchment-dim)",
                            marginTop: "0.25rem",
                          }}
                        >
                          {u.founder.name} · {new Date(u.createdAt).toLocaleDateString()}
                        </div>
                      </div>
                      <div
                        style={{
                          display: "flex",
                          gap: "0.5rem",
                          alignItems: "center",
                          flexShrink: 0,
                          flexWrap: "wrap",
                          justifyContent: "flex-end",
                        }}
                      >
                        <PublishToggle
                          uploadId={u.id}
                          initialPublishedAt={u.publishedAt}
                          initialSlug={u.slug}
                        />
                        <RetryProcessingButton
                          uploadId={u.id}
                          status={u.status}
                        />
                        <span className={statusBadge(u.status)}>
                          {u.status.replace("_", " ")}
                        </span>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>

          <section
            className="ascii-frame"
            data-label={`CONCLUSIONS · ${toRoman(conclusions.length) || "0"}`}
          >
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {conclusions.length === 0 ? (
                <LatinEmpty
                  latin="Adhuc nihil firmandum."
                  english="Nothing yet for the firm to affirm."
                />
              ) : (
                conclusions.map((c) => (
                  <div key={c.id} className="portal-card" style={{ padding: "0.9rem 1rem" }}>
                    <div
                      style={{
                        display: "flex",
                        gap: "0.9rem",
                        alignItems: "flex-start",
                      }}
                    >
                      <ConfidenceTierSigil tier={c.confidenceTier} />
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div
                          className="mono"
                          style={{
                            fontSize: "0.6rem",
                            color: "var(--amber-dim)",
                            textTransform: "uppercase",
                            letterSpacing: "0.12em",
                          }}
                        >
                          {c.confidenceTier} · {c.topicHint || "general"}
                        </div>
                        <p
                          style={{
                            marginTop: "0.4rem",
                            marginBottom: 0,
                            fontSize: "0.95rem",
                            color: "var(--parchment)",
                            lineHeight: 1.5,
                          }}
                        >
                          {c.text}
                        </p>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>
        </div>

        <div className="meander" aria-hidden="true" />

        <section
          className="ascii-frame"
          data-label={`DRIFT EVENTS · ${toRoman(drifts.length) || "0"}`}
          style={{ marginTop: "0.5rem" }}
        >
          {drifts.length === 0 ? (
            <LatinEmpty
              latin="Fundamenta firma."
              english="No drift observed — the foundations are firm."
            />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {drifts.map((d) => (
                <div key={d.id} className="portal-card" style={{ padding: "0.9rem 1rem" }}>
                  <div className="mono" style={{ fontSize: "0.72rem", color: "var(--ember)" }}>
                    score {(d.driftScore * 100).toFixed(0)}% · {d.targetKind}{" "}
                    {d.targetId.slice(0, 8)}…
                  </div>
                  <p
                    style={{
                      marginTop: "0.35rem",
                      fontSize: "0.9rem",
                      color: "var(--parchment-dim)",
                      lineHeight: 1.5,
                    }}
                  >
                    {d.naturalLanguageSummary || d.notes || "—"}
                  </p>
                  <div
                    className="mono"
                    style={{
                      fontSize: "0.6rem",
                      color: "var(--parchment-dim)",
                      marginTop: "0.3rem",
                    }}
                  >
                    {new Date(d.observedAt).toLocaleDateString()}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

/** Inline Latin empty state for populated `ascii-frame` sections. */
function LatinEmpty({ latin, english }: { latin: string; english: string }) {
  return (
    <div style={{ padding: "1rem 0.25rem", textAlign: "center" }}>
      <p
        style={{
          fontFamily: "'EB Garamond', serif",
          fontStyle: "italic",
          fontSize: "1rem",
          color: "var(--parchment)",
          margin: 0,
        }}
      >
        {latin}
      </p>
      <p
        className="mono"
        style={{
          fontSize: "0.7rem",
          color: "var(--parchment-dim)",
          marginTop: "0.25rem",
        }}
      >
        {english}
      </p>
    </div>
  );
}

/** Small positive int → Roman numerals, for display accents only. */
function toRoman(n: number): string {
  if (!n || n < 1) return "";
  const table: [number, string][] = [
    [10, "X"],
    [9, "IX"],
    [5, "V"],
    [4, "IV"],
    [1, "I"],
  ];
  let out = "";
  let rem = n;
  for (const [v, s] of table) {
    while (rem >= v) {
      out += s;
      rem -= v;
    }
  }
  return out;
}
