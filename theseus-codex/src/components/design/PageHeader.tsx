import type { ReactNode } from "react";

/**
 * Compact page header for authenticated/operator surfaces.
 *
 * Use this on workflow pages where the heading should be visible but not
 * theatrical. Mirrors `PageHelp` for content but with smaller Cinzel,
 * tighter tracking, no decorative subtitle row, and plain (non-italic)
 * description copy.
 *
 * For pages that need a one-line "what is this page" banner, keep
 * `PageHelp`; for pages that only need a title plus optional kicker /
 * description, use `PageHeader`.
 */
export default function PageHeader({
  title,
  kicker,
  description,
  actions,
}: {
  title: string;
  kicker?: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div className="page-header__lead">
        {kicker ? <p className="page-header__kicker">{kicker}</p> : null}
        <h1 className="page-header__title">{title}</h1>
        {description ? (
          <p className="page-header__desc">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="page-header__actions">{actions}</div> : null}
    </header>
  );
}
