"use client";

import { useMemo } from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";

import PageKeymap from "@/components/PageKeymap";
import { type HotkeyBinding } from "@/lib/hotkeys";

const TAB_ORDER = [
  "overview",
  "provenance",
  "cascade",
  "peer",
  "blindspots",
  "related",
  "lineage",
  "history",
] as const;

type TabId = (typeof TAB_ORDER)[number];

function isTabId(value: string | null | undefined): value is TabId {
  return TAB_ORDER.some((t) => t === value);
}

/**
 * Conclusion-page keymap: j/k cycle tabs, e edits the conclusion text,
 * r jumps to peer review, p triggers publish (gated by `canPublish`).
 *
 * The bindings are derived from URL state, not local state, so the
 * keymap stays in sync with the active tab without subscribing.
 */
export default function ConclusionKeymap({
  conclusionId,
  canPublish,
}: {
  conclusionId: string;
  canPublish: boolean;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const bindings = useMemo<HotkeyBinding[]>(() => {
    const tabParam = searchParams?.get("tab");
    const current: TabId = isTabId(tabParam) ? tabParam : "overview";
    const currentIndex = TAB_ORDER.indexOf(current);
    function go(tab: TabId) {
      const params = new URLSearchParams(searchParams?.toString() ?? "");
      params.set("tab", tab);
      router.push(`${pathname}?${params.toString()}`);
    }
    return [
      {
        chord: "j",
        description: "Next tab",
        handler: () => go(TAB_ORDER[(currentIndex + 1) % TAB_ORDER.length]),
      },
      {
        chord: "k",
        description: "Previous tab",
        handler: () => go(TAB_ORDER[(currentIndex - 1 + TAB_ORDER.length) % TAB_ORDER.length]),
      },
      {
        chord: "e",
        description: "Edit (focus the conclusion text)",
        handler: () => {
          if (typeof document === "undefined") return;
          const target = document.querySelector("blockquote");
          if (target instanceof HTMLElement) {
            target.scrollIntoView({ behavior: "smooth", block: "center" });
            target.setAttribute("tabindex", "-1");
            target.focus();
          }
        },
      },
      {
        chord: "r",
        description: "Open peer review tab",
        handler: () => go("peer"),
      },
      {
        chord: "p",
        description: canPublish ? "Focus publish controls" : "Publish (disabled — read-only role)",
        options: { enabled: canPublish },
        handler: () => {
          if (typeof document === "undefined") return;
          const node = document.querySelector(
            "[data-testid='publish-toggle'], a[href*='/c/']",
          );
          if (node instanceof HTMLElement) {
            node.scrollIntoView({ behavior: "smooth", block: "center" });
            node.focus();
          }
        },
      },
    ];
  }, [router, pathname, searchParams, canPublish]);

  return <PageKeymap bindings={bindings} label={`Conclusion ${conclusionId.slice(0, 8)}`} />;
}
