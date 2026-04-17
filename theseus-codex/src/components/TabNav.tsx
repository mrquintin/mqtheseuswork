import Link from "next/link";

/**
 * Sub-navigation bar for tabbed container pages (`/review`, `/library`,
 * `/ops`, `/conclusions/[id]`). The ACTIVE tab is styled gold; others dim.
 *
 * We avoid a client component for this because the tab state lives in
 * the URL (e.g. `?tab=contradictions`), which means:
 *   - server components can read `searchParams` and render the right tab's
 *     data server-side (no client fetch, faster first paint)
 *   - every tab has a bookmarkable URL
 *   - browser back/forward works
 *
 * Usage:
 *   <TabNav
 *     basePath="/review"
 *     current={tab}
 *     tabs={[
 *       { id: "contradictions", label: "Contradictions" },
 *       { id: "open-questions", label: "Open questions" },
 *     ]}
 *   />
 */
export default function TabNav({
  basePath,
  current,
  tabs,
}: {
  basePath: string;
  current: string;
  tabs: ReadonlyArray<{ id: string; label: string }>;
}) {
  return (
    <nav
      aria-label="Sub-navigation"
      style={{
        maxWidth: "1200px",
        margin: "0 auto 1rem",
        padding: "0 1.5rem",
        display: "flex",
        gap: "1.5rem",
        borderBottom: "1px solid var(--border)",
        flexWrap: "wrap",
      }}
    >
      {tabs.map((tab) => {
        const active = tab.id === current;
        const href = tab.id ? `${basePath}?tab=${tab.id}` : basePath;
        return (
          <Link
            key={tab.id}
            href={href}
            style={{
              fontFamily: "'Cinzel', serif",
              fontSize: "0.7rem",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              color: active ? "var(--gold)" : "var(--parchment-dim)",
              textDecoration: "none",
              padding: "0.6rem 0",
              borderBottom: active
                ? "2px solid var(--gold)"
                : "2px solid transparent",
              marginBottom: "-1px",
              transition: "color 0.2s, border-color 0.2s",
            }}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
