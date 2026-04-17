"use client";

import { AS_OF_ISO } from "@/lib/replayDate";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

export default function TemporalReplayBar() {
  const pathname = usePathname();
  const router = useRouter();
  const sp = useSearchParams();
  const current = sp.get("asOf") || "";
  const [draft, setDraft] = useState(current);

  useEffect(() => {
    setDraft(current);
  }, [current]);

  const merged = useMemo(() => {
    const q = new URLSearchParams(sp.toString());
    return q;
  }, [sp]);

  function apply(nextAsOf: string) {
    const q = new URLSearchParams(merged.toString());
    if (!nextAsOf) {
      q.delete("asOf");
    } else {
      q.set("asOf", nextAsOf);
    }
    const qs = q.toString();
    router.push(qs ? `${pathname}?${qs}` : pathname);
  }

  return (
    <div
      style={{
        marginBottom: "1.25rem",
        padding: "0.75rem 1rem",
        border: "1px solid var(--border)",
        borderRadius: "6px",
        background: "var(--stone)",
        display: "flex",
        flexWrap: "wrap",
        gap: "0.75rem",
        alignItems: "center",
        fontSize: "0.75rem",
        color: "var(--parchment-dim)",
      }}
    >
      <span style={{ fontFamily: "'Cinzel', serif", color: "var(--gold)", letterSpacing: "0.08em" }}>
        As of
      </span>
      <input
        type="date"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        style={{
          background: "#0d0d12",
          color: "var(--parchment)",
          border: "1px solid var(--border)",
          borderRadius: "4px",
          padding: "0.25rem 0.5rem",
        }}
      />
      <button type="button" className="btn" style={{ fontSize: "0.65rem" }} onClick={() => apply(draft)}>
        Apply
      </button>
      <button type="button" className="btn" style={{ fontSize: "0.65rem" }} onClick={() => { setDraft(""); apply(""); }}>
        Now
      </button>
      {current && (
        <span>
          Viewing replay cutoff <code style={{ color: "var(--gold-dim)" }}>{current}</code>
          {!AS_OF_ISO.test(current) ? " (invalid; ignored by server)" : null}. Conclusions use Noosphere replay rules;
          contradictions/founders filter portal rows by <code>createdAt</code> ≤ end of that UTC day (approximation).
        </span>
      )}
    </div>
  );
}
