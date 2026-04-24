/**
 * Founder role ladder + permission predicates.
 *
 * Every founder in the database carries a `role: string` column with one
 * of three values. The string is intentionally free-form (no enum at the
 * Prisma level) so adding a new tier later doesn't require a migration —
 * the SQL column stays `TEXT`, the validation lives here at the
 * application boundary.
 *
 * The ladder
 * ----------
 *
 *   admin    → full read + write + can change other founders' roles
 *              (the "alpha" tier; the only role that can promote /
 *              demote others). At least one admin must always exist
 *              per organization — see `/api/founders/[id]/role` for
 *              the self-demotion guard.
 *
 *   founder  → full read + write. Can upload files, publish posts,
 *              run peer reviews, request deletions, etc. The default
 *              for everyone added via `scripts/add-founder.ts`. This
 *              is the standard-issue role.
 *
 *   viewer   → read-only. Can navigate the entire portal — library,
 *              dashboard, conclusions, /ask, /post/<slug>, etc. — and
 *              read every artifact the org has produced, but every
 *              write affordance (upload, publish, delete, peer-review
 *              vote, request-deletion, dashboard dismissal, …) is
 *              disabled in the UI and rejected with 403 at the API.
 *              Useful for advisors, auditors, board observers, future
 *              hires you want to read-only-onboard before flipping
 *              them to founder.
 *
 * Where this is used
 * ------------------
 *
 *   • API gates: every write endpoint calls `canWrite(founder.role)`
 *     and 403s if false. The check happens AFTER auth (so an
 *     unauthenticated caller still gets 401, not 403) and BEFORE any
 *     side-effecting work.
 *
 *   • UI gates: server components pass the role into client components
 *     via the (authed) layout's `getFounder().role`. Client components
 *     hide write affordances based on the predicates here. The UI gate
 *     is a UX nicety; the API gate is the actual security boundary.
 *
 *   • Founder management: only admins see the /founders/manage page
 *     and `canManageFounders(role)` returns true.
 *
 * Why three roles instead of N permission flags
 * ---------------------------------------------
 *
 * The Codex's threat model is "trusted firm members with different
 * levels of write authority", not "complex multi-tenant marketplace".
 * Three labelled tiers are easier to reason about than a permissions
 * matrix and cover every case the product has surfaced so far.
 * Per-action permission flags can be layered on later if a real
 * use-case demands them.
 */

export type FounderRole = "admin" | "founder" | "viewer";

const VALID_ROLES: ReadonlySet<string> = new Set([
  "admin",
  "founder",
  "viewer",
]);

/**
 * Type-narrow + validate a string from the wire / DB into our role
 * union. Defaults are intentionally NOT applied here — callers should
 * decide whether an unknown role means "block" (most write APIs) or
 * "treat as viewer" (most UI surfaces).
 */
export function isValidRole(value: unknown): value is FounderRole {
  return typeof value === "string" && VALID_ROLES.has(value);
}

/**
 * Normalise a role string to a known value. Anything we don't
 * recognise — empty string, legacy uppercase, accidental whitespace,
 * unmigrated old enum — collapses to the safest fallback ("viewer"),
 * so a corrupted DB row can't accidentally elevate someone.
 */
export function normaliseRole(value: unknown): FounderRole {
  if (!isValidRole(value)) return "viewer";
  return value;
}

/** Every signed-in role can read. */
export function canRead(role: string): boolean {
  return isValidRole(role);
}

/**
 * "Write" = anything that changes durable state on behalf of this
 * founder. Uploading, publishing, deleting, requesting deletion,
 * casting a peer-review verdict, dismissing a dashboard item, etc.
 * Read-only API endpoints (/api/library, /api/upload/:id GET,
 * /api/ask) are NOT gated by this — viewers can see everything
 * they're authorised to see in their org.
 */
export function canWrite(role: string): boolean {
  return role === "admin" || role === "founder";
}

/**
 * Only admins can change other founders' roles. The /founders/manage
 * page checks this server-side; the PATCH /api/founders/:id/role
 * endpoint re-checks it and additionally guards against demoting the
 * last admin in the organisation (so an org can't accidentally lock
 * itself out of role management).
 */
export function canManageFounders(role: string): boolean {
  return role === "admin";
}

/**
 * Human-readable description for the role ladder. Surfaced in the
 * /founders/manage UI dropdown so the admin doesn't have to remember
 * what each label implies.
 */
export const ROLE_DESCRIPTIONS: Record<FounderRole, string> = {
  admin:
    "Full access. Can upload, publish, delete, AND change other founders' roles.",
  founder:
    "Standard access. Can upload, publish, delete, run peer reviews. Cannot change others' roles.",
  viewer:
    "Read-only. Can navigate the entire portal but every write action is blocked.",
};

/**
 * Standard JSON shape for the 403 a write endpoint returns when the
 * caller's role is below `canWrite`. Surfaces a stable error string
 * the client can match on if it wants to render a special "ask an
 * admin to upgrade you" affordance.
 */
export const WRITE_FORBIDDEN_RESPONSE = {
  error:
    "This account is read-only. An admin in your organisation must upgrade you to 'founder' or 'admin' before you can take this action.",
  code: "viewer_write_forbidden" as const,
};

/**
 * Standard JSON shape for the 403 the founder-management endpoint
 * returns when a non-admin tries to change someone's role.
 */
export const MANAGE_FORBIDDEN_RESPONSE = {
  error:
    "Only admins can change founder roles. Ask an admin in your organisation to make the change for you.",
  code: "manage_founders_forbidden" as const,
};
