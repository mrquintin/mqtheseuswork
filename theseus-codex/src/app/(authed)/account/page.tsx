import Link from "next/link";
import ChangePasswordForm from "./ChangePasswordForm";
import { requireTenantContext } from "@/lib/tenant";
import { db } from "@/lib/db";

/**
 * /account — per-founder settings. v1 exposes passphrase rotation +
 * a read-only summary of the current identity (who you're signed in
 * as, which org, when the account was created). Future additions —
 * display name, bio, avatar upload, email change — slot in as
 * additional framed panels below the passphrase panel without
 * touching the shell.
 */
export default async function AccountPage() {
  const tenant = await requireTenantContext();
  if (!tenant) return null;

  const founder = await db.founder.findUnique({
    where: { id: tenant.founderId },
    select: {
      id: true,
      name: true,
      username: true,
      email: true,
      role: true,
      createdAt: true,
      updatedAt: true,
      organization: { select: { slug: true, name: true } },
    },
  });
  if (!founder) return null;

  return (
    <main
      style={{
        maxWidth: "760px",
        margin: "0 auto",
        padding: "2.5rem 2rem 4rem",
      }}
    >
      <header style={{ marginBottom: "2rem" }}>
        <h1
          style={{
            fontFamily: "'Cinzel Decorative', 'Cinzel', serif",
            fontSize: "2rem",
            letterSpacing: "0.18em",
            color: "var(--amber)",
            textShadow: "var(--glow-md)",
            margin: 0,
          }}
        >
          Rationes
        </h1>
        <p
          className="mono"
          style={{
            fontSize: "0.62rem",
            letterSpacing: "0.28em",
            textTransform: "uppercase",
            color: "var(--amber-dim)",
            marginTop: "0.25rem",
            marginBottom: 0,
          }}
        >
          Account · Identity and credentials
        </p>
        <p
          style={{
            fontFamily: "'EB Garamond', serif",
            fontStyle: "italic",
            fontSize: "1.05rem",
            color: "var(--parchment-dim)",
            marginTop: "0.6rem",
            marginBottom: 0,
            lineHeight: 1.55,
          }}
        >
          Your sign-in identity for the Codex and the desk apps. Changing
          your passphrase signs out every other device — you stay signed
          in here.
        </p>
      </header>

      {/* ── Identity summary ────────────────────────────────────── */}
      <section
        className="ascii-frame"
        data-label="IDENTITY"
        style={{
          marginBottom: "2rem",
          padding: "1rem 1.25rem",
          display: "grid",
          gridTemplateColumns: "max-content 1fr",
          columnGap: "1.25rem",
          rowGap: "0.45rem",
          fontSize: "0.92rem",
        }}
      >
        <span
          className="mono"
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.6rem",
            letterSpacing: "0.22em",
            textTransform: "uppercase",
          }}
        >
          Name
        </span>
        <span style={{ color: "var(--parchment)" }}>{founder.name}</span>

        <span
          className="mono"
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.6rem",
            letterSpacing: "0.22em",
            textTransform: "uppercase",
          }}
        >
          Email
        </span>
        <span
          style={{
            color: "var(--parchment)",
            fontFamily: "'IBM Plex Mono', monospace",
            fontSize: "0.85rem",
          }}
        >
          {founder.email}
        </span>

        <span
          className="mono"
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.6rem",
            letterSpacing: "0.22em",
            textTransform: "uppercase",
          }}
        >
          Username
        </span>
        <span
          style={{
            color: "var(--parchment)",
            fontFamily: "'IBM Plex Mono', monospace",
            fontSize: "0.85rem",
          }}
        >
          {founder.username}
        </span>

        <span
          className="mono"
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.6rem",
            letterSpacing: "0.22em",
            textTransform: "uppercase",
          }}
        >
          Role
        </span>
        <span style={{ color: "var(--parchment)" }}>{founder.role}</span>

        <span
          className="mono"
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.6rem",
            letterSpacing: "0.22em",
            textTransform: "uppercase",
          }}
        >
          Organization
        </span>
        <span style={{ color: "var(--parchment)" }}>
          {founder.organization?.name || founder.organization?.slug || "—"}{" "}
          <span
            className="mono"
            style={{ color: "var(--amber-dim)", fontSize: "0.75rem" }}
          >
            {founder.organization?.slug
              ? `(${founder.organization.slug})`
              : ""}
          </span>
        </span>

        <span
          className="mono"
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.6rem",
            letterSpacing: "0.22em",
            textTransform: "uppercase",
          }}
        >
          Member since
        </span>
        <span style={{ color: "var(--parchment)" }}>
          {new Date(founder.createdAt).toLocaleDateString(undefined, {
            year: "numeric",
            month: "long",
            day: "numeric",
          })}
        </span>
      </section>

      {/* ── Passphrase rotation ─────────────────────────────────── */}
      <ChangePasswordForm />

      {/* ── Device credentials pointer ──────────────────────────── */}
      <aside
        style={{
          marginTop: "1.75rem",
          padding: "0.9rem 1.1rem",
          border: "1px solid var(--stroke, var(--amber-deep))",
          borderRadius: "4px",
          background: "rgba(212, 160, 23, 0.04)",
          fontSize: "0.88rem",
          color: "var(--parchment-dim)",
          lineHeight: 1.5,
        }}
      >
        Device / CLI credentials (Dialectic, Noosphere) are API keys —
        they&rsquo;re <strong>not</strong> reset when you change your
        passphrase. Review and revoke them individually from{" "}
        <Link
          href="/api-keys"
          style={{
            color: "var(--amber)",
            textDecoration: "underline",
          }}
        >
          /api-keys
        </Link>{" "}
        if you think any have been compromised.
      </aside>
    </main>
  );
}
