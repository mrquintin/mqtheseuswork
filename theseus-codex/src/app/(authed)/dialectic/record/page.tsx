import { redirect } from "next/navigation";

import { requireTenantContext } from "@/lib/tenant";

/**
 * `/(authed)/dialectic/record` — operator surface for starting a new
 * Dialectic live recording (prompt 14).
 *
 * The form names the participants up front. The recorder refuses to
 * start until every named participant has flipped to consented (the
 * per-row "I consent" buttons render on the session detail page).
 *
 * Submitting POSTs to the currents API at
 * `/v1/dialectic/sessions` (see
 * `current_events_api/routes/dialectic_live.py`), then redirects to
 * the session detail page.
 */

export const dynamic = "force-dynamic";
export const revalidate = 0;

async function createSession(formData: FormData) {
  "use server";

  const title = String(formData.get("title") ?? "").trim();
  const speakersRaw = String(formData.get("speakers") ?? "").trim();
  const visibility = String(formData.get("visibility") ?? "PRIVATE");
  if (!title || !speakersRaw) return;

  const apiBase =
    process.env.NEXT_PUBLIC_CURRENTS_API_URL ?? "http://localhost:8000";
  const res = await fetch(`${apiBase}/v1/dialectic/sessions`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      title,
      speaker_names: speakersRaw
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      visibility,
    }),
  });
  if (!res.ok) {
    throw new Error(`Failed to create session (${res.status})`);
  }
  const body = (await res.json()) as { session: { id: string } };
  redirect(`/dialectic/live/${body.session.id}`);
}

export default async function DialecticRecordPage() {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login?next=%2Fdialectic%2Frecord");

  return (
    <main className="authed-prose" data-testid="dialectic-record-page">
      <header style={{ marginBottom: "1.5rem" }}>
        <h1>Start a Dialectic recording</h1>
        <p style={{ color: "var(--amber-dim)" }}>
          Name the participants. Every participant must individually
          consent on the session page before the microphone opens.
          Contradiction alerts surface live; provisional principles
          stay in triage until you review them.
        </p>
      </header>

      <form action={createSession} style={{ display: "grid", gap: "0.75rem" }}>
        <label style={{ display: "grid", gap: "0.25rem" }}>
          <span>Title</span>
          <input
            name="title"
            type="text"
            required
            placeholder="e.g. Founders' weekly — 2026-05-16"
            style={{ padding: "0.4rem 0.5rem" }}
          />
        </label>

        <label style={{ display: "grid", gap: "0.25rem" }}>
          <span>Participants (comma-separated)</span>
          <input
            name="speakers"
            type="text"
            required
            placeholder="e.g. Michael Quintin, Claire Lee, James Park"
            style={{ padding: "0.4rem 0.5rem" }}
          />
        </label>

        <label style={{ display: "grid", gap: "0.25rem" }}>
          <span>Visibility</span>
          <select name="visibility" defaultValue="PRIVATE">
            <option value="PRIVATE">Private (operator-only)</option>
            <option value="PUBLIC">Public (publishes the transcript)</option>
          </select>
        </label>

        <button type="submit" style={{ marginTop: "0.5rem" }}>
          Create session
        </button>
      </form>
    </main>
  );
}
