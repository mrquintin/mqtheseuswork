"use client";

import dynamic from "next/dynamic";
import { usePathname } from "next/navigation";
import PageHelp from "./PageHelp";
import { PAGE_HELP_REGISTRY, normalizePath } from "./pageHelpRegistry";

/**
 * Layout-level auto-injected page help banner.
 *
 * Reads the current pathname, looks up its entry in `PAGE_HELP_REGISTRY`,
 * and renders the corresponding `<PageHelp>`. If the registry entry has a
 * `sigil` set, we also mount a tiny rotating-ASCII Platonic-solid emblem
 * next to the title.
 *
 * The sigil import is done via `next/dynamic({ ssr: false })` BECAUSE we
 * need to avoid rendering the ASCII sigil on the server. Next 16 requires
 * that `{ ssr: false }` be used only from client components — so the
 * dynamic import lives here, in this `"use client"` file, rather than in
 * `PageHelp.tsx` (which stays server-safe).
 */

const AsciiSigil = dynamic(() => import("./AsciiSigil"), {
  ssr: false,
  loading: () => (
    <div
      aria-hidden="true"
      style={{ width: 128, height: 56, opacity: 0 }}
    />
  ),
});

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
      sigil={
        entry.sigil ? (
          <AsciiSigil shape={entry.sigil} cols={24} rows={10} size={128} speed={0.8} />
        ) : null
      }
      learnMoreHref="/Theseus_Codex_User_Guide.pdf"
    />
  );
}
