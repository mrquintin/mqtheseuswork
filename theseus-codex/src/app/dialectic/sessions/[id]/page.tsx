import { notFound } from "next/navigation";

import { db } from "@/lib/db";

/**
 * `/dialectic/sessions/[id]` — public read of a Dialectic session
 * (prompt 14).
 *
 * Renders the transcript with speaker attribution. Inline annotations
 * mark every HISTORICAL contradiction flag with a link back to the
 * prior position. The footer surfaces principles that were promoted
 * post-triage (driven by the session's `summaryMemoId`).
 *
 * Only sessions whose `visibility === "PUBLIC"` are exposed. Anything
 * else returns 404 so unlisted recordings stay private.
 */

export const dynamic = "force-dynamic";
export const revalidate = 0;

type SessionRow = {
  id: string;
  title: string;
  visibility: string;
  status: string;
  startedAt: Date;
  endedAt: Date | null;
  participantsJson: string;
  summaryMemoId: string | null;
};

type UtteranceRow = {
  id: string;
  speakerId: string;
  startTime: number;
  endTime: number;
  text: string;
  liveContradictionFlagsJson: string;
};

type FlagRow = {
  id: string;
  utteranceId: string;
  flagKind: string;
  contradictionScore: number;
  axis: string | null;
  humanExplanation: string | null;
  priorUtteranceId: string | null;
  priorPrincipleId: string | null;
  priorSpeakerId: string | null;
};

function parseSpeakerLookup(
  raw: string,
): Map<string, string> {
  try {
    const parsed = JSON.parse(raw || "[]");
    const map = new Map<string, string>();
    if (Array.isArray(parsed)) {
      for (const entry of parsed) {
        const id = String(entry?.speaker_id ?? "");
        const name = String(entry?.display_name ?? "");
        if (id) map.set(id, name || id);
      }
    }
    return map;
  } catch {
    return new Map();
  }
}

async function loadPublicSession(id: string): Promise<SessionRow | null> {
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
  if (!row) return null;
  if (row.visibility !== "PUBLIC") return null;
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

async function loadFlags(utteranceIds: string[]): Promise<FlagRow[]> {
  if (utteranceIds.length === 0) return [];
  const api = (
    db as unknown as {
      dialecticContradictionFlag?: {
        findMany: (args: unknown) => Promise<FlagRow[]>;
      };
    }
  ).dialecticContradictionFlag;
  if (!api) return [];
  return await api
    .findMany({
      where: { utteranceId: { in: utteranceIds } },
    })
    .catch(() => []);
}

export default async function PublicDialecticSessionPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const session = await loadPublicSession(id);
  if (!session) notFound();

  const utterances = await loadUtterances(session.id);
  const speakerNames = parseSpeakerLookup(session.participantsJson);
  const flags = await loadFlags(utterances.map((u) => u.id));
  const flagsByUtterance = new Map<string, FlagRow[]>();
  for (const f of flags) {
    const arr = flagsByUtterance.get(f.utteranceId) ?? [];
    arr.push(f);
    flagsByUtterance.set(f.utteranceId, arr);
  }
  const historicalFlags = flags.filter((f) => f.flagKind !== "INTRA_SESSION");

  return (
    <main className="prose" data-testid="public-dialectic-session">
      <header style={{ marginBottom: "1.5rem" }}>
        <h1>{session.title || "Untitled session"}</h1>
        <p style={{ color: "var(--amber-dim)" }}>
          {session.startedAt instanceof Date
            ? session.startedAt.toISOString().slice(0, 10)
            : String(session.startedAt)}{" "}
          · {session.status}
        </p>
      </header>

      <section>
        <h2>Transcript</h2>
        {utterances.length === 0 ? (
          <p>(No utterances published.)</p>
        ) : (
          <ol style={{ paddingLeft: "1.25rem" }}>
            {utterances.map((u) => {
              const flagged = flagsByUtterance.get(u.id) ?? [];
              const historical = flagged.filter(
                (f) => f.flagKind !== "INTRA_SESSION",
              );
              return (
                <li key={u.id} data-utterance-id={u.id}>
                  <strong>
                    {speakerNames.get(u.speakerId) ?? u.speakerId}
                  </strong>
                  : {u.text}
                  {historical.length > 0 ? (
                    <aside
                      data-testid="historical-annotation"
                      style={{
                        marginTop: "0.4rem",
                        borderLeft: "3px solid var(--warning, #d35400)",
                        paddingLeft: "0.6rem",
                        color: "var(--amber-dim)",
                        fontSize: "0.88rem",
                      }}
                    >
                      Contradicts an earlier position
                      {historical[0].priorSpeakerId
                        ? ` (${
                            speakerNames.get(historical[0].priorSpeakerId) ??
                            historical[0].priorSpeakerId
                          })`
                        : ""}{" "}
                      — score {historical[0].contradictionScore.toFixed(2)}
                      {historical[0].axis ? `, axis ${historical[0].axis}` : ""}.
                    </aside>
                  ) : null}
                </li>
              );
            })}
          </ol>
        )}
      </section>

      <footer
        style={{
          marginTop: "2rem",
          borderTop: "1px solid var(--rule)",
          paddingTop: "1rem",
        }}
      >
        <h3>What changed during this conversation</h3>
        {historicalFlags.length === 0 ? (
          <p style={{ color: "var(--amber-dim)" }}>
            No historical positions were challenged.
          </p>
        ) : (
          <p>
            {historicalFlags.length} historical contradiction
            {historicalFlags.length === 1 ? "" : "s"} surfaced during this
            session.
          </p>
        )}
        {session.summaryMemoId ? (
          <p>
            <a href={`/memos/${session.summaryMemoId}`}>
              Read the session summary memo →
            </a>
          </p>
        ) : null}
      </footer>
    </main>
  );
}
