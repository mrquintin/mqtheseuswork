/**
 * PATCH /api/founders/:id/role
 *
 * Admin-only endpoint for changing another founder's role on the
 * organisation's role ladder. The full ladder + per-tier semantics
 * lives in `src/lib/roles.ts`; this route is the only path through
 * which a role can be flipped from outside the database.
 *
 * Request body: `{ role: "admin" | "founder" | "viewer" }`
 *
 * Authorisation
 * -------------
 *   * Caller must be authenticated (cookie session OR Bearer API
 *     key — same as every other write API).
 *   * Caller must have `role === "admin"` (the only tier that
 *     `canManageFounders` returns true for).
 *   * Target founder must exist AND be in the caller's organisation
 *     — we never let an admin in Org A flip the role of someone in
 *     Org B, regardless of how the id was obtained.
 *
 * Last-admin protection
 * ---------------------
 * If demoting the target would leave the organisation with ZERO
 * remaining admins, the request is rejected with 409. This is the
 * one case the admin can't talk their way out of from this endpoint
 * — they have to promote someone ELSE to admin first, then come
 * back and demote themselves. Without this guard a single careless
 * click on the management page could permanently lock the org out
 * of role management (the only way back would be an admin running
 * `scripts/add-founder.ts` against the DB directly).
 *
 * No-op semantics
 * ---------------
 * Re-assigning a founder to the role they already have is allowed
 * and returns 200 with no audit event written. Keeps the UI's
 * dropdown-onChange flow simple — clicking the same option twice
 * doesn't surface an error.
 *
 * Side effects on success
 * -----------------------
 *   * Founder.role updated.
 *   * AuditEvent written: action = "role_change", detail captures
 *     {targetId, oldRole, newRole, byFounderId}.
 *   * Sessions are NOT invalidated — a viewer-promoted-to-founder
 *     keeps their existing cookie and gains write access on the next
 *     request. A founder-demoted-to-viewer also keeps their session,
 *     but every write API will now 403 them. Both are intentional:
 *     forcing a re-login on a role change would be jarring for the
 *     promoted user and unhelpful for the demoted one (their
 *     session ending wouldn't actually revoke any access they no
 *     longer have).
 */
import { NextResponse } from "next/server";
import { getFounderFromAuth } from "@/lib/apiKeyAuth";
import { db } from "@/lib/db";
import {
  canManageFounders,
  isValidRole,
  MANAGE_FORBIDDEN_RESPONSE,
  type FounderRole,
} from "@/lib/roles";

export async function PATCH(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const founder = await getFounderFromAuth(req);
    if (!founder) {
      return NextResponse.json(
        { error: "Not authenticated" },
        { status: 401 },
      );
    }
    if (!canManageFounders(founder.role)) {
      return NextResponse.json(MANAGE_FORBIDDEN_RESPONSE, { status: 403 });
    }

    const { id: targetId } = await params;
    const body = (await req.json().catch(() => ({}))) as { role?: string };
    const newRole = body.role;
    if (!isValidRole(newRole)) {
      return NextResponse.json(
        {
          error:
            'role is required and must be one of "admin", "founder", "viewer".',
        },
        { status: 400 },
      );
    }

    // Same-org gate — admins can only manage their own organisation.
    const target = await db.founder.findUnique({
      where: { id: targetId },
      select: { id: true, role: true, organizationId: true, name: true, email: true },
    });
    if (!target || target.organizationId !== founder.organizationId) {
      // Generic 404 — don't confirm that a cross-org founder exists.
      return NextResponse.json({ error: "Founder not found" }, { status: 404 });
    }

    // No-op fast path: dropdown re-confirmation, no audit event.
    if (target.role === newRole) {
      return NextResponse.json({
        ok: true,
        founder: { id: target.id, role: target.role },
        changed: false,
      });
    }

    // Last-admin protection: if this flip would leave the org with
    // zero admins, refuse. Only relevant when we're DEMOTING the
    // target — promoting to admin always leaves admin count ≥ 1.
    if (target.role === "admin" && newRole !== "admin") {
      const remainingAdmins = await db.founder.count({
        where: {
          organizationId: founder.organizationId,
          role: "admin",
          id: { not: target.id },
        },
      });
      if (remainingAdmins === 0) {
        return NextResponse.json(
          {
            error:
              "This would leave the organisation with no admins. Promote someone else to admin first, then come back and change this role.",
            code: "last_admin_demotion_blocked",
          },
          { status: 409 },
        );
      }
    }

    const updated = await db.$transaction(async (tx) => {
      const u = await tx.founder.update({
        where: { id: target.id },
        data: { role: newRole as FounderRole },
        select: { id: true, role: true, name: true, email: true },
      });
      await tx.auditEvent.create({
        data: {
          organizationId: founder.organizationId,
          founderId: founder.id,
          action: "role_change",
          detail: JSON.stringify({
            targetFounderId: target.id,
            targetEmail: target.email,
            targetName: target.name,
            oldRole: target.role,
            newRole,
          }),
        },
      });
      return u;
    });

    return NextResponse.json({
      ok: true,
      founder: updated,
      changed: true,
    });
  } catch (error) {
    console.error("founders/[id]/role PATCH error:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}
