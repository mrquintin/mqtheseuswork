import Link from "next/link";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";

import CalibrationTriagePanel, {
  type CalibrationTriageRow,
} from "@/components/algorithms/CalibrationTriagePanel";
import {
  retireAlgorithm,
  setAlgorithmStatus,
} from "@/lib/algorithmsApi";
import {
  listPublicAlgorithms,
  type PublicAlgorithmRow,
} from "@/lib/algorithmsPublicApi";
import {
  acceptTriageRecommendation,
  deferTriageRecommendation,
  listPendingTriageRecommendations,
  rejectTriageRecommendation,
} from "@/lib/algorithmsCalibrationApi";
import { requireTenantContext } from "@/lib/tenant";

export const dynamic = "force-dynamic";

/**
 * Operator-only console for the LogicalAlgorithm runtime.
 *
 * The public surface (`/algorithms`) shows the firm thinking aloud;
 * this page is the operator's hand on the wheel:
 *
 *   - Force-fire an algorithm with overridden inputs (calls
 *     `noosphere algorithms fire` via the noosphere CLI / API; the
 *     UI here records the operator intent and the founder runs the
 *     actual command — keeping the LLM-spend gate in the operator's
 *     terminal where it belongs).
 *   - Pause / unpause an active algorithm.
 *   - Edit an active algorithm (link to the existing triage editor
 *     in `/algorithms/queue` so we don't duplicate that surface).
 *   - Retire an algorithm with a reason.
 */
export default async function AlgorithmsOperatorPage() {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login");

  const algorithms = await listPublicAlgorithms(tenant.organizationId, {
    status: "ALL",
  });
  const triageRows = await listPendingTriageRecommendations(
    tenant.organizationId,
  );

  async function acceptTriageAction(formData: FormData) {
    "use server";
    const id = String(formData.get("id") ?? "").trim();
    if (!id) return;
    const t = await requireTenantContext();
    if (!t) redirect("/login");
    await acceptTriageRecommendation(t.organizationId, id, {
      actor: t.founderId ?? "operator",
    });
    revalidatePath("/(authed)/algorithms/operator");
    revalidatePath("/algorithms");
  }

  async function rejectTriageAction(formData: FormData) {
    "use server";
    const id = String(formData.get("id") ?? "").trim();
    const note = String(formData.get("note") ?? "").trim();
    if (!id) return;
    const t = await requireTenantContext();
    if (!t) redirect("/login");
    if (note.length < 20) {
      throw new Error(
        "REJECT requires a resolution_note of at least 20 characters",
      );
    }
    await rejectTriageRecommendation(t.organizationId, id, {
      actor: t.founderId ?? "operator",
      note,
    });
    revalidatePath("/(authed)/algorithms/operator");
  }

  async function deferTriageAction(formData: FormData) {
    "use server";
    const id = String(formData.get("id") ?? "").trim();
    if (!id) return;
    const t = await requireTenantContext();
    if (!t) redirect("/login");
    await deferTriageRecommendation(t.organizationId, id, {
      actor: t.founderId ?? "operator",
    });
    revalidatePath("/(authed)/algorithms/operator");
  }

  async function pauseAction(formData: FormData) {
    "use server";
    const id = String(formData.get("id") ?? "").trim();
    if (!id) return;
    const t = await requireTenantContext();
    if (!t) redirect("/login");
    await setAlgorithmStatus(t.organizationId, id, "PAUSED");
    revalidatePath("/(authed)/algorithms/operator");
    revalidatePath("/algorithms");
  }

  async function unpauseAction(formData: FormData) {
    "use server";
    const id = String(formData.get("id") ?? "").trim();
    if (!id) return;
    const t = await requireTenantContext();
    if (!t) redirect("/login");
    await setAlgorithmStatus(t.organizationId, id, "ACTIVE");
    revalidatePath("/(authed)/algorithms/operator");
    revalidatePath("/algorithms");
  }

  async function retireAction(formData: FormData) {
    "use server";
    const id = String(formData.get("id") ?? "").trim();
    const reason = String(formData.get("reason") ?? "").trim();
    if (!id || !reason) return;
    const t = await requireTenantContext();
    if (!t) redirect("/login");
    await retireAlgorithm(t.organizationId, id, reason);
    revalidatePath("/(authed)/algorithms/operator");
    revalidatePath("/algorithms");
  }

  const active = algorithms.filter((a) => a.status === "ACTIVE");
  const paused = algorithms.filter((a) => a.status === "PAUSED");
  const retired = algorithms.filter((a) => a.status === "RETIRED");

  return (
    <main
      id="algorithms-operator-main"
      className="public-container public-methodology-page"
      data-testid="algorithms-operator"
    >
      <header style={{ marginBottom: "1.5rem" }}>
        <h1 className="public-title" style={{ margin: 0 }}>
          Algorithms · operator
        </h1>
        <p className="public-lede" style={{ marginTop: "0.5rem" }}>
          Operator-only console. Pause, retire, or trigger sub-loops on the
          algorithms the firm is running. Public surface: {" "}
          <Link href="/algorithms" style={{ color: "var(--amber, #d4a017)" }}>
            /algorithms
          </Link>
          .
        </p>
      </header>

      <CalibrationTriagePanel
        rows={triageRows}
        acceptAction={acceptTriageAction}
        rejectAction={rejectTriageAction}
        deferAction={deferTriageAction}
      />

      <OperatorSection
        title="Active"
        rows={active}
        pauseAction={pauseAction}
        unpauseAction={unpauseAction}
        retireAction={retireAction}
        canPause
      />
      <OperatorSection
        title="Paused"
        rows={paused}
        pauseAction={pauseAction}
        unpauseAction={unpauseAction}
        retireAction={retireAction}
        canUnpause
      />
      <OperatorSection
        title="Retired"
        rows={retired}
        pauseAction={pauseAction}
        unpauseAction={unpauseAction}
        retireAction={retireAction}
      />
    </main>
  );
}

