"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

const NOTICES: Record<string, string> = {
  "publication-retired":
    "Publication has been retired. Conclusions show their publish state inline.",
};

export default function RetiredRouteToast({ notice }: { notice?: string }) {
  const message = notice ? NOTICES[notice] : undefined;
  const [visible, setVisible] = useState(false);
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    if (!notice || !message) return;
    // R-014: dismissal keys include the retired path so a stale bookmark
    // for a different retired route still fires its notice once per
    // session, instead of being suppressed by an unrelated earlier one.
    const key = `theseus:retired-route-notice:${notice}:${pathname}`;
    try {
      if (window.sessionStorage.getItem(key) === "1") return;
      window.sessionStorage.setItem(key, "1");
    } catch {
      /* If storage is unavailable, still show the notice once on mount. */
    }
    setVisible(true);
    const hide = window.setTimeout(() => setVisible(false), 6500);

    const params = new URLSearchParams(searchParams.toString());
    params.delete("notice");
    const next = params.toString();
    router.replace(`${pathname}${next ? `?${next}` : ""}`, { scroll: false });

    return () => window.clearTimeout(hide);
  }, [message, notice, pathname, router, searchParams]);

  if (!visible || !message) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="portal-card"
      style={{
        position: "fixed",
        right: "1rem",
        bottom: "1rem",
        zIndex: 80,
        maxWidth: "24rem",
        padding: "0.85rem 1rem",
        borderLeft: "3px solid var(--gold)",
        color: "var(--parchment)",
        boxShadow: "0 18px 40px rgba(0, 0, 0, 0.35)",
      }}
    >
      {message}
    </div>
  );
}
