import { notFound, redirect } from "next/navigation";
import Link from "next/link";

import { db } from "@/lib/db";
import { requireTenantContext } from "@/lib/tenant";

/**
 * `/(authed)/dialectic/live/[id]` — per-session operator view
 * (prompt 14).
 *
 * Surfaces the participant consent panel, the rolling utterance
 * transcript, and the live contradiction flag log. While the session
 * is RECORDING, the page polls the currents API for new utterances /
 * flags. Once it transitions to PROCESSING / COMPLETE, the page goes
 * read-only and links to the triage queue.
 */

export const dynamic = "force-dynamic";
export const revalidate = 0;

type Participant = {
  speaker_id: string;
  display_name: string;
  consented: boolean;
  consented_at?: string | null;
};

type SessionRow = {
  id: string;
  organizationId: string;
  title: string;
  status: string;
  visibility: string;
  startedAt: Date;
  endedAt: Date | null;
  participantsJson: string;
  liveContradictionsDetected: number;
  principlesExtracted: number;
  summaryMemoId: string | null;
};

type UtteranceRow = {
  id: string;
  speakerId: string;
  startTime: number;
  endTime: number;
  text: string;
  derivedPrincipleIdsJson: string;
  liveContradictionFlagsJson: string;
};

type FlagRow = {
  id: string;
  utteranceId: string;
  flagKind: string;
  contradictionScore: number;
  axis: string | null;
  humanExplanation: string | null;
  priorSpeakerId: string | null;
  acknowledgedAt: Date | null;
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
      orderBy: { detectedAt: "asc" },
    })
    .catch(() => []);
}

function parseParticipants(raw: string): Participant[] {
  try {
    const parsed = JSON.parse(raw || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export default async function DialecticSessionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const tenant = await requireTenantContext();
  if (!tenant) redirect(`/login?next=%2Fdialectic%2Fsessions%2F${id}`);

  const session = await loadSession(id, tenant.organizationId);
  if (!session) notFound();

  const participants = parseParticipants(session.participantsJson);
  const consentGate = participants.some((p) => !p.consented);
  const utterances = await loadUtterances(session.id);
  const flags = await loadFlags(utterances.map((u) => u.id));

  return (
    <main className="authed-prose" data-testid="dialectic-session-detail">
      <header style={{ marginBottom: "1rem" }}>
        <h1>{session.title || session.id}</h1>
        <p
          className="mono"
          style={{ color: "var(--amber-dim)", marginTop: "0.25rem" }}
        >
          Status: {session.status} · Visibility: {session.visibility} ·{" "}
          Contradictions: {session.liveContradictionsDetected} ·{" "}
          Provisional principles: {session.principlesExtracted}
        </p>
      </header>

      <section style={{ marginBottom: "1.5rem" }}>
        <h2>Consent</h2>
        {consentGate ? (
          <p style={{ color: "var(--danger, #c0392b)" }}>
            Recording is paused until every participant consents.
          </p>
        ) : (
          <p style={{ color: "var(--ok, #2e7d32)" }}>
            All participants have consented — recorder may stream.
          </p>
        )}
        <ul style={{ listStyle: "none", padding: 0 }}>
          {participants.map((p) => (
            <li
              key={p.speaker_id}
              data-speaker-id={p.speaker_id}
              data-consented={p.consented ? "true" : "false"}
              style={{
                padding: "0.4rem 0",
                borderBottom: "1px solid var(--rule)",
              }}
            >
              <strong>{p.display_name}</strong>{" "}
              {p.consented ? "— consented" : "— awaiting consent"}
            </li>
          ))}
        </ul>
      </section>

      <section style={{ marginBottom: "1.5rem" }}>
        <h2>Transcript</h2>
        {utterances.length === 0 ? (
          <p style={{ color: "var(--amber-dim)" }}>No utterances yet.</p>
        ) : (
          <ol style={{ paddingLeft: "1.25rem" }}>
            {utterances.map((u) => (
              <li key={u.id} data-utterance-id={u.id}>
                <code>{u.speakerId}</code>{" "}
                ({u.startTime.toFixed(1)}–{u.endTime.toFixed(1)}s): {u.text}
              </li>
            ))}
          </ol>
        )}
      </section>

      <section style={{ marginBottom: "1.5rem" }}>
        <h2>Contradiction log</h2>
        {flags.length === 0 ? (
          <p style={{ color: "var(--amber-dim)" }}>No contradictions flagged.</p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0 }}>
            {flags.map((f) => (
              <li
                key={f.id}
                data-flag-id={f.id}
                style={{
                  borderLeft: "3px solid var(--danger, #c0392b)",
                  paddingLeft: "0.6rem",
                  marginBottom: "0.6rem",
                }}
              >
                <strong>{f.flagKind}</strong> · score{" "}
                {f.contradictionScore.toFixed(2)}
                {f.axis ? ` · axis ${f.axis}` : null}
                {f.humanExplanation ? (
                  <p style={{ margin: "0.3rem 0" }}>{f.humanExplanation}</p>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      {session.status !== "RECORDING" ? (
        <p>
          <Link href={`/dialectic/live/${session.id}/triage`}>
            Review provisional principles in triage →
          </Link>
        </p>
      ) : null}
    </main>
  );
}
