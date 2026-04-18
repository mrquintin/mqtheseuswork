import Link from "next/link";
import DashboardHearth from "@/components/DashboardHearthClient";
import ConfidenceTierSigil from "@/components/ConfidenceTierSigil";
import SculptureAscii from "@/components/SculptureAsciiClient";
import { db } from "@/lib/db";
import { requireTenantContext } from "@/lib/tenant";

/**
 * Dashboard — the landing page after login.
 *
 * Visual hierarchy:
 *   1. A large live ASCII brazier at the top. Its flame intensity is
 *      derived from system activity (pending + processing + queued
 *      uploads), so the page *pulses* when work is happening.
 *   2. A three-column band of labelled ASCII-frame cards: uploads,
 *      conclusions, drift. Each conclusion gets an inline tier sigil
 *      so the confidence tier reads at a glance.
 *   3. A meander (Greek-key) divider before any low-priority sections.
 *
 * Empty states are handled by the `LatinEmpty` component so an empty
 * Codex still feels considered rather than broken.
 */

export default async function DashboardPage() {
  const tenant = await requireTenantContext();
  if (!tenant) {
    return null;
  }

  const uploads = await db.upload.findMany({
    where: { organizationId: tenant.organizationId },
    orderBy: { createdAt: "desc" },
    take: 12,
    include: { founder: { select: { name: true } } },
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

  // Hearth intensity: uploads still in-flight are the biggest signal.
  // `queued_offline` counts at half-strength (the firm has sent work but
  // the CLI hasn't run yet). Cap at 1.0 so the flame never leaves the frame.
  const activeUploads =
    uploads.filter((u) => u.status === "processing" || u.status === "pending").length +
    uploads.filter((u) => u.status === "queued_offline").length * 0.5;
  const hearthIntensity = Math.max(
    0.18, // a quiet cauldron even when idle — always some life
    Math.min(1.0, activeUploads / 4),
  );

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
    <main style={{ padding: "1.25rem 0 3rem" }}>
      {/* The Oracle's Hearth — sitewide signature element, full-bleed band. */}
      <div
        style={{
          borderTop: "1px solid var(--border)",
          borderBottom: "1px solid var(--border)",
          background:
            "radial-gradient(ellipse at center, rgba(233,163,56,0.08) 0%, rgba(233,163,56,0.02) 40%, transparent 80%)",
          margin: "0 0 2rem",
          padding: "1.25rem 0 0.75rem",
          position: "relative",
        }}
      >
        <div style={{ display: "flex", justifyContent: "center" }}>
          <DashboardHearth cols={84} rows={22} intensity={hearthIntensity} />
        </div>
        {/* Latin dedication under the hearth. Gives the brazier a shelf to
            sit on and makes the abstract 3D asset legible as an artifact. */}
        <p
          className="mono"
          style={{
            textAlign: "center",
            fontSize: "0.6rem",
            letterSpacing: "0.3em",
            textTransform: "uppercase",
            color: "var(--amber-dim)",
            marginTop: "0.35rem",
            marginBottom: 0,
          }}
        >
          Focus Sapientiae · The Firm&apos;s Hearth
        </p>
        <p
          style={{
            textAlign: "center",
            fontFamily: "'EB Garamond', serif",
            fontStyle: "italic",
            fontSize: "0.8rem",
            color: "var(--parchment-dim)",
            marginTop: "0.25rem",
            marginBottom: 0,
          }}
        >
          {activeUploads > 0
            ? `${Math.ceil(activeUploads)} contribution${activeUploads > 1.5 ? "s" : ""} on the coals.`
            : "The coals are banked; the oracle listens."}
        </p>
      </div>

      <div style={{ maxWidth: "1100px", margin: "0 auto", padding: "0 2rem" }}>
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            alignItems: "center",
            marginBottom: "1.5rem",
          }}
        >
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
                            fontFamily: "'EB Garamond', serif",
                            color: "var(--parchment)",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {u.title}
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
                      <span className={statusBadge(u.status)}>{u.status.replace("_", " ")}</span>
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

        {/* Hercules pedestal — a rotating marble sculpture scanned from
            the Louvre, rendered as amber ASCII, standing between the
            two-column band above and the drift ledger below. Reads as
            "the firm's strength and discipline" on the landing page. */}
        <section
          aria-hidden="true"
          style={{
            margin: "1.25rem 0 1.75rem",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "2rem",
            flexWrap: "wrap",
          }}
        >
          <SculptureAscii
            src="/sculptures/hercules.mesh.bin"
            cols={42}
            rows={22}
            yawSpeed={0.03}
            ariaLabel="Hercules — classical sculpture rotating as amber ASCII"
          />
          <div style={{ maxWidth: "340px" }}>
            <p
              className="mono"
              style={{
                fontSize: "0.62rem",
                letterSpacing: "0.3em",
                textTransform: "uppercase",
                color: "var(--amber-dim)",
                margin: 0,
              }}
            >
              Hercules · Louvre
            </p>
            <p
              style={{
                fontFamily: "'EB Garamond', serif",
                fontStyle: "italic",
                fontSize: "1rem",
                color: "var(--parchment-dim)",
                marginTop: "0.4rem",
                marginBottom: 0,
                lineHeight: 1.55,
              }}
            >
              Fortitudine et disciplina — through strength and discipline. The
              firm&apos;s inheritance is the labour of distinguishing what it
              believes from what it merely said.
            </p>
          </div>
        </section>

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
      </div>
    </main>
  );
}

/** Inline Latin empty state. Used inside ascii-frame sections so the frame
 *  stays populated (rather than collapsing to a lonely label). Shown as
 *  italic Latin phrase with an English gloss underneath in a dimmer color. */
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

/** Convert a small positive integer to Roman numerals (for display accents).
 *  Only called with counts from DB queries capped at ~12, so this doesn't
 *  need to handle huge numbers correctly. Returns empty string for 0. */
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
