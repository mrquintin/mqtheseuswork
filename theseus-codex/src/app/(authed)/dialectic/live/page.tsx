import Link from "next/link";
import { redirect } from "next/navigation";

import { db } from "@/lib/db";
import { requireTenantContext } from "@/lib/tenant";

/**
 * `/(authed)/dialectic/live` — operator list of every Dialectic
 * recorded session in the org (prompt 14).
 *
 * Lives at `/dialectic/live` (not `/dialectic/sessions`) so the public
 * reader surface at `/dialectic/sessions/[id]` owns the canonical
 * session URL without ambiguity.
 *
 * Sessions surface their current status, the live contradiction
 * count, and a deep link into the per-session detail page (which is
 * also where consent + recording controls live).
 */

export const dynamic = "force-dynamic";
export const revalidate = 0;

type SessionRow = {
  id: string;
  title: string;
  status: string;
  visibility: string;
  startedAt: Date;
  endedAt: Date | null;
  liveContradictionsDetected: number;
  principlesExtracted: number;
};

async function loadSessions(organizationId: string): Promise<SessionRow[]> {
  const api = (
    db as unknown as {
      dialecticSession?: {
        findMany: (args: unknown) => Promise<SessionRow[]>;
      };
    }
  ).dialecticSession;
  if (!api) return [];
  try {
    return await api.findMany({
      where: { organizationId },
      orderBy: { startedAt: "desc" },
      take: 100,
    });
  } catch {
    return [];
  }
}

export default async function DialecticSessionsIndexPage() {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login?next=%2Fdialectic%2Fsessions");

  const sessions = await loadSessions(tenant.organizationId);

  return (
    <main className="authed-prose" data-testid="dialectic-sessions-page">
      <header
        style={{
          marginBottom: "1.25rem",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
        }}
      >
        <div>
          <h1>Dialectic sessions</h1>
          <p style={{ color: "var(--amber-dim)" }}>
            Recorded conversations with live contradiction detection.
          </p>
        </div>
        <Link href="/dialectic/record">Start a new recording →</Link>
      </header>

      {sessions.length === 0 ? (
        <p style={{ color: "var(--amber-dim)" }}>
          No sessions yet. Use{" "}
          <code>noosphere dialectic record --title &quot;…&quot;</code> or the
          form linked above.
        </p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left" }}>
              <th>Title</th>
              <th>Status</th>
              <th>Visibility</th>
              <th>Contradictions</th>
              <th>Provisional principles</th>
              <th>Started</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map((s) => (
              <tr key={s.id} data-session-id={s.id}>
                <td>
                  <Link href={`/dialectic/live/${s.id}`}>{s.title || s.id}</Link>
                </td>
                <td>{s.status}</td>
                <td>{s.visibility}</td>
                <td>{s.liveContradictionsDetected}</td>
                <td>{s.principlesExtracted}</td>
                <td>
                  {s.startedAt instanceof Date
                    ? s.startedAt.toISOString().slice(0, 19) + "Z"
                    : String(s.startedAt)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
