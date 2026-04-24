import Link from "next/link";
import { revalidatePath } from "next/cache";
import ConfidenceTierSigil from "@/components/ConfidenceTierSigil";
import SculptureBackdrop from "@/components/SculptureBackdrop";
import AutoProcessStatusBanner from "@/components/AutoProcessStatusBanner";
import PublishToggle from "@/components/PublishToggle";
import UploadStatusBadge from "@/components/UploadStatusBadge";
import UploadRowDetail from "@/components/UploadRowDetail";
import { db } from "@/lib/db";
import { fetchDecayRecords } from "@/lib/api/round3";
import { requireTenantContext } from "@/lib/tenant";

/**
 * Dashboard — landing page after login.
 *
 * Patron sculpture: **Sisyphus**, rendered huge and dim on the right
 * side of the page. The daily act of returning to the Codex — scanning
 * newly-synthesized conclusions, picking up where yesterday's
 * deliberation left off, discovering the contradictions that drifted
 * overnight — is the boulder at firm-memory scale. The reward for a
 * round of work well done is another round of work: the dashboard is
 * the summit the figure never quite reaches, and the page is the
 * fresh slope they return to.
 */

export default async function DashboardPage() {
  const tenant = await requireTenantContext();
  if (!tenant) {
    return null;
  }

  // The "Uploads" panel now surfaces every recent upload regardless
  // of status — this is the feedback surface that tells a founder
  // what the pipeline is doing to their file. The status badge is
  // how they tell one state from another at a glance; the detail row
  // shows extractionMethod on success and an expandable error +
  // retry button on failure (see UploadRowDetail).
  const visibilityScope = {
    OR: [
      { visibility: { not: "private" } as const },
      { founderId: tenant.founderId },
    ],
  };
  const [recentUploads, pendingUploads, failedUploads] = await Promise.all([
    db.upload.findMany({
      where: {
        organizationId: tenant.organizationId,
        deletedAt: null,
        ...visibilityScope,
      },
      orderBy: { createdAt: "desc" },
      take: 12,
      select: {
        id: true,
        title: true,
        status: true,
        errorMessage: true,
        extractionMethod: true,
        visibility: true,
        publishedAt: true,
        slug: true,
        createdAt: true,
        founder: { select: { name: true } },
      },
    }),
    db.upload.count({
      where: {
        organizationId: tenant.organizationId,
        deletedAt: null,
        status: {
          in: ["pending", "extracting", "awaiting_ingest", "processing", "queued_offline"],
        },
        ...visibilityScope,
      },
    }),
    db.upload.count({
      where: {
        organizationId: tenant.organizationId,
        deletedAt: null,
        status: "failed",
        ...visibilityScope,
      },
    }),
  ]);

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
    where: {
      organizationId: tenant.organizationId,
      // Hide conclusions this founder has dismissed from their
      // dashboard. Other founders' dashboards are unaffected.
      dashboardDismissals: {
        none: { founderId: tenant.founderId },
      },
    },
    orderBy: { createdAt: "desc" },
    take: 8,
  });

  // Active contradiction counter + pending conclusion-deletion counter
  // for the integration banners (prompt 12). Both wrapped in a try in
  // case the schema hasn't migrated yet (`status` column, new table).
  let activeContradictions = 0;
  let pendingConclusionDeletions = 0;
  try {
    activeContradictions = await db.contradiction.count({
      where: {
        organizationId: tenant.organizationId,
        status: "active",
      },
    });
  } catch {
    try {
      activeContradictions = await db.contradiction.count({
        where: { organizationId: tenant.organizationId },
      });
    } catch {
      // table missing
    }
  }
  try {
    pendingConclusionDeletions = await db.conclusionDeletionRequest.count({
      where: {
        conclusion: { organizationId: tenant.organizationId },
        status: "pending",
      },
    });
  } catch {
    // table not yet migrated
  }

  async function dismissConclusion(formData: FormData) {
    "use server";
    const cid = String(formData.get("conclusionId") || "");
    if (!cid) return;
    const t = await requireTenantContext();
    if (!t) return;
    await db.dashboardDismissal.upsert({
      where: {
        founderId_conclusionId: {
          founderId: t.founderId,
          conclusionId: cid,
        },
      },
      update: {},
      create: { founderId: t.founderId, conclusionId: cid },
    });
    revalidatePath("/dashboard");
  }

  const drifts = await db.driftEvent.findMany({
    where: { organizationId: tenant.organizationId },
    orderBy: { observedAt: "desc" },
    take: 6,
  });

  // Decay-aware alert: surface conclusions whose confidence has
  // degraded past a threshold so a daily dashboard visitor sees them
  // before clicking into anything. `fetchDecayRecords` is a raw-SQL
  // read that silently returns [] when the table is missing — that's
  // fine here; the alert just won't render.
  const decayRecords = await fetchDecayRecords(tenant.organizationId);
  const decaying = decayRecords.filter((r) => r.status === "decaying");
  const expired = decayRecords.filter((r) => r.status === "expired");

  const activeUploads = pendingUploads;

  return (
    <div style={{ position: "relative", overflow: "hidden", minHeight: "80vh" }}>
      <SculptureBackdrop src="/sculptures/sisyphus.mesh.bin" side="right" />

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
            Sisyphus · Labor redivivus
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

        {(expired.length > 0 || decaying.length > 0) && (
          <div
            style={{
              padding: "1rem 1.25rem",
              border: "1px solid var(--ember)",
              borderRadius: 2,
              marginBottom: "1.5rem",
            }}
          >
            <div
              style={{
                fontFamily: "'Cinzel', serif",
                fontSize: "0.65rem",
                letterSpacing: "0.15em",
                textTransform: "uppercase",
                color: "var(--ember)",
                marginBottom: "0.5rem",
              }}
            >
              Conclusions requiring attention
            </div>
            {expired.length > 0 && (
              <p style={{ fontSize: "0.85rem", color: "var(--ember)", margin: "0.25rem 0" }}>
                {expired.length} expired conclusion
                {expired.length > 1 ? "s" : ""} — confidence has decayed below
                threshold.
              </p>
            )}
            {decaying.length > 0 && (
              <p style={{ fontSize: "0.85rem", color: "var(--parchment)", margin: "0.25rem 0" }}>
                {decaying.length} decaying conclusion
                {decaying.length > 1 ? "s" : ""} — confidence is declining.
              </p>
            )}
            <Link
              href="/decay"
              style={{
                display: "inline-block",
                marginTop: "0.5rem",
                fontSize: "0.7rem",
                color: "var(--gold)",
                textDecoration: "none",
              }}
            >
              View decay dashboard →
            </Link>
          </div>
        )}

        {activeContradictions > 0 && (
          <Link href="/contradictions" style={{ textDecoration: "none", display: "block" }}>
            <div
              className="portal-card"
              style={{
                padding: "0.7rem 1rem",
                marginBottom: "1rem",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                fontSize: "0.8rem",
                borderLeft: "3px solid var(--ember)",
              }}
            >
              <span style={{ color: "var(--ember)" }}>
                {activeContradictions} active contradiction
                {activeContradictions > 1 ? "s" : ""} detected
              </span>
              <span
                className="mono"
                style={{
                  fontSize: "0.6rem",
                  color: "var(--amber-dim)",
                  textTransform: "uppercase",
                }}
              >
                Review →
              </span>
            </div>
          </Link>
        )}

        {pendingConclusionDeletions > 0 && (
          <Link href="/conclusions" style={{ textDecoration: "none", display: "block" }}>
            <div
              className="portal-card"
              style={{
                padding: "0.7rem 1rem",
                marginBottom: "1rem",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                fontSize: "0.8rem",
              }}
            >
              <span style={{ color: "var(--amber)" }}>
                {pendingConclusionDeletions} pending conclusion deletion
                {pendingConclusionDeletions > 1 ? " requests" : " request"}
              </span>
              <span
                className="mono"
                style={{
                  fontSize: "0.6rem",
                  color: "var(--amber-dim)",
                  textTransform: "uppercase",
                }}
              >
                Review →
              </span>
            </div>
          </Link>
        )}

        {(failedUploads > 0 || pendingUploads > 0) && (
          <Link href="/library" style={{ textDecoration: "none", display: "block" }}>
            <div
              className="portal-card"
              style={{
                padding: "0.7rem 1rem",
                marginBottom: "1rem",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                fontSize: "0.8rem",
              }}
            >
              <span style={{ color: "var(--parchment-dim)" }}>
                {failedUploads > 0 && (
                  <span style={{ color: "var(--ember)" }}>
                    {failedUploads} failed upload{failedUploads > 1 ? "s" : ""}
                  </span>
                )}
                {failedUploads > 0 && pendingUploads > 0 && " · "}
                {pendingUploads > 0 && (
                  <span>{pendingUploads} processing</span>
                )}
              </span>
              <span
                className="mono"
                style={{
                  fontSize: "0.6rem",
                  color: "var(--amber-dim)",
                  textTransform: "uppercase",
                }}
              >
                View in library →
              </span>
            </div>
          </Link>
        )}

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
            data-label={`UPLOADS · ${toRoman(recentUploads.length) || "0"}`}
          >
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {recentUploads.length === 0 ? (
                <LatinEmpty
                  latin="Scriba exspectat."
                  english="The scribe awaits — nothing ingested yet."
                />
              ) : (
                recentUploads.map((u) => (
                  <div key={u.id} className="portal-card" style={{ padding: "0.9rem 1rem" }}>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        gap: "1rem",
                        alignItems: "flex-start",
                      }}
                    >
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "0.45rem",
                            overflow: "hidden",
                            flexWrap: "wrap",
                          }}
                        >
                          <span
                            style={{
                              fontFamily: "'EB Garamond', serif",
                              color: "var(--parchment)",
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                              minWidth: 0,
                            }}
                          >
                            {u.title}
                          </span>
                          <UploadStatusBadge status={u.status} />
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
                          ) : u.visibility === "semi-private" ? (
                            <span
                              className="mono"
                              title="Semi-private — firm sees this; public blog never does. Noosphere still analyses it."
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
                              Semi-private
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
                        <UploadRowDetail upload={u} />
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
                        {u.status === "ingested" ? (
                          <PublishToggle
                            uploadId={u.id}
                            initialPublishedAt={u.publishedAt}
                            initialSlug={u.slug}
                          />
                        ) : null}
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
                      <form action={dismissConclusion}>
                        <input type="hidden" name="conclusionId" value={c.id} />
                        <button
                          type="submit"
                          title="Dismiss from dashboard"
                          style={{
                            background: "none",
                            border: "none",
                            color: "var(--parchment-dim)",
                            cursor: "pointer",
                            fontSize: "0.9rem",
                            padding: "0.1rem 0.4rem",
                            opacity: 0.6,
                            lineHeight: 1,
                          }}
                        >
                          ×
                        </button>
                      </form>
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
