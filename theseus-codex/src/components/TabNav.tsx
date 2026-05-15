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
export type TabSemantics = "state" | "route";

/**
 * R-015: tabs render differently depending on whether they're in-page
 * state (the URL only changes its `?tab=` parameter; same page) or
 * route-bearing (each tab navigates to a different page in the firm).
 *
 *  - "state" tabs: 1 px amber underline on the active state.
 *  - "route" tabs: plain Cinzel small-caps — they're nav, not state.
 *
 * `TabNav` is for state tabs by default; pass `semantics="route"` for
 * route-bearing strips (e.g. a sub-navigation that takes the user to a
 * different /knowledge sub-section that lives at a different path).
 */
export default function TabNav({
  basePath,
  current,
  tabs,
  semantics = "state",
}: {
  basePath: string;
  current: string;
  tabs: ReadonlyArray<{ id: string; label: string; href?: string }>;
  semantics?: TabSemantics;
}) {
  const isRoute = semantics === "route";
  return (
    <nav
      aria-label="Sub-navigation"
      data-tab-semantics={semantics}
      style={{
        maxWidth: "1200px",
        margin: "0 auto 1rem",
        padding: "0 1.5rem",
        display: "flex",
        gap: "1.5rem",
        borderBottom: isRoute ? undefined : "1px solid var(--border)",
        flexWrap: "wrap",
      }}
    >
      {tabs.map((tab) => {
        const active = tab.id === current;
        const href =
          tab.href ?? (tab.id ? `${basePath}?tab=${tab.id}` : basePath);
        return (
          <a
            key={tab.id}
            href={href}
            data-active={active ? "true" : undefined}
            style={{
              fontFamily: "'Cinzel', serif",
              fontSize: "0.7rem",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              color: active ? "var(--gold)" : "var(--parchment-dim)",
              textDecoration: "none",
              padding: "0.6rem 0",
              // R-015: state tabs use an amber underline on active;
              // route tabs are plain nav (no underline) so the two
              // patterns look different to the reader.
              borderBottom: isRoute
                ? "none"
                : active
                  ? "1px solid var(--amber)"
                  : "1px solid transparent",
              marginBottom: "-1px",
              transition: "color 0.2s, border-color 0.2s",
            }}
          >
            {tab.label}
          </a>
        );
      })}
    </nav>
  );
}
