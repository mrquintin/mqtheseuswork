"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * Context-sensitive sub-navigation.
 *
 * The Codex has ~20 feature pages that naturally cluster into 4 thematic
 * groups: Coherence review, External library, Operations, and the
 * Conclusion lineage trio. The TOP nav shows those 4 groups as single
 * entries. This SUB nav, rendered one row below, shows the siblings of
 * whatever page you're currently on — so once you click "Review" in the
 * top nav and land on /contradictions, you can see and jump between
 * /open-questions, /adversarial, /q/review, and /scoreboard without
 * returning to the top nav.
 *
 * The component reads `usePathname()` and matches against `GROUPS`. If the
 * current path doesn't belong to any group (e.g. /dashboard, /upload,
 * /publication), the sub-nav renders nothing — those pages don't have
 * peers.
 */

type SubNavGroup = {
  /** Human label for the group (shown in the top nav). */
  topLabel: string;
  /** Default landing URL when the user clicks the top-nav label. */
  defaultHref: string;
  /** Siblings that appear in the sub-nav when any of them is active. */
  tabs: ReadonlyArray<{ href: string; label: string }>;
};

export const SUB_NAV_GROUPS: ReadonlyArray<SubNavGroup> = [
  {
    topLabel: "Review",
    defaultHref: "/contradictions",
    tabs: [
      { href: "/contradictions", label: "Contradictions" },
      { href: "/open-questions", label: "Open questions" },
      { href: "/adversarial", label: "Adversarial" },
      { href: "/q/review", label: "Layer review" },
      { href: "/scoreboard", label: "Calibration" },
    ],
  },
  {
    topLabel: "Library",
    defaultHref: "/voices",
    tabs: [
      { href: "/voices", label: "Voices" },
      { href: "/literature", label: "Literature" },
      { href: "/reading-queue", label: "Reading queue" },
      { href: "/research", label: "Research" },
    ],
  },
  {
    topLabel: "Ops",
    defaultHref: "/provenance",
    tabs: [
      { href: "/provenance", label: "Provenance" },
      { href: "/eval", label: "Eval runs" },
      { href: "/post-mortem", label: "Post-mortem" },
      { href: "/decay", label: "Decay" },
      { href: "/rigor-gate", label: "Rigor gate" },
      { href: "/methods", label: "Methods" },
      { href: "/founders", label: "Founders" },
    ],
  },
];

/** All hrefs that belong to any group — used by the top nav to mark the
 * correct group as active for detail-page URLs like `/voices/abc123`. */
export function findGroupForPath(pathname: string): SubNavGroup | null {
  for (const group of SUB_NAV_GROUPS) {
    for (const tab of group.tabs) {
      if (pathname === tab.href || pathname.startsWith(tab.href + "/")) {
        return group;
      }
    }
  }
  return null;
}

export default function SubNav() {
  const pathname = usePathname();
  const group = findGroupForPath(pathname);
  if (!group) return null;

  return (
    <nav
      aria-label={`${group.topLabel} sub-navigation`}
      style={{
        borderBottom: "1px solid var(--border)",
        background: "var(--stone)",
      }}
    >
      <div
        style={{
          maxWidth: "1200px",
          margin: "0 auto",
          padding: "0 1.5rem",
          display: "flex",
          gap: "1.5rem",
          overflowX: "auto",
        }}
      >
        {group.tabs.map((tab) => {
          const active =
            pathname === tab.href || pathname.startsWith(tab.href + "/");
          return (
            <Link
              key={tab.href}
              href={tab.href}
              style={{
                fontFamily: "'Cinzel', serif",
                fontSize: "0.65rem",
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                color: active ? "var(--gold)" : "var(--parchment-dim)",
                textDecoration: "none",
                padding: "0.5rem 0",
                borderBottom: active
                  ? "2px solid var(--gold)"
                  : "2px solid transparent",
                marginBottom: "-1px",
                whiteSpace: "nowrap",
              }}
            >
              {tab.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
