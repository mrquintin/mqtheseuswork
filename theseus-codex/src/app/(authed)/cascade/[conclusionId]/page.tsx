import { redirect } from "next/navigation";
import CascadeTree3D from "@/components/CascadeTree3DClient";
import {
  fetchCascade,
  toCSV,
  downloadHref,
  type CascadeNode,
} from "@/lib/api/round3";
import { requireTenantContext } from "@/lib/tenant";

export default async function CascadeExplorerPage({
  params,
}: {
  params: Promise<{ conclusionId: string }>;
}) {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login");

  const { conclusionId } = await params;
  // Scoped so a cross-tenant conclusion id resolves to "no cascade
  // nodes found" rather than leaking another firm's inference tree.
  const roots = await fetchCascade(tenant.organizationId, conclusionId);

  function flattenNodes(nodes: CascadeNode[], depth = 0): Array<CascadeNode & { depth: number }> {
    const result: Array<CascadeNode & { depth: number }> = [];
    for (const node of nodes) {
      result.push({ ...node, depth });
      result.push(...flattenNodes(node.children, depth + 1));
    }
    return result;
  }

  const flat = flattenNodes(roots);
  const csvData = toCSV(
    flat.map((n) => ({
      id: n.id,
      kind: n.kind,
      label: n.label,
      confidence: n.confidence,
      parentId: n.parentId ?? "",
      depth: n.depth,
    })),
  );

  return (
    <main style={{ maxWidth: "960px", margin: "0 auto", padding: "3rem 2rem" }}>
      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          color: "var(--gold)",
          letterSpacing: "0.08em",
        }}
      >
        Cascade explorer
      </h1>
      <p style={{ color: "var(--parchment-dim)", marginBottom: "0.5rem", fontSize: "0.9rem" }}>
        Inference cascade for conclusion{" "}
        <code style={{ color: "var(--gold-dim)" }}>{conclusionId.slice(0, 12)}…</code>
      </p>

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
        <a
          href={downloadHref(csvData, "text/csv")}
          download={`cascade-${conclusionId.slice(0, 8)}.csv`}
          className="btn"
          style={{ fontSize: "0.65rem", textDecoration: "none" }}
        >
          Download CSV
        </a>
        <a
          href={downloadHref(JSON.stringify(roots, null, 2), "application/json")}
          download={`cascade-${conclusionId.slice(0, 8)}.json`}
          className="btn"
          style={{ fontSize: "0.65rem", textDecoration: "none" }}
        >
          Download JSON
        </a>
      </div>

      {flat.length === 0 ? (
        <div className="portal-card" style={{ padding: "1rem 1.25rem", color: "var(--parchment-dim)" }}>
          <em>Cascade vacua.</em> No cascade nodes found for this conclusion.
        </div>
      ) : (
        <>
          <CascadeTree3D
            nodes={flat.map((n) => ({
              id: n.id,
              label: n.label.length > 40 ? n.label.slice(0, 38) + "…" : n.label,
              depth: n.depth,
              parentId: n.parentId ?? null,
              weight: n.confidence,
            }))}
          />
          <details style={{ marginTop: "1.25rem" }}>
            <summary
              className="mono"
              style={{
                cursor: "pointer",
                fontSize: "0.7rem",
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                color: "var(--amber-dim)",
                padding: "0.5rem 0",
              }}
            >
              ╚══ listed form ═══
            </summary>
            <ul
              style={{
                listStyle: "none",
                padding: 0,
                marginTop: "0.5rem",
                display: "flex",
                flexDirection: "column",
                gap: "0.25rem",
              }}
            >
              {flat.map((node) => (
                <li
                  key={node.id}
                  className="portal-card"
                  style={{
                    padding: "0.6rem 1rem",
                    marginLeft: `${node.depth * 1.5}rem`,
                    borderLeft:
                      node.depth > 0 ? "2px solid var(--gold-dim)" : "none",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
                    <span style={{ fontSize: "0.7rem", color: "var(--gold-dim)", textTransform: "uppercase" }}>
                      {node.kind}
                    </span>
                    <span style={{ fontSize: "0.65rem", color: "var(--parchment-dim)" }}>
                      confidence {(node.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <p style={{ marginTop: "0.25rem", color: "var(--parchment)", fontSize: "0.85rem" }}>
                    {node.label}
                  </p>
                </li>
              ))}
            </ul>
          </details>
        </>
      )}
    </main>
  );
}
