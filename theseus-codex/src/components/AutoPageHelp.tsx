"use client";

import { usePathname } from "next/navigation";
import PageHelp from "./PageHelp";
import { PAGE_HELP_REGISTRY, normalizePath } from "./pageHelpRegistry";

/**
 * Layout-level auto-injected page help banner.
 *
 * Reads the current pathname, looks up its entry in `PAGE_HELP_REGISTRY`,
 * and renders the corresponding `<PageHelp>`. Pages NOT in the registry
 * (marketing home, obscure detail pages) render nothing here — they can
 * still add a manual `<PageHelp>` if they want dynamic content.
 *
 * Lives in `(authed)/layout.tsx` above `{children}`, so every signed-in
 * page gets the banner without editing the page file itself.
 *
 * Pages that render their own `<PageHelp>` inline (e.g. conclusion detail,
 * where the purpose string includes the conclusion's text) should omit
 * their pathname from the registry to avoid rendering two banners.
 */
export default function AutoPageHelp() {
  const pathname = usePathname();
  const key = normalizePath(pathname);
  const entry = PAGE_HELP_REGISTRY[key];
  if (!entry) return null;
  return (
    <PageHelp
      title={entry.title}
      purpose={entry.purpose}
      howTo={entry.howTo}
      learnMoreHref="/Theseus_Codex_User_Guide.pdf"
    />
  );
}
