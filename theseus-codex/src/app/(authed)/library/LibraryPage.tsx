import LibraryBrowser from "./LibraryBrowser";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { db } from "@/lib/db";
import { canWrite } from "@/lib/roles";
import { requireTenantContext } from "@/lib/tenant";

/**
 * /library — org-wide upload inventory.
 *
 * The Codex is collective. Every founder can see what's in the library
 * and who put it there. Only owners can delete their own entries; peers
 * can open a "please delete" request that the owner reviews.
 *
 * The server component here does only the auth check — all data
 * fetching is in the client component so we can reload after every
 * mutation (accept / decline / delete / request / cancel) without a
 * full page navigation.
 */
type LibrarySearchParams = {
  request?: string;
  requested?: string;
  error?: string;
};

async function LibraryContent({
  searchParams,
}: {
  searchParams: Promise<LibrarySearchParams>;
}) {
  const tenant = await requireTenantContext();
  if (!tenant) return null;

  const sp = await searchParams;
  const requestConclusionId = String(sp.request || "").trim();
  const deletionTarget = requestConclusionId
    ? await db.conclusion.findFirst({
        where: {
          id: requestConclusionId,
          organizationId: tenant.organizationId,
        },
        select: {
          id: true,
          text: true,
          confidenceTier: true,
          topicHint: true,
        },
      })
    : null;
  const existingConclusionDeletionRequest = deletionTarget
    ? await db.conclusionDeletionRequest.findFirst({
        where: {
          conclusionId: deletionTarget.id,
          requesterId: tenant.founderId,
          status: "pending",
        },
        select: { id: true },
      })
    : null;

  async function requestConclusionDeletionFromLibrary(formData: FormData) {
    "use server";
    const conclusionId = String(formData.get("conclusionId") || "").trim();
    const reason = String(formData.get("reason") || "").trim();
    const currentTenant = await requireTenantContext();
    if (!currentTenant) redirect("/login");
    if (!conclusionId) redirect("/library?error=missing-conclusion");

    if (!canWrite(currentTenant.role)) {
      redirect(
        `/library?request=${encodeURIComponent(
          conclusionId,
        )}&error=readonly#conclusion-deletion-request`,
      );
    }

    const conclusion = await db.conclusion.findFirst({
      where: {
        id: conclusionId,
        organizationId: currentTenant.organizationId,
      },
      select: { id: true },
    });
    if (!conclusion) {
      redirect("/library?error=not-found#conclusion-deletion-request");
    }

    const existing = await db.conclusionDeletionRequest.findFirst({
      where: {
        conclusionId,
        requesterId: currentTenant.founderId,
        status: "pending",
      },
      select: { id: true },
    });

    if (!existing) {
      const created = await db.conclusionDeletionRequest.create({
        data: {
          conclusionId,
          requesterId: currentTenant.founderId,
          reason: reason || "Requested from library peer-review delete flow",
        },
      });
      await db.auditEvent.create({
        data: {
          organizationId: currentTenant.organizationId,
          founderId: currentTenant.founderId,
          action: "conclusion_deletion_request",
          detail: JSON.stringify({
            conclusionId,
            requestId: created.id,
            source: "library-request-link",
          }),
        },
      });
    }

    revalidatePath("/library");
    revalidatePath(`/conclusions/${conclusionId}`);
    redirect(
      `/library?request=${encodeURIComponent(
        conclusionId,
      )}&requested=1#conclusion-deletion-request`,
    );
  }

  return (
    <main
      style={{
        maxWidth: "1000px",
        margin: "0 auto",
        padding: "2rem 2rem 4rem",
      }}
    >
      <header style={{ marginBottom: "1rem" }}>
        <h2
          style={{
            fontFamily: "'Cinzel', serif",
            fontSize: "1.2rem",
            letterSpacing: "0.06em",
            color: "var(--amber)",
            margin: 0,
            fontWeight: 500,
          }}
        >
          Library
        </h2>
        <p
          style={{
            color: "var(--parchment-dim)",
            fontSize: "0.85rem",
            margin: "0.35rem 0 0",
            lineHeight: 1.5,
            maxWidth: "44em",
          }}
        >
          Every upload in the firm. Owners can delete their own entries
          directly. For material you didn&rsquo;t upload, send a deletion
          request — the owner decides. Every action leaves an audit trail.
        </p>
      </header>

      {requestConclusionId ? (
        <ConclusionDeletionRequestPanel
          conclusion={deletionTarget}
          requested={sp.requested === "1"}
          error={sp.error || ""}
          canRequest={canWrite(tenant.role)}
          existingRequestId={existingConclusionDeletionRequest?.id || null}
          action={requestConclusionDeletionFromLibrary}
        />
      ) : null}

      <LibraryBrowser />
    </main>
  );
}

