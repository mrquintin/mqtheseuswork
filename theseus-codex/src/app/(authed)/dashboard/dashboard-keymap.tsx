"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import PageKeymap from "@/components/PageKeymap";
import { type HotkeyBinding } from "@/lib/hotkeys";

interface AttentionItemSlim {
  queue: string;
  itemId: string;
  link: string;
  preview: string;
}

/**
 * Dashboard keymap: Enter focuses (navigates into) the current item, n
 * advances to the next, x dismisses the current. The queue is fetched
 * once on mount; n/x then operate on a local cursor.
 *
 * Dismiss prompts via window.prompt for the required reason — the
 * attention API rejects empty reasons, and the dashboard already
 * surfaces a richer dismiss form for users who'd rather use it.
 */
export default function DashboardKeymap() {
  const router = useRouter();
  const [items, setItems] = useState<AttentionItemSlim[]>([]);
  const cursor = useRef(0);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch("/api/founder/attention", { cache: "no-store" });
        if (!res.ok || cancelled) return;
        const json = (await res.json()) as { items?: AttentionItemSlim[] };
        if (!cancelled && Array.isArray(json.items)) setItems(json.items);
      } catch {
        // ignore
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const advance = useCallback(() => {
    if (items.length === 0) return;
    cursor.current = (cursor.current + 1) % items.length;
  }, [items]);

  const focusCurrent = useCallback(() => {
    const item = items[cursor.current];
    if (!item) return;
    router.push(item.link);
  }, [items, router]);

  const dismissCurrent = useCallback(async () => {
    const item = items[cursor.current];
    if (!item) return;
    const reason = typeof window !== "undefined" ? window.prompt("Dismiss reason?") : "";
    if (!reason) return;
    try {
      await fetch("/api/founder/attention", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          queue: item.queue,
          itemId: item.itemId,
          action: "dismiss",
          reason,
        }),
      });
    } catch {
      return;
    }
    setItems((current) => current.filter((entry) => entry.itemId !== item.itemId));
    cursor.current = 0;
    router.refresh();
  }, [items, router]);

  const bindings = useMemo<HotkeyBinding[]>(
    () => [
      {
        chord: "enter",
        description: "Open the current attention item",
        handler: () => focusCurrent(),
      },
      {
        chord: "n",
        description: "Cursor → next attention item",
        handler: () => advance(),
      },
      {
        chord: "x",
        description: "Dismiss the current attention item",
        handler: () => {
          void dismissCurrent();
        },
      },
    ],
    [advance, dismissCurrent, focusCurrent],
  );

  return <PageKeymap bindings={bindings} label="Dashboard" />;
}
