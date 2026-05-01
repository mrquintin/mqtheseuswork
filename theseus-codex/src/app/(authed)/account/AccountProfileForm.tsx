"use client";

import { useState } from "react";

export default function AccountProfileForm({
  initialDisplayName,
  initialRoleTitle,
  initialPublicUrl,
  initialBio,
  email,
}: {
  initialDisplayName: string;
  initialRoleTitle: string;
  initialPublicUrl: string;
  initialBio: string;
  email: string;
}) {
  const [displayName, setDisplayName] = useState(initialDisplayName);
  const [roleTitle, setRoleTitle] = useState(initialRoleTitle);
  const [publicUrl, setPublicUrl] = useState(initialPublicUrl);
  const [bio, setBio] = useState(initialBio);
  const [state, setState] = useState<"idle" | "saving" | "ok" | "error">(
    "idle",
  );
  const [message, setMessage] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setState("saving");
    setMessage("");

    try {
      const res = await fetch("/api/account", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ displayName, roleTitle, publicUrl, bio }),
      });
      const data = (await res.json().catch(() => ({}))) as {
        ok?: boolean;
        error?: string;
        founder?: {
          displayName?: string | null;
          roleTitle?: string | null;
          publicUrl?: string | null;
          bio?: string | null;
        };
      };

      if (!res.ok || !data.ok) {
        setState("error");
        setMessage(data.error || `Save failed (${res.status})`);
        return;
      }

      setDisplayName(data.founder?.displayName ?? displayName);
      setRoleTitle(data.founder?.roleTitle ?? "");
      setPublicUrl(data.founder?.publicUrl ?? "");
      setBio(data.founder?.bio ?? "");
      setState("ok");
      setMessage("Profile saved.");
    } catch (err) {
      setState("error");
      setMessage(err instanceof Error ? err.message : "Network error");
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="ascii-frame"
      data-label="PUBLIC PROFILE"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "1rem",
        padding: "1.25rem 1.5rem",
        marginBottom: "2rem",
      }}
    >
      <Labelled
        label="Display name"
        hint="2-60 characters. This is what peers and readers see."
      >
        <input
          name="displayName"
          type="text"
          autoComplete="name"
          minLength={2}
          maxLength={60}
          required
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          disabled={state === "saving"}
        />
      </Labelled>

      <Labelled
        label="Public role title"
        hint="Optional. Shown on the public About page; internal roles are never shown there."
      >
        <input
          name="roleTitle"
          type="text"
          maxLength={80}
          value={roleTitle}
          onChange={(e) => setRoleTitle(e.target.value)}
          disabled={state === "saving"}
        />
      </Labelled>

      <Labelled label="Public link" hint="Optional LinkedIn or personal site URL.">
        <input
          name="publicUrl"
          type="url"
          autoComplete="url"
          maxLength={2048}
          placeholder="https://"
          value={publicUrl}
          onChange={(e) => setPublicUrl(e.target.value)}
          disabled={state === "saving"}
        />
      </Labelled>

      <Labelled label="Bio" hint={`${500 - bio.length} characters remaining.`}>
        <textarea
          name="bio"
          rows={5}
          maxLength={500}
          value={bio}
          onChange={(e) => setBio(e.target.value)}
          disabled={state === "saving"}
          style={{ resize: "vertical" }}
        />
      </Labelled>

      <Labelled label="Email" hint="Email changes require a separate sensitive flow.">
        <input
          type="email"
          value={email}
          readOnly
          aria-readonly="true"
          style={{ opacity: 0.75 }}
        />
      </Labelled>

      {message ? (
        <p
          role="status"
          style={{
            margin: 0,
            fontSize: "0.85rem",
            color:
              state === "ok"
                ? "var(--success, #6ed0a8)"
                : state === "error"
                  ? "var(--ember)"
                  : "var(--parchment-dim)",
          }}
        >
          {message}
        </p>
      ) : null}

      <button
        type="submit"
        className="btn-solid btn"
        disabled={state === "saving"}
        style={{ alignSelf: "flex-start" }}
      >
        {state === "saving" ? "Saving..." : "Save profile"}
      </button>
    </form>
  );
}

function Labelled({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
      <span
        className="mono"
        style={{
          fontSize: "0.65rem",
          letterSpacing: "0.2em",
          textTransform: "uppercase",
          color: "var(--amber-dim)",
        }}
      >
        {label}
      </span>
      {children}
      {hint ? (
        <span
          style={{
            fontSize: "0.75rem",
            color: "var(--parchment-dim)",
            lineHeight: 1.45,
          }}
        >
          {hint}
        </span>
      ) : null}
    </label>
  );
}
