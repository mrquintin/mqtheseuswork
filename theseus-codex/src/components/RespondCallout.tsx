import RespondForm from "@/components/RespondForm";
import type { PublishedConclusion } from "@/lib/conclusionsRead";

export default function RespondCallout({
  conclusions,
}: {
  conclusions: PublishedConclusion[];
}) {
  return (
    <details
      style={{
        borderBottom: "1px solid var(--stroke)",
        margin: "0 0 1.6rem",
        padding: "0 0 1.1rem",
      }}
    >
      <summary
        className="mono"
        style={{
          border: "1px solid var(--amber-dim)",
          color: "var(--amber)",
          cursor: "pointer",
          display: "inline-flex",
          fontSize: "0.62rem",
          letterSpacing: "0.2em",
          padding: "0.55rem 0.72rem",
          textTransform: "uppercase",
        }}
      >
        Submit a structured response
      </summary>
      <div style={{ marginTop: "0.9rem" }}>
        <RespondForm conclusions={conclusions} />
      </div>
    </details>
  );
}
