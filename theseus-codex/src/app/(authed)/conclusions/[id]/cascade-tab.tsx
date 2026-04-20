import { fetchCascadeDiag, type CascadeNode } from "@/lib/api/round3";
import { requireTenantContext } from "@/lib/tenant";

/**
 * Cascade tab on the conclusion-detail page.
 *
 * Renders the downstream-inference tree with connector lines, a
 * per-kind accent colour, and a small confidence bar so nodes are
 * scannable even at depth 3+. Deep subtrees wrap in a collapsible
 * `<details>` so the surface stays readable by default.
 */
export default async function CascadeTab({ conclusionId }: { conclusionId: string }) {
  const tenant = await requireTenantContext();
  if (!tenant) return null;
  const { roots, error } = await fetchCascadeDiag(tenant.organizationId, conclusionId);

  if (roots.length === 0) {
    return (
      <div style={{ padding: "0.75rem 0", color: "var(--parchment-dim)", fontSize: "0.85rem" }}>
        No cascade nodes for this conclusion.
        {error && (
          <details style={{ marginTop: "0.5rem" }}>
            <summary style={{ cursor: "pointer", fontSize: "0.7rem", color: "var(--ember)" }}>
              Query diagnostic
            </summary>
            <pre
              style={{
                fontSize: "0.65rem",
                color: "var(--parchment-dim)",
                marginTop: "0.25rem",
                whiteSpace: "pre-wrap",
              }}
            >
              {error}
            </pre>
          </details>
        )}
      </div>
    );
  }

  return <div>{renderNodes(roots, 0)}</div>;
}

function kindColor(kind: string): string {
  switch (kind) {
    case "principle":
      return "var(--gold)";
    case "claim":
      return "var(--amber)";
    case "evidence":
      return "var(--parchment)";
    case "conclusion":
      return "var(--gold-dim)";
    default:
      return "var(--parchment-dim)";
  }
}

function renderNodes(nodes: CascadeNode[], depth: number): React.ReactNode {
  return (
    <div
      style={{
        paddingLeft: depth > 0 ? "0.75rem" : 0,
        borderLeft: depth > 0 ? "1px solid var(--border)" : "none",
        marginLeft: depth > 0 ? "0.25rem" : 0,
      }}
    >
      {nodes.map((node) => (
        <CascadeRow key={node.id} node={node} depth={depth} />
      ))}
    </div>
  );
}

function CascadeRow({ node, depth }: { node: CascadeNode; depth: number }) {
  const accent = kindColor(node.kind);
  const confPct = Math.max(0, Math.min(1, node.confidence)) * 100;
  return (
    <div style={{ position: "relative" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.5rem",
          padding: "0.4rem 0.75rem",
          marginBottom: "0.25rem",
          borderLeft: `2px solid ${accent}`,
        }}
      >
        {depth > 0 && (
          <span
            aria-hidden
            style={{
              display: "inline-block",
              width: "0.75rem",
              borderBottom: "1px solid var(--border)",
              alignSelf: "center",
            }}
          />
        )}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              gap: "0.5rem",
              alignItems: "center",
            }}
          >
            <span
              style={{
                fontSize: "0.65rem",
                color: accent,
                textTransform: "uppercase",
                letterSpacing: "0.1em",
              }}
            >
              {node.kind}
            </span>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.4rem",
              }}
              title={`${confPct.toFixed(0)}% confidence`}
            >
              <div
                style={{
                  width: "3rem",
                  height: "3px",
                  background: "var(--border)",
                  borderRadius: 2,
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: `${confPct.toFixed(0)}%`,
                    height: "100%",
                    background: "var(--gold)",
                  }}
                />
              </div>
              <span style={{ fontSize: "0.6rem", color: "var(--parchment-dim)" }}>
                {confPct.toFixed(0)}%
              </span>
            </div>
          </div>
          <div style={{ color: "var(--parchment)", fontSize: "0.8rem", marginTop: "0.15rem" }}>
            {node.label}
          </div>
        </div>
      </div>
      {node.children.length > 0 && (
        <details open style={{ marginTop: "0.15rem" }}>
          <summary
            style={{
              cursor: "pointer",
              fontSize: "0.6rem",
              color: "var(--parchment-dim)",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              marginLeft: "1rem",
            }}
          >
            {node.children.length} child node{node.children.length > 1 ? "s" : ""}
          </summary>
          {renderNodes(node.children, depth + 1)}
        </details>
      )}
    </div>
  );
}
