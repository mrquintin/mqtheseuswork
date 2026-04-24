import { requireTenantContext } from "@/lib/tenant";
import ExplorerScatterPlot from "./scatter-plot";

export default async function ExplorerPage() {
  const tenant = await requireTenantContext();
  if (!tenant) return null;

  return (
    <main style={{ maxWidth: "1200px", margin: "0 auto", padding: "2rem" }}>
      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          color: "var(--gold)",
          letterSpacing: "0.08em",
        }}
      >
        Semantic Explorer
      </h1>
      <p
        style={{
          fontFamily: "'EB Garamond', serif",
          fontStyle: "italic",
          fontSize: "1rem",
          color: "var(--parchment-dim)",
          maxWidth: "44em",
          lineHeight: 1.55,
          marginBottom: "1.5rem",
        }}
      >
        Your conclusions plotted in semantic space. Each point is a
        conclusion; proximity means semantic similarity. The axes represent
        the principal dimensions of variation across your entire belief
        model.
      </p>
      <ExplorerScatterPlot />
    </main>
  );
}
