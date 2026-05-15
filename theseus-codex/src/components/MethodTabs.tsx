import Link from "next/link";

export type MethodTabKey =
  | "overview"
  | "track-record"
  | "domain"
  | "composition"
  | "failures"
  | "changelog"
  | "conclusions";

type TabSpec = {
  key: MethodTabKey;
  label: string;
  /** When set, the tab href is `/methodology/[method]<suffix>`. */
  suffix?: string;
  /** Override href entirely (used for Composition, which is a single global view). */
  href?: (method: string) => string;
};

const TABS: TabSpec[] = [
  { key: "overview", label: "Overview", suffix: "" },
  { key: "track-record", label: "Track record", suffix: "/track-record" },
  { key: "domain", label: "Domain", suffix: "/domain" },
  {
    key: "composition",
    label: "Composition",
    href: (m) => `/methodology/composition#${encodeURIComponent(m)}`,
  },
  { key: "failures", label: "Failure modes", suffix: "/failures" },
  { key: "changelog", label: "Changelog", suffix: "/changelog" },
  {
    key: "conclusions",
    label: "Conclusions produced",
    href: (m) => `/c?method=${encodeURIComponent(m)}`,
  },
];

/**
 * URL-driven section nav for `/methodology/[method]/...`. Per-method
 * sections (Overview / Track record / Domain / Failure modes) live at
 * distinct sub-routes so they are independently shareable and indexable.
 * Composition links into the global composition map, anchored on the
 * method; Conclusions links into the conclusions index filtered by
 * method. Both stay shareable.
 *
 * Explorer v2: this strip is now *secondary*. The method page front-
 * loads the description, the essentials pills, and the cross-links;
 * this nav sits below them under a "Detailed sections" heading. Because
 * every entry navigates to a different document, it is a plain
 * navigation landmark with `aria-current="page"` on the active entry —
 * not an ARIA `tablist`, whose `tab`/`tabpanel` contract assumes the
 * panels live in the same document. Correct semantics here also keep
 * the focus order through the new hierarchy honest.
 */
export default function MethodTabs({
  method,
  active,
}: {
  method: string;
  active: MethodTabKey;
}) {
  const enc = encodeURIComponent(method);
  return (
    <nav
      aria-label={`Detailed sections for method ${method}`}
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: 0,
        margin: "1rem 0 1.5rem",
        borderBottom: "1px solid var(--public-rule, #ddd)",
      }}
    >
      {TABS.map((t) => {
        const isActive = t.key === active;
        const href = t.href
          ? t.href(method)
          : `/methodology/${enc}${t.suffix ?? ""}`;
        return (
          <Link
            key={t.key}
            href={href}
            aria-current={isActive ? "page" : undefined}
            style={{
              padding: "0.55rem 0.95rem",
              textDecoration: "none",
              fontFamily:
                "ui-monospace, SFMono-Regular, Menlo, monospace",
              fontSize: "0.7rem",
              letterSpacing: "0.16em",
              textTransform: "uppercase",
              color: isActive
                ? "var(--amber, #d4a017)"
                : "var(--public-muted, #888)",
              borderBottom: isActive
                ? "2px solid var(--amber, #d4a017)"
                : "2px solid transparent",
              marginBottom: -1,
            }}
          >
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
