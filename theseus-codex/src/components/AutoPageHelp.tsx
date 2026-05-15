"use client";

import { usePathname } from "next/navigation";
import PageHelp from "./PageHelp";
import { PAGE_HELP_REGISTRY, normalizePath } from "./pageHelpRegistry";

/**
 * Layout-level auto-injected page help banner.
 *
 * Reads the current pathname, looks up its entry in `PAGE_HELP_REGISTRY`,
 * and renders the corresponding `<PageHelp>`.
 *
 * This used to mount a rotating ASCII sigil on most pages. That meant
 * ordinary navigation hydrated the ASCII canvas engine and started an
 * animation loop before the founder had done anything. The banner is
 * intentionally text-only now; decorative geometry belongs on pages that
 * explicitly opt into it.
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