export default async function LibraryPage({
  searchParams,
}: {
  searchParams: Promise<LibrarySearchParams>;
}) {
  return LibraryContent({ searchParams });
}

function ConclusionDeletionRequestPanel({
  conclusion,
  requested,
  error,
  canRequest,
  existingRequestId,
  action,
}: {
  conclusion: {
    id: string;
    text: string;
    confidenceTier: string;
    topicHint: string;
  } | null;
  requested: boolean;
  error: string;
  canRequest: boolean;
  existingRequestId: string | null;
  action: (formData: FormData) => Promise<void>;
}) {
  return (
    <section
      id="conclusion-deletion-request"
      className="portal-card"
      style={{
        marginBottom: "1.75rem",
        padding: "1rem 1.2rem",
        border: "1px solid var(--ember)",
        background:
          "linear-gradient(180deg, rgba(166,68,45,0.11), rgba(166,68,45,0.03))",
      }}
    >
      <h2
        className="mono"
        style={{
          margin: "0 0 0.6rem",
          color: "var(--ember)",
          fontSize: "0.65rem",
          letterSpacing: "0.24em",
          textTransform: "uppercase",
        }}
      >
        Peer-review conclusion deletion
      </h2>
      {!conclusion ? (
        <p style={{ margin: 0, color: "var(--parchment-dim)", fontSize: "0.85rem" }}>
          This conclusion is not available in your organization.
        </p>
      ) : (
        <>
          <p
            style={{
              margin: 0,
              color: "var(--parchment)",
              fontFamily: "'EB Garamond', serif",
              fontSize: "1rem",
              lineHeight: 1.5,
            }}
          >
            {conclusion.text}
          </p>
          <p
            className="mono"
            style={{
              margin: "0.4rem 0 0.85rem",
              color: "var(--parchment-dim)",
              fontSize: "0.6rem",
              letterSpacing: "0.14em",
              textTransform: "uppercase",
            }}
          >
            {conclusion.confidenceTier} · {conclusion.topicHint || "general"}
          </p>

          {requested || existingRequestId ? (
            <p style={{ color: "var(--amber)", fontSize: "0.82rem", margin: 0 }}>
              A pending peer-review deletion request already exists.
            </p>
          ) : !canRequest ? (
            <p style={{ color: "var(--ember)", fontSize: "0.82rem", margin: 0 }}>
              Your current role cannot open conclusion deletion requests.
            </p>
          ) : (
            <form action={action}>
              <input type="hidden" name="conclusionId" value={conclusion.id} />
              <label
                className="mono"
                htmlFor="conclusion-deletion-reason"
                style={{
                  display: "block",
                  color: "var(--parchment-dim)",
                  fontSize: "0.58rem",
                  letterSpacing: "0.18em",
                  textTransform: "uppercase",
                  marginBottom: "0.35rem",
                }}
              >
                Reason for peer review
              </label>
              <textarea
                id="conclusion-deletion-reason"
                name="reason"
                rows={3}
                style={{
                  width: "100%",
                  boxSizing: "border-box",
                  resize: "vertical",
                  border: "1px solid var(--stroke)",
                  borderRadius: 2,
                  background: "rgba(10,10,10,0.25)",
                  color: "var(--parchment)",
                  padding: "0.55rem 0.65rem",
                  fontFamily: "'EB Garamond', serif",
                  fontSize: "0.95rem",
                }}
              />
              <button
                type="submit"
                className="btn"
                style={{
                  marginTop: "0.65rem",
                  color: "var(--ember)",
                  borderColor: "var(--ember)",
                  fontSize: "0.65rem",
                }}
              >
                Request deletion
              </button>
            </form>
          )}
        </>
      )}
      {error ? (
        <p style={{ color: "var(--ember)", fontSize: "0.8rem", margin: "0.75rem 0 0" }}>
          Request error: {error}
        </p>
      ) : null}
    </section>
  );
}
