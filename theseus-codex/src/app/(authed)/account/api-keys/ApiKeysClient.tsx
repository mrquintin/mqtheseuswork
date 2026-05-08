"use client";

import { useCallback, useMemo, useState } from "react";

type KeyRow = {
  id: string;
  label: string;
  prefix: string;
  scopes: string;
  createdAt: string;
  lastUsedAt: string | null;
};

const SCOPE_OPTIONS = [
  { value: "read", description: "Read-only API access." },
  { value: "write", description: "Read + uploads, edits, draft conclusions." },
  {
    value: "publish",
    description: "Write + sign-and-publish (only for trusted automation).",
  },
];

function readCsrfCookie(): string {
  if (typeof document === "undefined") return "";
  const m = document.cookie
    .split(/;\s*/)
    .map((p) => p.split("="))
    .find(([k]) => k === "theseus_csrf");
  return m ? decodeURIComponent(m[1] ?? "") : "";
}

function fmt(date: string | null): string {
  if (!date) return "—";
  return new Date(date).toLocaleString();
}

export default function ApiKeysClient({
  initialKeys,
  canWrite,
}: {
  initialKeys: KeyRow[];
  canWrite: boolean;
}) {
  const [keys, setKeys] = useState<KeyRow[]>(initialKeys);
  const [label, setLabel] = useState("");
  const [scope, setScope] = useState<string>("read");
  const [minted, setMinted] = useState<{ plaintext: string; label: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const onMint = useCallback(
    async (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      setError(null);
      setMinted(null);
      try {
        const res = await fetch("/api/auth/api-keys", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": readCsrfCookie(),
          },
          body: JSON.stringify({ label, scopes: scope }),
        });
        const json = (await res.json()) as
          | { id: string; label: string; prefix: string; createdAt: string; plaintext: string }
          | { error: string };
        if (!res.ok || !("plaintext" in json)) {
          setError("error" in json ? json.error : "Failed to mint key");
          return;
        }
        setMinted({ plaintext: json.plaintext, label: json.label });
        setKeys((prev) => [
          {
            id: json.id,
            label: json.label,
            prefix: json.prefix,
            scopes: scope,
            createdAt: json.createdAt,
            lastUsedAt: null,
          },
          ...prev,
        ]);
        setLabel("");
        setScope("read");
      } catch {
        setError("Network error");
      }
    },
    [label, scope],
  );

  const onRevoke = useCallback(async (id: string) => {
    if (!confirm("Revoke this key? Any client using it will start failing immediately.")) return;
    setBusyId(id);
    setError(null);
    try {
      const res = await fetch(`/api/auth/api-keys?id=${encodeURIComponent(id)}`, {
        method: "DELETE",
        headers: { "X-CSRF-Token": readCsrfCookie() },
      });
      const json = (await res.json().catch(() => null)) as { ok?: true; error?: string } | null;
      if (!res.ok || !json?.ok) {
        setError(json?.error ?? "Failed to revoke");
        return;
      }
      setKeys((prev) => prev.filter((k) => k.id !== id));
    } finally {
      setBusyId(null);
    }
  }, []);

  const onRotate = useCallback(
    async (row: KeyRow) => {
      if (
        !confirm(
          `Rotate "${row.label}"? A new key will be minted with the same scope; the old key is revoked immediately.`,
        )
      )
        return;
      setBusyId(row.id);
      setError(null);
      setMinted(null);
      try {
        const mintRes = await fetch("/api/auth/api-keys", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": readCsrfCookie(),
          },
          body: JSON.stringify({ label: row.label, scopes: row.scopes }),
        });
        const mintJson = (await mintRes.json()) as
          | { id: string; label: string; prefix: string; createdAt: string; plaintext: string }
          | { error: string };
        if (!mintRes.ok || !("plaintext" in mintJson)) {
          setError("error" in mintJson ? mintJson.error : "Rotate failed at mint step");
          return;
        }
        await fetch(`/api/auth/api-keys?id=${encodeURIComponent(row.id)}`, {
          method: "DELETE",
          headers: { "X-CSRF-Token": readCsrfCookie() },
        });
        setMinted({ plaintext: mintJson.plaintext, label: mintJson.label });
        setKeys((prev) => [
          {
            id: mintJson.id,
            label: mintJson.label,
            prefix: mintJson.prefix,
            scopes: row.scopes,
            createdAt: mintJson.createdAt,
            lastUsedAt: null,
          },
          ...prev.filter((k) => k.id !== row.id),
        ]);
      } finally {
        setBusyId(null);
      }
    },
    [],
  );

  const sortedKeys = useMemo(
    () =>
      keys
        .slice()
        .sort((a, b) => (a.createdAt < b.createdAt ? 1 : a.createdAt > b.createdAt ? -1 : 0)),
    [keys],
  );

  return (
    <div>
      {error && (
        <div role="alert" style={{ color: "var(--rust)", marginBottom: "1rem" }}>
          {error}
        </div>
      )}

      {minted && (
        <div
          role="status"
          style={{
            border: "1px solid var(--amber)",
            padding: "1rem",
            marginBottom: "1.5rem",
            background: "rgba(212, 160, 23, 0.06)",
          }}
        >
          <p style={{ marginTop: 0 }}>
            <strong>Plaintext for &quot;{minted.label}&quot;</strong> — copy now; this is the
            only time it will be shown.
          </p>
          <code
            style={{
              display: "block",
              padding: "0.5rem",
              fontFamily: "'IBM Plex Mono', monospace",
              wordBreak: "break-all",
              background: "rgba(0,0,0,0.25)",
              userSelect: "all",
            }}
          >
            {minted.plaintext}
          </code>
          <button
            type="button"
            onClick={() => navigator.clipboard?.writeText(minted.plaintext)}
            style={{ marginTop: "0.5rem" }}
          >
            Copy
          </button>
        </div>
      )}

      {canWrite && (
        <form
          onSubmit={onMint}
          style={{
            display: "grid",
            gap: "0.75rem",
            marginBottom: "2rem",
            padding: "1rem",
            border: "1px solid var(--stroke, var(--amber-deep))",
            borderRadius: 4,
          }}
        >
          <h2 style={{ marginTop: 0 }}>Mint new key</h2>
          <label style={{ display: "grid", gap: 4 }}>
            <span>Label</span>
            <input
              required
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="Dialectic on laptop"
              style={{ padding: "0.5rem" }}
            />
          </label>
          <label style={{ display: "grid", gap: 4 }}>
            <span>Scope</span>
            <select value={scope} onChange={(e) => setScope(e.target.value)} style={{ padding: "0.5rem" }}>
              {SCOPE_OPTIONS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.value} — {s.description}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" disabled={!label.trim()}>
            Mint key
          </button>
        </form>
      )}

      <h2>Active keys</h2>
      {sortedKeys.length === 0 ? (
        <p style={{ color: "var(--parchment-dim)" }}>No active keys.</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={th}>Label</th>
              <th style={th}>Prefix</th>
              <th style={th}>Scope</th>
              <th style={th}>Created</th>
              <th style={th}>Last used</th>
              {canWrite && <th style={th}>Actions</th>}
            </tr>
          </thead>
          <tbody>
            {sortedKeys.map((k) => (
              <tr key={k.id}>
                <td style={td}>{k.label}</td>
                <td style={{ ...td, fontFamily: "'IBM Plex Mono', monospace" }}>{k.prefix}…</td>
                <td style={td}>{k.scopes || "(legacy: full)"}</td>
                <td style={td}>{fmt(k.createdAt)}</td>
                <td style={td}>{fmt(k.lastUsedAt)}</td>
                {canWrite && (
                  <td style={td}>
                    <button
                      type="button"
                      onClick={() => onRotate(k)}
                      disabled={busyId === k.id}
                      style={{ marginRight: "0.5rem" }}
                    >
                      Rotate
                    </button>
                    <button
                      type="button"
                      onClick={() => onRevoke(k.id)}
                      disabled={busyId === k.id}
                    >
                      Revoke
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

const th: React.CSSProperties = {
  textAlign: "left",
  padding: "0.5rem 0.4rem",
  borderBottom: "1px solid var(--stroke, var(--amber-deep))",
  fontSize: "0.75rem",
  letterSpacing: "0.18em",
  textTransform: "uppercase",
  color: "var(--amber-dim)",
};

const td: React.CSSProperties = {
  padding: "0.5rem 0.4rem",
  borderBottom: "1px solid rgba(212, 160, 23, 0.1)",
  fontSize: "0.9rem",
  color: "var(--parchment)",
};
