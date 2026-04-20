import { redirect } from "next/navigation";
import { db } from "@/lib/db";
import { canManageFounders } from "@/lib/roles";
import { requireTenantContext } from "@/lib/tenant";
import ManageFoundersClient from "./ManageFoundersClient";

/**
 * Admin-only founder management page.
 *
 * Lists every founder in the caller's organisation along with their
 * current role and a dropdown to change it. The dropdown calls the
 * PATCH /api/founders/:id/role endpoint, which:
 *   * re-checks `canManageFounders` server-side (so the page being
 *     reachable doesn't itself confer the power);
 *   * enforces the same-org rule;
 *   * blocks the last-admin demotion case.
 *
 * Non-admins who navigate here directly get redirected to /dashboard
 * — same effect as if the page didn't exist for them. The Nav also
 * hides the "Manage" link for non-admins, so the only path here for
 * a viewer/founder is typing the URL by hand.
 *
 * Why this lives at /founders/manage rather than as a section on
 * /founders: the existing /founders page is a public-to-the-firm
 * profile gallery (everyone sees everyone's bio + upload counts).
 * Layering admin controls into it would mean every founder loads
 * the management UI on every visit just to see it greyed out, and
 * every render would have to branch on role. A dedicated subroute
 * keeps the admin surface separate, cheap to render for non-admins
 * (instant redirect, no client bundle), and trivial to extend later
 * (audit log of role changes, bulk operations, etc.).
 */
export default async function ManageFoundersPage() {
  const tenant = await requireTenantContext();
  if (!tenant) return null;
  if (!canManageFounders(tenant.role)) {
    redirect("/dashboard");
  }

  const founders = await db.founder.findMany({
    where: { organizationId: tenant.organizationId },
    orderBy: [{ role: "asc" }, { createdAt: "asc" }],
    select: {
      id: true,
      name: true,
      email: true,
      username: true,
      role: true,
      createdAt: true,
    },
  });

  return (
    <main
      style={{
        maxWidth: "960px",
        margin: "0 auto",
        padding: "3rem 2rem",
      }}
    >
      <header style={{ marginBottom: "2rem" }}>
        <h1
          style={{
            fontFamily: "'Cinzel Decorative', 'Cinzel', serif",
            fontSize: "1.8rem",
            letterSpacing: "0.18em",
            color: "var(--amber)",
            textShadow: "var(--glow-md)",
            margin: 0,
          }}
        >
          Imperium
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
          Manage founders · Role assignments
        </p>
        <p
          style={{
            fontFamily: "'EB Garamond', serif",
            fontStyle: "italic",
            fontSize: "1rem",
            color: "var(--parchment-dim)",
            marginTop: "0.75rem",
            lineHeight: 1.55,
            maxWidth: "44em",
          }}
        >
          Move founders up and down the role ladder. <strong>Admin</strong>{" "}
          can do everything (read, write, change roles).{" "}
          <strong>Founder</strong> can read and write (upload, publish,
          delete, vote in peer review). <strong>Viewer</strong> can read
          but every write action is blocked. The last admin in the
          organisation cannot demote themselves — promote someone else
          first.
        </p>
      </header>

      <ManageFoundersClient
        currentFounderId={tenant.founderId}
        founders={founders.map((f) => ({
          id: f.id,
          name: f.name,
          email: f.email,
          username: f.username,
          role: f.role,
          createdAt: f.createdAt.toISOString(),
        }))}
      />
    </main>
  );
}
