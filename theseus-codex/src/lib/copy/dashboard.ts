/**
 * Founder-facing copy for the dashboard and adjacent review surfaces.
 *
 * The founder said the original terminology — "Attention", "Open
 * Question", "Snooze", "Dismiss" — did not communicate. These four
 * strings replace what the founder reads, while the underlying API
 * verbs (`snooze`, `dismiss`) and the schema labels (`open_question`)
 * stay put. See `docs/operator/dashboard_terminology.md` for the
 * rationale and the regression-test guarantee.
 *
 * Every founder-facing surface that previously said one of those words
 * imports from this module. A vitest lint (`dashboard-copy.test.ts`)
 * scans component files and fails if the literals leak back in.
 */
export const DASHBOARD_COPY = {
  /** Replaces "Snooze". A timed hide; the item returns automatically. */
  hideForNow: "Hide for now (returns in 7 days)",
  /** Replaces "Dismiss". The founder is done with this item. */
  hidePermanently: "Hide permanently",
  /**
   * Replaces "Open Question" / "Open questions". The label for the
   * queue of research threads that have not been resolved yet.
   */
  unresolvedResearchThread: "Unresolved research thread",
} as const;

export type DashboardCopyKey = keyof typeof DASHBOARD_COPY;

/**
 * Strings the lint expects to live only inside this module. Components
 * that need to display these phrases must import `DASHBOARD_COPY` and
 * reference the field, not inline the literal.
 */
export const DASHBOARD_COPY_LITERALS: readonly string[] = [
  DASHBOARD_COPY.hideForNow,
  DASHBOARD_COPY.hidePermanently,
  DASHBOARD_COPY.unresolvedResearchThread,
];
