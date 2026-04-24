"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

type Intervention = {
  id: string;
  kind: string;
  overlay_lines: string[];
  tts_text: string;
  trigger_context: Record<string, unknown>;
  quality_gate: Record<string, unknown>;
  engagement?: string;
  value_rating?: string;
  dropped_reason?: string;
};

type Bundle = {
  session_id: string;
  mode: string;
  participants_opted_in: boolean;
  stand_down: boolean;
  interventions: Intervention[];
};

export default function SessionReflectionPage() {
  const params = useParams();
  const id = typeof params?.id === "string" ? params.id : "";
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const r = await fetch(`/api/sessions/${encodeURIComponent(id)}/reflection`);
    const j = (await r.json()) as { ok?: boolean; data?: Bundle; error?: string };
    if (!r.ok) {
      setError(j.error ?? "Failed to load");
      setBundle(null);
    } else {
      setBundle(j.data ?? null);
    }
    setLoading(false);
  }, [id]);

  useEffect(() => {
    if (id) void load();
  }, [id, load]);

  async function rate(interventionId: string, valueRating: "high_value" | "low_value" | "annoying") {
    const r = await fetch(`/api/sessions/${encodeURIComponent(id)}/reflection`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ interventionId, valueRating }),
    });
    if (!r.ok) {
      const j = (await r.json()) as { error?: string };
      setError(j.error ?? "Save failed");
      return;
    }
    await load();
  }

  return (
    <div style={{ maxWidth: "900px", margin: "0 auto", padding: "1.5rem 1rem" }}>
      <h1 style={{ fontFamily: "'Cinzel', serif", fontSize: "1.25rem", marginBottom: "0.5rem" }}>
        Session reflection
      </h1>
      <p style={{ color: "var(--muted)", fontSize: "0.9rem", marginBottom: "1.25rem" }}>
        Theseus interlocutor (SP09). Place Dialectic <code style={{ fontSize: "0.85em" }}>{id}_reflection.json</code>{" "}
        under <code style={{ fontSize: "0.85em" }}>DIALECTIC_REFLECTIONS_DIR</code> on the server, then refresh.
      </p>
      {loading && <p>Loading…</p>}
      {error && (
        <p style={{ color: "#a44" }}>
          {error}
        </p>
      )}
      {bundle && (
        <>
          <p style={{ fontSize: "0.85rem", marginBottom: "1rem" }}>
            Mode: <strong>{bundle.mode}</strong>
            {" · "}
            Opt-in: {bundle.participants_opted_in ? "yes" : "no"}
            {" · "}
            Stood down: {bundle.stand_down ? "yes" : "no"}
          </p>
          <ul style={{ listStyle: "none", padding: 0, display: "flex", flexDirection: "column", gap: "1rem" }}>
            {bundle.interventions.map((row) => (
              <li
                key={row.id}
                style={{
                  border: "1px solid var(--border)",
                  borderRadius: "8px",
                  padding: "1rem",
                  background: "var(--stone)",
                }}
              >
                <div style={{ fontSize: "0.75rem", color: "var(--muted)" }}>{row.kind}</div>
                {row.overlay_lines?.length ? (
                  <pre
                    style={{
                      whiteSpace: "pre-wrap",
                      fontFamily: "system-ui",
                      fontSize: "0.85rem",
                      margin: "0.5rem 0",
                    }}
                  >
                    {row.overlay_lines.join("\n")}
                  </pre>
                ) : (
                  <p style={{ fontSize: "0.85rem" }}>Dropped: {row.dropped_reason || "—"}</p>
                )}
                <div style={{ fontSize: "0.75rem", marginTop: "0.5rem" }}>
                  Rating: {row.value_rating || "none"} · Engagement: {row.engagement || "pending"}
                </div>
                {!row.dropped_reason && (
                  <div style={{ marginTop: "0.75rem", display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                    <button
                      type="button"
                      style={{ fontSize: "0.75rem", padding: "0.35rem 0.6rem", cursor: "pointer" }}
                      onClick={() => rate(row.id, "high_value")}
                    >
                      High value
                    </button>
                    <button
                      type="button"
                      style={{ fontSize: "0.75rem", padding: "0.35rem 0.6rem", cursor: "pointer" }}
                      onClick={() => rate(row.id, "low_value")}
                    >
                      Low value
                    </button>
                    <button
                      type="button"
                      style={{ fontSize: "0.75rem", padding: "0.35rem 0.6rem", cursor: "pointer" }}
                      onClick={() => rate(row.id, "annoying")}
                    >
                      Annoying
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
