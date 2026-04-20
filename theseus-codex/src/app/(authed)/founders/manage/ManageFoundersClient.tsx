"use client";

import { useMemo, useState, useTransition } from "react";
import { ROLE_DESCRIPTIONS, type FounderRole } from "@/lib/roles";

interface FounderRow {
  id: string;
  name: string;
  email: string;
  username: string;
  role: string; // string from DB; widened so we don't crash on legacy values
  createdAt: string;
}

interface SaveState {
  status: "idle" | "saving" | "saved" | "error";
  message?: string;
}

const ROLE_ORDER: FounderRole[] = ["admin", "founder", "viewer"];

/**
 * Client-side founder-row table for /founders/manage.
 *
 * Renders a row per founder with a role <select>. Changing the
 * dropdown immediately POSTs the new role to PATCH
 * /api/founders/:id/role and reflects the result inline:
 *
 *   "saving…"   the request is in flight (dropdown disabled)
 *   "saved"     the server accepted the change; row's role is now updated
 *   "error"     the server returned a 4xx/5xx — message surfaces below
 *               the dropdown and the dropdown reverts to the previous
 *               role so the UI never claims a state the server doesn't
 *               agree with.
 *
 * The "current" founder (the admin viewing this page) is rendered with
 * a subtle annotation but their dropdown is otherwise enabled — the
 * server enforces the last-admin-demotion guard, and the message it
 * returns ("This would leave the organisation with no admins…") is
 * surfaced verbatim.
 */
