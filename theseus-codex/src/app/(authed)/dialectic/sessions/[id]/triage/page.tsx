import { notFound, redirect } from "next/navigation";

import { db } from "@/lib/db";
import { requireTenantContext } from "@/lib/tenant";

/**
 * `/(authed)/dialectic/sessions/[id]/triage` — founder review queue
 * for provisional principles surfaced by the live recorder
 * (prompt 14).
 *
 * Nothing on this page promotes a principle automatically — the
 * founder accepts / rejects / edits each item and the promotion is
 * an explicit POST. The PROVISIONAL badge stays on every row until
 * the founder acts.
 */

export const dynamic = "force-dynamic";
export const revalidate = 0;

type SessionRow = {
  id: string;
  organizationId: string;
  title: string;
  status: string;
};

type UtteranceRow = {
  id: string;
  speakerId: string;
  text: string;
  derivedPrincipleIdsJson: string;
};

async function loadSession(id: string, orgId: string): Promise<SessionRow | null> {
  const api = (
    db as unknown as {
      dialecticSession?: {
        findUnique: (args: unknown) => Promise<SessionRow | null>;
      };
    }
  ).dialecticSession;
  if (!api) return null;
  const row = await api
    .findUnique({ where: { id } })
    .catch(() => null);
  if (!row || row.organizationId !== orgId) return null;
  return row;
}

async function loadUtterances(sessionId: string): Promise<UtteranceRow[]> {
  const api = (
    db as unknown as {
      dialecticUtterance?: {
        findMany: (args: unknown) => Promise<UtteranceRow[]>;
      };
    }
  ).dialecticUtterance;
  if (!api) return [];
  return await api
    .findMany({
      where: { sessionId },
      orderBy: { startTime: "asc" },
    })
    .catch(() => []);
}

function parsePrincipleIds(raw: string): string[] {
  try {
    const parsed = JSON.parse(raw || "[]");
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}

export default async function DialecticTriagePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const tenant = await requireTenantContext();
  if (!tenant) redirect(`/login?next=%2Fdialectic%2Fsessions%2F${id}%2Ftriage`);

  const session = await loadSession(id, tenant.organizationId);
  if (!session) notFound();

  const utterances = await loadUtterances(session.id);
  const queue = utterances.flatMap((u) => {
    const ids = parsePrincipleIds(u.derivedPrincipleIdsJson);
    if (ids.length === 0) return [];
    return [
      {
        utteranceId: u.id,
        speakerId: u.speakerId,
        text: u.text,
        principleIds: ids,
      },
    ];
  });

  return (
    <main className="authed-prose" data-testid="dialectic-triage-page">
      <header style={{ marginBottom: "1rem" }}>
        <h1>Triage — {session.title || session.id}</h1>
        <p style={{ color: "var(--amber-dim)" }}>
          Provisional principles extracted live from this session. Every
          row is marked PROVISIONAL until you accept, reject, or edit
          it. None of these are queryable or shown publicly yet.
        </p>
      </header>

      {queue.length === 0 ? (
        <p style={{ color: "var(--amber-dim)" }}>
          Nothing to triage from this session.
        </p>
      ) : (
        <ol style={{ paddingLeft: "1.25rem" }}>
          {queue.map((item) => (
            <li
              key={item.utteranceId}
              data-utterance-id={item.utteranceId}
              style={{ marginBottom: "1rem" }}
            >
              <span
                style={{
                  color: "var(--warning, #d35400)",
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.8rem",
                  marginRight: "0.5rem",
                }}
              >
                PROVISIONAL
              </span>
              <strong>{item.speakerId}</strong>: {item.text}
              <p
                style={{
                  marginTop: "0.25rem",
                  color: "var(--amber-dim)",
                  fontSize: "0.85rem",
                }}
              >
                {item.principleIds.length} candidate principle
                {item.principleIds.length === 1 ? "" : "s"}
              </p>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <button type="button">Accept</button>
                <button type="button">Reject</button>
                <button type="button">Edit…</button>
              </div>
            </li>
          ))}
        </ol>
      )}
    </main>
  );
}
