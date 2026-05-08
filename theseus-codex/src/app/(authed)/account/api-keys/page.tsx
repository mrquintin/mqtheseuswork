import { redirect } from "next/navigation";

import { requireTenantContext } from "@/lib/tenant";
import { db } from "@/lib/db";
import ApiKeysClient from "./ApiKeysClient";

/**
 * /account/api-keys — founder-facing key management.
 *
 * Renders the live list of non-revoked keys (label, prefix, scopes,
 * created, last-used) plus mint, rotate, and revoke affordances.
 * Plaintext is shown exactly once at mint time, with a copy-to-clipboard
 * button — the server side stores only the bcrypt hash.
 *
 * Server-side gates:
 *   - `requireTenantContext` enforces auth + role membership
 *     (viewers can read this page, but the API mint/revoke routes
 *     also CSRF- and auth-check on POST/DELETE).
 *   - The mint and revoke API routes (`/api/auth/api-keys`) require
 *     a CSRF header; the client reads the cookie set by the
 *     middleware and echoes it back.
 *
 * See `docs/security/Threat_Model.md` §3.3 for the rationale.
 */
export default async function ApiKeysPage() {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login?next=/account/api-keys");

  const keys = await db.apiKey.findMany({
    where: { founderId: tenant.founderId, revokedAt: null },
    select: {
      id: true,
      label: true,
      prefix: true,
      scopes: true,
      createdAt: true,
      lastUsedAt: true,
    },
    orderBy: { createdAt: "desc" },
  });

  const initial = keys.map((k) => ({
    id: k.id,
    label: k.label,
    prefix: k.prefix,
    scopes: k.scopes ?? "",
    createdAt: k.createdAt.toISOString(),
    lastUsedAt: k.lastUsedAt ? k.lastUsedAt.toISOString() : null,
  }));

  const canWrite = tenant.role === "admin" || tenant.role === "founder";

  return (
    <main style={{ maxWidth: "880px", margin: "0 auto", padding: "2.5rem 2rem 4rem" }}>
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
          API Keys
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
          Account · Machine credentials
        </p>
        <p
          style={{
            fontFamily: "'EB Garamond', serif",
            fontStyle: "italic",
            fontSize: "1.0rem",
            color: "var(--parchment-dim)",
            marginTop: "0.6rem",
            marginBottom: 0,
            lineHeight: 1.55,
          }}
        >
          Each key carries a scope. <strong>read</strong> grants
          read-only access. <strong>write</strong> permits uploads
          and edits. <strong>publish</strong> additionally permits
          signed publication. Treat every key like a password; the
          plaintext is shown once.
        </p>
      </header>

      <ApiKeysClient initialKeys={initial} canWrite={canWrite} />
    </main>
  );
}
