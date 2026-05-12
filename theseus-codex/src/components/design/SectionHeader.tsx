import type { ReactNode } from "react";

/**
 * Compact section heading for grouped content inside a page.
 *
 * Reserved tracking (≥0.12em uppercase) is the *kicker* label, not the
 * heading itself — keeps small caps where they belong (labels) and
 * stops them from competing with body copy.
 */
export default function SectionHeader({
  title,
  kicker,
  hint,
  actions,
  as = "h2",
}: {
  title: ReactNode;
  kicker?: string;
  hint?: ReactNode;
  actions?: ReactNode;
  as?: "h2" | "h3";
}) {
  const Heading = as;
  return (
    <div className="section-header">
      <div className="section-header__lead">
        {kicker ? (
          <span className="section-header__kicker mono">{kicker}</span>
        ) : null}
        <Heading className="section-header__title">{title}</Heading>
        {hint ? <p className="section-header__hint">{hint}</p> : null}
      </div>
      {actions ? <div className="section-header__actions">{actions}</div> : null}
    </div>
  );
}
