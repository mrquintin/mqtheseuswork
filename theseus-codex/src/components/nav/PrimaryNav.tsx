import Link from "next/link";
import type { ReactNode } from "react";

/**
 * Primary navigation buttons for authenticated workflow surfaces.
 *
 * The Round 20 trigger was the founder noticing the dashboard's
 * "Library" link rendered in a different typeface from "Upload". The
 * underlying cause was per-instance `className` choices on `<Link>` —
 * Library passed `btn btn--quiet` (Inter, mixed case) while Upload
 * passed `btn-solid btn` (Cinzel, uppercase). Both are valid button
 * variants on their own, but rendering them side-by-side in a header
 * makes one look like a sibling and the other like a stray.
 *
 * This primitive is the contract that the header's CTAs share font,
 * size, and weight. The only intentional difference between siblings
 * is the emphasis: `"solid"` paints the primary action, `"quiet"` is
 * the secondary affordance — both still use Cinzel uppercase tracking
 * so neither stands out as "the odd one". When Round 18 prompt 06's
 * shared design system lands, this file can become a re-export.
 *
 * Round 21 added Principles as the firm's spine surface. The
 * dashboard's `PrimaryNav` now leads with a `Principles` link —
 * `PRIMARY_NAV_PRINCIPLES_HREF` is exported so callers don't have to
 * hard-code the path, and so a future canonical-URL change ripples
 * through a single source.
 */

/** Canonical entry point for the firm's principle index. */
export const PRIMARY_NAV_PRINCIPLES_HREF = "/principles";
export type PrimaryNavLinkProps = {
  href: string;
  emphasis?: "default" | "solid";
  children: ReactNode;
};

function primaryNavLinkClassName(emphasis: "default" | "solid"): string {
  // Both variants ride on `.btn` (Cinzel uppercase) so the font
  // family / size / letter-spacing match. `.btn-solid` is purely the
  // filled-vs-outline modifier — it does not change typography.
  return emphasis === "solid" ? "btn btn-solid" : "btn";
}

export function PrimaryNavLink({
  href,
  emphasis = "default",
  children,
}: PrimaryNavLinkProps) {
  return (
    <Link href={href} className={primaryNavLinkClassName(emphasis)}>
      {children}
    </Link>
  );
}

/**
 * Inline container for header-level primary-nav links. The wrapping
 * `data-primary-nav` attribute exists so the Playwright snapshot can
 * grab exactly the nav strip without depending on the surrounding
 * header layout.
 */
export default function PrimaryNav({ children }: { children: ReactNode }) {
  return (
    <div data-primary-nav style={{ display: "contents" }}>
      {children}
    </div>
  );
}