type OperatorSectionProps = {
  title: string;
  rows: PublicAlgorithmRow[];
  pauseAction: (fd: FormData) => Promise<void>;
  unpauseAction: (fd: FormData) => Promise<void>;
  retireAction: (fd: FormData) => Promise<void>;
  canPause?: boolean;
  canUnpause?: boolean;
};

function OperatorSection({
  title,
  rows,
  pauseAction,
  unpauseAction,
  retireAction,
  canPause = false,
  canUnpause = false,
}: OperatorSectionProps) {
  return (
    <section
      className="public-section"
      data-testid={`operator-section-${title.toLowerCase()}`}
    >
      <h2>
        {title} · {rows.length}
      </h2>
      {rows.length === 0 ? (
        <p style={{ color: "var(--public-muted, #888)" }}>
          (no algorithms in this state)
        </p>
      ) : (
        <ul
          style={{
            listStyle: "none",
            padding: 0,
            margin: 0,
            display: "flex",
            flexDirection: "column",
            gap: "0.85rem",
          }}
        >
          {rows.map((row) => (
            <li
              key={row.id}
              data-testid="operator-row"
              data-algorithm-id={row.id}
              style={{
                padding: "0.85rem 1rem",
                border: "1px solid var(--border, #333)",
                borderRadius: 3,
                background: "var(--stone-light, #1d1d1d)",
                display: "flex",
                flexDirection: "column",
                gap: "0.65rem",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: "0.85rem",
                  alignItems: "baseline",
                  flexWrap: "wrap",
                }}
              >
                <div>
                  <Link
                    href={`/algorithms/${row.id}`}
                    style={{ color: "var(--text, #eee)", textDecoration: "none" }}
                  >
                    <strong>{row.name}</strong>
                  </Link>
                  <span
                    style={{
                      marginLeft: "0.6rem",
                      fontSize: "0.7rem",
                      color: "var(--public-muted, #888)",
                    }}
                  >
                    {row.invocationCount} invocations · last fired{" "}
                    {row.latestInvocationAt
                      ? row.latestInvocationAt.toISOString().slice(0, 10)
                      : "never"}
                  </span>
                </div>
                <div
                  style={{
                    display: "flex",
                    gap: "0.4rem",
                    alignItems: "center",
                    flexWrap: "wrap",
                  }}
                >
                  {canPause ? (
                    <form action={pauseAction}>
                      <input type="hidden" name="id" value={row.id} />
                      <button type="submit" className="btn">
                        Pause
                      </button>
                    </form>
                  ) : null}
                  {canUnpause ? (
                    <form action={unpauseAction}>
                      <input type="hidden" name="id" value={row.id} />
                      <button type="submit" className="btn">
                        Unpause
                      </button>
                    </form>
                  ) : null}
                  <Link
                    href={`/algorithms/queue`}
                    className="btn"
                    title="Edit via the triage queue"
                  >
                    Edit
                  </Link>
                </div>
              </div>

              {row.status !== "RETIRED" ? (
                <details>
                  <summary
                    style={{
                      cursor: "pointer",
                      fontSize: "0.7rem",
                      letterSpacing: "0.18em",
                      textTransform: "uppercase",
                      color: "var(--public-muted, #888)",
                    }}
                  >
                    Force-fire with overridden inputs
                  </summary>
                  <pre
                    data-testid="force-fire-cli"
                    style={{
                      margin: "0.5rem 0 0",
                      padding: "0.55rem 0.75rem",
                      background: "var(--stone-light, #111)",
                      border: "1px solid var(--border, #333)",
                      borderRadius: 3,
                      fontFamily: "'JetBrains Mono', monospace",
                      fontSize: "0.72rem",
                      color: "var(--text, #ddd)",
                      whiteSpace: "pre-wrap",
                    }}
                  >
                    {`noosphere algorithms fire \\\n  --algorithm-id ${row.id} \\\n  --inputs-json '{${row.inputs
                      .map((i) => `"${i.name}": <value>`)
                      .join(", ")}}'`}
                  </pre>
                  <p
                    style={{
                      marginTop: "0.4rem",
                      fontSize: "0.7rem",
                      color: "var(--public-muted, #aaa)",
                    }}
                  >
                    Force-fire keeps the LLM-spend gate in the terminal — copy
                    this command and run it in the operator shell.
                  </p>
                </details>
              ) : null}

              {row.status !== "RETIRED" ? (
                <details>
                  <summary
                    style={{
                      cursor: "pointer",
                      fontSize: "0.7rem",
                      letterSpacing: "0.18em",
                      textTransform: "uppercase",
                      color: "var(--ember, #c0584a)",
                    }}
                  >
                    Retire
                  </summary>
                  <form
                    action={retireAction}
                    style={{
                      marginTop: "0.5rem",
                      display: "flex",
                      flexDirection: "column",
                      gap: "0.4rem",
                    }}
                  >
                    <input type="hidden" name="id" value={row.id} />
                    <textarea
                      name="reason"
                      required
                      rows={2}
                      placeholder="Why are we retiring this algorithm?"
                      style={{
                        background: "var(--stone-light, #111)",
                        color: "var(--text, #eee)",
                        border: "1px solid var(--border, #333)",
                        borderRadius: 3,
                        padding: "0.5rem",
                        fontFamily: "'EB Garamond', serif",
                      }}
                    />
                    <button type="submit" className="btn btn-solid">
                      Retire algorithm
                    </button>
                  </form>
                </details>
              ) : (
                row.retiredReason ? (
                  <p
                    style={{
                      margin: 0,
                      fontSize: "0.78rem",
                      color: "var(--public-muted, #aaa)",
                    }}
                  >
                    Retired — {row.retiredReason}
                  </p>
                ) : null
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