export default function ManageFoundersClient({
  founders: initialFounders,
  currentFounderId,
}: {
  founders: FounderRow[];
  currentFounderId: string;
}) {
  const [founders, setFounders] = useState<FounderRow[]>(initialFounders);
  const [pending, startTransition] = useTransition();
  // Per-row save state, keyed on founder.id. Only rows that have been
  // touched ever appear here, so a fresh page render shows "idle" for
  // every row without us pre-populating the map.
  const [saveStates, setSaveStates] = useState<Record<string, SaveState>>({});

  const adminCount = useMemo(
    () => founders.filter((f) => f.role === "admin").length,
    [founders],
  );

  async function changeRole(founderId: string, newRole: FounderRole) {
    const previousRole = founders.find((f) => f.id === founderId)?.role;
    if (!previousRole || previousRole === newRole) return;
    setSaveStates((s) => ({ ...s, [founderId]: { status: "saving" } }));
    // Optimistic update: flip the row's role immediately so the
    // dropdown reflects the user's intent. Roll back on error.
    setFounders((rows) =>
      rows.map((r) => (r.id === founderId ? { ...r, role: newRole } : r)),
    );

    try {
      const res = await fetch(`/api/founders/${founderId}/role`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role: newRole }),
      });
      const body = (await res.json().catch(() => ({}))) as {
        ok?: boolean;
        error?: string;
        founder?: { role: string };
      };
      if (!res.ok || !body.ok) {
        setFounders((rows) =>
          rows.map((r) =>
            r.id === founderId ? { ...r, role: previousRole } : r,
          ),
        );
        setSaveStates((s) => ({
          ...s,
          [founderId]: {
            status: "error",
            message: body.error || `Save failed (${res.status})`,
          },
        }));
        return;
      }
      setSaveStates((s) => ({
        ...s,
        [founderId]: { status: "saved" },
      }));
      // After a moment, fade the "saved" indicator back to idle so the
      // table doesn't permanently advertise stale "saved!" states.
      window.setTimeout(() => {
        setSaveStates((s) => {
          const next = { ...s };
          delete next[founderId];
          return next;
        });
      }, 2400);
    } catch (err) {
      setFounders((rows) =>
        rows.map((r) =>
          r.id === founderId ? { ...r, role: previousRole } : r,
        ),
      );
      setSaveStates((s) => ({
        ...s,
        [founderId]: {
          status: "error",
          message: err instanceof Error ? err.message : "Network error",
        },
      }));
    }
  }

  return (
    <div>
      <p
        className="mono"
        style={{
          fontSize: "0.65rem",
          letterSpacing: "0.16em",
          textTransform: "uppercase",
          color: "var(--parchment-dim)",
          marginBottom: "1rem",
        }}
      >
        {founders.length} founder{founders.length === 1 ? "" : "s"} ·{" "}
        {adminCount} admin{adminCount === 1 ? "" : "s"}
      </p>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "0.55rem",
        }}
      >
        {founders.map((f) => {
          const state = saveStates[f.id] || { status: "idle" };
          const isSelf = f.id === currentFounderId;
          const isOnlyAdmin = adminCount === 1 && f.role === "admin";

          return (
            <div
              key={f.id}
              className="portal-card"
              style={{
                display: "grid",
                gridTemplateColumns: "1fr auto auto",
                alignItems: "center",
                gap: "1rem",
                padding: "0.85rem 1rem",
                opacity: pending ? 0.85 : 1,
              }}
            >
              <div style={{ minWidth: 0 }}>
                <div
                  style={{
                    fontFamily: "'EB Garamond', serif",
                    fontSize: "1.05rem",
                    color: "var(--amber)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {f.name}
                  {isSelf ? (
                    <span
                      className="mono"
                      style={{
                        marginLeft: "0.5rem",
                        fontSize: "0.55rem",
                        letterSpacing: "0.2em",
                        textTransform: "uppercase",
                        color: "var(--amber-dim)",
                        border: "1px solid var(--amber-dim)",
                        padding: "0.08rem 0.4rem",
                        borderRadius: 2,
                      }}
                    >
                      You
                    </span>
                  ) : null}
                </div>
                <div
                  className="mono"
                  style={{
                    fontSize: "0.65rem",
                    letterSpacing: "0.08em",
                    color: "var(--parchment-dim)",
                    marginTop: "0.2rem",
                  }}
                >
                  @{f.username} · {f.email}
                </div>
              </div>

              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "flex-end",
                  gap: "0.2rem",
                  minWidth: "12rem",
                }}
              >
                <select
                  value={f.role}
                  onChange={(e) =>
                    startTransition(() => {
                      void changeRole(f.id, e.target.value as FounderRole);
                    })
                  }
                  disabled={state.status === "saving"}
                  title={
                    isOnlyAdmin
                      ? "This founder is currently the only admin. Promote someone else before demoting them."
                      : ROLE_DESCRIPTIONS[f.role as FounderRole] ?? ""
                  }
                  style={{
                    fontFamily: "'IBM Plex Mono', monospace",
                    fontSize: "0.78rem",
                    letterSpacing: "0.08em",
                    padding: "0.35rem 0.6rem",
                    background: "var(--stone-light)",
                    color: "var(--amber)",
                    border: "1px solid var(--amber-dim)",
                    borderRadius: 2,
                    cursor:
                      state.status === "saving" ? "wait" : "pointer",
                  }}
                >
                  {ROLE_ORDER.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
                {state.status === "saving" ? (
                  <span
                    className="mono"
                    style={{
                      fontSize: "0.55rem",
                      letterSpacing: "0.18em",
                      color: "var(--amber-dim)",
                    }}
                  >
                    saving…
                  </span>
                ) : null}
                {state.status === "saved" ? (
                  <span
                    className="mono"
                    style={{
                      fontSize: "0.55rem",
                      letterSpacing: "0.18em",
                      color: "var(--success, #6ed0a8)",
                    }}
                  >
                    saved
                  </span>
                ) : null}
                {state.status === "error" ? (
                  <span
                    className="mono"
                    style={{
                      fontSize: "0.6rem",
                      color: "var(--ember)",
                      textAlign: "right",
                      maxWidth: "20rem",
                    }}
                  >
                    {state.message}
                  </span>
                ) : null}
              </div>

              <div
                style={{
                  fontFamily: "'IBM Plex Mono', monospace",
                  fontSize: "0.6rem",
                  color: "var(--parchment-dim)",
                  whiteSpace: "nowrap",
                }}
                title={`Joined ${f.createdAt}`}
              >
                {f.createdAt.slice(0, 10)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
