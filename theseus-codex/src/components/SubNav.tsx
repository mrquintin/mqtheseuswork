"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

/**
 * Context-sensitive sub-navigation.
 *
 * Wave E removes Review and Library as secondary groups. The only
 * remaining secondary row is Ops, and it appears exclusively on `/ops`
 * where advanced tooling panels are selected by `?panel=...`.
 */

type SubNavGroup = {
  /** Human label for the group (shown in the top nav). */
  topLabel: string;
  /** Default landing URL when the user clicks the top-nav label. */
  defaultHref: string;
  /** Siblings that appear in the sub-nav when any of them is active. */
  tabs: ReadonlyArray<{ href: string; label: string; panel: string }>;
};

export const SUB_NAV_GROUPS: ReadonlyArray<SubNavGroup> = [
  {
    topLabel: "Ops",
    defaultHref: "/ops",
    tabs: [
      { href: "/ops?panel=provenance", label: "Provenance", panel: "provenance" },
      { href: "/ops?panel=eval", label: "Eval runs", panel: "eval" },
      { href: "/ops?panel=contradictions", label: "Contradictions", panel: "contradictions" },
      { href: "/ops?panel=peer-review", label: "Peer review", panel: "peer-review" },
      { href: "/ops?panel=open-questions", label: "Open questions", panel: "open-questions" },
      { href: "/ops?panel=adversarial", label: "Adversarial", panel: "adversarial" },
      { href: "/ops?panel=layer-review", label: "Layer review", panel: "layer-review" },
      { href: "/ops?panel=calibration", label: "Calibration", panel: "calibration" },
      { href: "/ops?panel=post-mortem", label: "Post-mortem", panel: "post-mortem" },
      { href: "/ops?panel=decay", label: "Decay", panel: "decay" },
      { href: "/ops?panel=rigor-gate", label: "Rigor gate", panel: "rigor-gate" },
      { href: "/ops?panel=methods", label: "Methods", panel: "methods" },
      { href: "/ops?panel=founders", label: "Founders", panel: "founders" },
    ],
  },
];

/** All hrefs that belong to any group — used by the top nav to mark the
 * correct group as active for detail-page URLs like `/voices/abc123`. */
export function findGroupForPath(pathname: string): SubNavGroup | null {
  for (const group of SUB_NAV_GROUPS) {
    if (pathname === group.defaultHref || pathname.startsWith(group.defaultHref + "/")) {
      return group;
    }
  }
  return null;
}

export default function SubNav() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const group = findGroupForPath(pathname);
  if (!group) return null;
  const activePanel = searchParams.get("panel") || "overview";

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
          const active = activePanel === tab.panel;
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
