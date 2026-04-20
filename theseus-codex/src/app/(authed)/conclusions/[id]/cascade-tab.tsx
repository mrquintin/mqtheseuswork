import { fetchCascade, type CascadeNode } from "@/lib/api/round3";
import { requireTenantContext } from "@/lib/tenant";

/**
 * Cascade tab on the conclusion-detail page.
 *
 * The raw-SQL `cascade_node` fetch is tenant-scoped at the query
 * layer; we resolve the founder's org here and forward the id so
 * cross-tenant conclusion ids can't leak a downstream tree.
 */
export default async function CascadeTab({ conclusionId }: { conclusionId: string }) {
  const tenant = await requireTenantContext();
  if (!tenant) return null;
  const roots = await fetchCascade(tenant.organizationId, conclusionId);

  if (roots.length === 0) {
    return (
      <div style={{ padding: "0.75rem 0", color: "var(--parchment-dim)", fontSize: "0.85rem" }}>
        No cascade nodes for this conclusion.
      </div>
    );
  }

  function renderNodes(nodes: CascadeNode[], depth: number): React.ReactNode {
    return nodes.map((node) => (
      <div key={node.id} style={{ paddingLeft: `${depth * 1.25}rem` }}>
        <div
          style={{
            padding: "0.4rem 0.75rem",
            marginBottom: "0.25rem",
            borderLeft: depth > 0 ? "2px solid var(--gold-dim)" : "none",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
            <span style={{ fontSize: "0.65rem", color: "var(--gold-dim)", textTransform: "uppercase" }}>
              {node.kind}
            </span>
            <span style={{ fontSize: "0.6rem", color: "var(--parchment-dim)" }}>
              {(node.confidence * 100).toFixed(0)}%
            </span>
          </div>
          <div style={{ color: "var(--parchment)", fontSize: "0.8rem", marginTop: "0.15rem" }}>
            {node.label}
          </div>
        </div>
        {node.children.length > 0 && renderNodes(node.children, depth + 1)}
      </div>
    ));
  }

  return <div>{renderNodes(roots, 0)}</div>;
}
