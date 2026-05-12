"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  type KeyboardEvent,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
import { ChevronDown, EyeOff, RotateCcw, Trash2 } from "lucide-react";
import ConfidenceTierSigil from "@/components/ConfidenceTierSigil";
import {
  dismissConclusionFromMyDashboard,
  showAllDashboardConclusionsAgain,
  undoConclusionDismissalFromMyDashboard,
} from "./actions";

export type DashboardConclusionCard = {
  id: string;
  confidenceTier: string;
  topicHint: string | null;
  text: string;
};

const DISMISS_TOOLTIP =
  "Hide this conclusion from MY dashboard. Other founders' dashboards are unaffected.";
const REQUEST_DELETION_TOOLTIP =
  "Open the peer-review delete flow in /library.";
const TOAST_DURATION_MS = 8000;

type HiddenConclusion = {
  conclusion: DashboardConclusionCard;
  index: number;
};

export default function DashboardConclusionsClient({
  initialConclusions,
  initialHiddenCount,
}: {
  initialConclusions: DashboardConclusionCard[];
  initialHiddenCount: number;
}) {
  const router = useRouter();
  const [conclusions, setConclusions] = useState(initialConclusions);
  const [hiddenCount, setHiddenCount] = useState(initialHiddenCount);
  const [lastHidden, setLastHidden] = useState<HiddenConclusion | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [sectionBusy, setSectionBusy] = useState(false);
  const [error, setError] = useState("");
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setConclusions(initialConclusions);
  }, [initialConclusions]);

  useEffect(() => {
    setHiddenCount(initialHiddenCount);
  }, [initialHiddenCount]);

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    };
  }, []);

  function queueToast(hidden: HiddenConclusion) {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    setLastHidden(hidden);
    toastTimerRef.current = setTimeout(() => {
      setLastHidden(null);
    }, TOAST_DURATION_MS);
  }

  async function handleDismiss(conclusion: DashboardConclusionCard) {
    if (busyId) return;
    const index = conclusions.findIndex((c) => c.id === conclusion.id);
    const hidden = { conclusion, index: Math.max(0, index) };

    setError("");
    setBusyId(conclusion.id);
    setConclusions((items) => items.filter((item) => item.id !== conclusion.id));
    setHiddenCount((count) => count + 1);
    queueToast(hidden);

    const result = await dismissConclusionFromMyDashboard(conclusion.id);
    if (!result.ok) {
      setConclusions((items) => insertConclusionAt(items, hidden));
      setHiddenCount((count) => Math.max(0, count - 1));
      setLastHidden(null);
      setError(result.error || "Dismiss failed.");
    } else {
      router.refresh();
    }
    setBusyId(null);
  }

  async function handleUndo() {
    if (!lastHidden || sectionBusy) return;
    const hidden = lastHidden;
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);

    setError("");
    setSectionBusy(true);
    setLastHidden(null);
    setConclusions((items) => insertConclusionAt(items, hidden));
    setHiddenCount((count) => Math.max(0, count - 1));

    const result = await undoConclusionDismissalFromMyDashboard(hidden.conclusion.id);
    if (!result.ok) {
      setConclusions((items) =>
        items.filter((item) => item.id !== hidden.conclusion.id),
      );
      setHiddenCount((count) => count + 1);
      setLastHidden(hidden);
      setError(result.error || "Undo failed.");
    } else {
      router.refresh();
    }
    setSectionBusy(false);
  }

  async function handleShowAllAgain() {
    if (hiddenCount === 0 || sectionBusy) return;
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);

    const previousCount = hiddenCount;
    setError("");
    setSectionBusy(true);
    setLastHidden(null);
    setHiddenCount(0);

    const result = await showAllDashboardConclusionsAgain();
    if (!result.ok) {
      setHiddenCount(previousCount);
      setError(result.error || "Could not show hidden conclusions.");
    } else {
      router.refresh();
    }
    setSectionBusy(false);
  }

  return (
    <section
      className="ascii-frame"
      data-label={`CONCLUSIONS · ${toRoman(conclusions.length) || "0"}`}
    >
      <div
        className="mono"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "0.75rem",
          marginBottom: "0.65rem",
          fontSize: "0.58rem",
          letterSpacing: "0.16em",
          textTransform: "uppercase",
          color: "var(--parchment-dim)",
        }}
      >
        <span>{hiddenCount} hidden from your view ·</span>
        <button
          type="button"
          onClick={handleShowAllAgain}
          disabled={hiddenCount === 0 || sectionBusy}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.3rem",
            border: "none",
            background: "none",
            color: hiddenCount === 0 ? "var(--parchment-dim)" : "var(--amber)",
            cursor: hiddenCount === 0 ? "default" : "pointer",
            font: "inherit",
            letterSpacing: "inherit",
            textTransform: "inherit",
            padding: 0,
            opacity: hiddenCount === 0 ? 0.45 : 1,
          }}
        >
          <RotateCcw size={12} aria-hidden="true" />
          Show all again
        </button>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {conclusions.length === 0 ? (
          <LatinEmpty
            latin="No conclusions yet."
            english={
              hiddenCount > 0
                ? "Some conclusions are hidden from your dashboard."
                : "Nothing yet for the firm to affirm."
            }
          />
        ) : (
          conclusions.map((conclusion) => (
            <ConclusionCard
              key={conclusion.id}
              conclusion={conclusion}
              busy={busyId === conclusion.id}
              onDismiss={handleDismiss}
            />
          ))
        )}
      </div>

      {lastHidden ? (
        <div
          role="status"
          className="mono"
          style={{
            marginTop: "0.8rem",
            padding: "0.55rem 0.7rem",
            border: "1px solid var(--amber-dim)",
            borderRadius: 2,
            color: "var(--parchment)",
            background: "rgba(212, 160, 23, 0.08)",
            fontSize: "0.68rem",
            letterSpacing: "0.08em",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: "0.75rem",
          }}
        >
          <span>Hidden from your dashboard.</span>
          <button
            type="button"
            onClick={handleUndo}
            aria-label="Undo dismissal"
            disabled={sectionBusy}
            style={{
              border: "none",
              background: "none",
              color: "var(--amber)",
              cursor: sectionBusy ? "default" : "pointer",
              font: "inherit",
              padding: 0,
              textDecoration: "underline",
              textUnderlineOffset: "3px",
            }}
          >
            Undo
          </button>
        </div>
      ) : null}

      {error ? (
        <div
          role="alert"
          style={{
            marginTop: "0.75rem",
            color: "var(--ember)",
            fontSize: "0.75rem",
          }}
        >
          {error}
        </div>
      ) : null}
    </section>
  );
}

function ConclusionCard({
  conclusion,
  busy,
  onDismiss,
}: {
  conclusion: DashboardConclusionCard;
  busy: boolean;
  onDismiss: (conclusion: DashboardConclusionCard) => Promise<void>;
}) {
  return (
    <div
      data-testid="dashboard-conclusion-card"
      className="portal-card"
      style={{ padding: "0.9rem 1rem" }}
    >
      <div
        style={{
          display: "flex",
          gap: "0.9rem",
          alignItems: "flex-start",
        }}
      >
        <ConfidenceTierSigil tier={conclusion.confidenceTier} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <div
            className="mono"
            style={{
              fontSize: "0.6rem",
              color: "var(--amber-dim)",
              textTransform: "uppercase",
              letterSpacing: "0.12em",
            }}
          >
            {conclusion.confidenceTier} · {conclusion.topicHint || "general"}
          </div>
          <p
            style={{
              marginTop: "0.4rem",
              marginBottom: 0,
              fontSize: "0.95rem",
              color: "var(--parchment)",
              lineHeight: 1.5,
            }}
          >
            {conclusion.text}
          </p>
        </div>
        <ConclusionActionMenu
          conclusion={conclusion}
          busy={busy}
          onDismiss={onDismiss}
        />
      </div>
    </div>
  );
}

function ConclusionActionMenu({
  conclusion,
  busy,
  onDismiss,
}: {
  conclusion: DashboardConclusionCard;
  busy: boolean;
  onDismiss: (conclusion: DashboardConclusionCard) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [showHint, setShowHint] = useState(false);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | HTMLAnchorElement | null>>([]);
  const tooltipId = useId();
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    function onWindowPointerDown(event: PointerEvent) {
      const target = event.target as Node | null;
      if (!target) return;
      const button = buttonRef.current;
      const menuItems = itemRefs.current;
      if (button?.contains(target)) return;
      if (menuItems.some((item) => item?.contains(target))) return;
      setOpen(false);
    }
    window.addEventListener("pointerdown", onWindowPointerDown);
    return () => window.removeEventListener("pointerdown", onWindowPointerDown);
  }, [open]);

  function focusItem(index: number) {
    itemRefs.current[index]?.focus();
  }

  function openMenu(index = 0) {
    setOpen(true);
    window.requestAnimationFrame(() => focusItem(index));
  }

  function closeMenu() {
    setOpen(false);
    window.requestAnimationFrame(() => buttonRef.current?.focus());
  }

  function onButtonKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (
      event.key === "Enter" ||
      event.key === " " ||
      event.key === "ArrowDown"
    ) {
      event.preventDefault();
      openMenu(0);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      openMenu(1);
    }
  }

  function onMenuKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const activeIndex = itemRefs.current.findIndex(
      (item) => item === document.activeElement,
    );
    if (event.key === "ArrowDown") {
      event.preventDefault();
      focusItem(activeIndex >= 0 ? (activeIndex + 1) % 2 : 0);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      focusItem(activeIndex >= 0 ? (activeIndex + 2 - 1) % 2 : 1);
    } else if (event.key === "Home") {
      event.preventDefault();
      focusItem(0);
    } else if (event.key === "End") {
      event.preventDefault();
      focusItem(1);
    } else if (event.key === "Escape") {
      event.preventDefault();
      closeMenu();
    } else if (event.key === "Tab") {
      setOpen(false);
    }
  }

  const requestDeletionHref = `/library?request=${encodeURIComponent(
    conclusion.id,
  )}#conclusion-deletion-request`;

  return (
    <div style={{ position: "relative", flexShrink: 0 }}>
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-describedby={showHint && !open ? tooltipId : undefined}
        aria-label={`Conclusion actions for: ${truncate(conclusion.text, 72)}`}
        onClick={() => (open ? setOpen(false) : openMenu(0))}
        onKeyDown={onButtonKeyDown}
        onMouseEnter={() => setShowHint(true)}
        onMouseLeave={() => setShowHint(false)}
        onFocus={() => setShowHint(true)}
        onBlur={() => setShowHint(false)}
        disabled={busy}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "0.32rem",
          border: "1px solid var(--stroke)",
          background: "rgba(10, 10, 10, 0.26)",
          color: "var(--parchment-dim)",
          cursor: busy ? "default" : "pointer",
          fontFamily: "'Cinzel', serif",
          fontSize: "0.58rem",
          letterSpacing: "0.12em",
          textTransform: "uppercase",
          padding: "0.28rem 0.45rem",
          borderRadius: 2,
          lineHeight: 1,
          opacity: busy ? 0.45 : 0.92,
        }}
      >
        <EyeOff size={13} aria-hidden="true" />
        Actions
        <ChevronDown size={12} aria-hidden="true" />
      </button>

      {showHint && !open ? (
        <div
          id={tooltipId}
          role="tooltip"
          style={{
            position: "absolute",
            right: 0,
            top: "calc(100% + 0.35rem)",
            zIndex: 6,
            width: "15rem",
            padding: "0.45rem 0.55rem",
            border: "1px solid var(--amber-dim)",
            borderRadius: 2,
            background: "rgba(18, 15, 11, 0.97)",
            color: "var(--parchment)",
            fontSize: "0.68rem",
            lineHeight: 1.35,
            boxShadow: "0 12px 28px rgba(0,0,0,0.35)",
          }}
        >
          Dismiss is a private dashboard hide. Deletion opens peer review.
        </div>
      ) : null}

      {open ? (
        <div
          id={menuId}
          role="menu"
          aria-label="Conclusion actions"
          onKeyDown={onMenuKeyDown}
          style={{
            position: "absolute",
            right: 0,
            top: "calc(100% + 0.35rem)",
            zIndex: 7,
            minWidth: "16rem",
            padding: "0.35rem",
            border: "1px solid var(--stroke)",
            borderRadius: 3,
            background: "rgba(18, 15, 11, 0.98)",
            boxShadow: "0 16px 34px rgba(0,0,0,0.42)",
          }}
        >
          <button
            ref={(node) => {
              itemRefs.current[0] = node;
            }}
            type="button"
            role="menuitem"
            title={DISMISS_TOOLTIP}
            aria-label={DISMISS_TOOLTIP}
            onClick={() => {
              setOpen(false);
              void onDismiss(conclusion);
            }}
            style={menuItemStyle}
          >
            <EyeOff size={14} aria-hidden="true" />
            <span>Dismiss from my view</span>
          </button>
          <Link
            ref={(node) => {
              itemRefs.current[1] = node;
            }}
            href={requestDeletionHref}
            role="menuitem"
            title={REQUEST_DELETION_TOOLTIP}
            aria-label={`Request deletion. ${REQUEST_DELETION_TOOLTIP}`}
            onClick={() => setOpen(false)}
            style={{
              ...menuItemStyle,
              color: "var(--ember)",
              textDecoration: "none",
            }}
          >
            <Trash2 size={14} aria-hidden="true" />
            <span>Request deletion...</span>
          </Link>
        </div>
      ) : null}
    </div>
  );
}

function insertConclusionAt(
  items: DashboardConclusionCard[],
  hidden: HiddenConclusion,
) {
  if (items.some((item) => item.id === hidden.conclusion.id)) return items;
  const next = [...items];
  next.splice(Math.min(hidden.index, next.length), 0, hidden.conclusion);
  return next;
}

function LatinEmpty({ latin, english }: { latin: string; english: string }) {
  return (
    <div style={{ padding: "1rem 0.25rem", textAlign: "center" }}>
      <p
        style={{
          fontFamily: "'EB Garamond', serif",
          fontSize: "1rem",
          color: "var(--parchment)",
          margin: 0,
        }}
      >
        {latin}
      </p>
      <p
        className="mono"
        style={{
          fontSize: "0.7rem",
          color: "var(--parchment-dim)",
          marginTop: "0.25rem",
        }}
      >
        {english}
      </p>
    </div>
  );
}

const menuItemStyle = {
  width: "100%",
  display: "flex",
  alignItems: "center",
  gap: "0.5rem",
  border: "none",
  background: "transparent",
  color: "var(--parchment)",
  cursor: "pointer",
  fontFamily: "'EB Garamond', serif",
  fontSize: "0.88rem",
  lineHeight: 1.2,
  textAlign: "left" as const,
  padding: "0.45rem 0.5rem",
  borderRadius: 2,
};

function toRoman(n: number): string {
  if (!n || n < 1) return "";
  const table: [number, string][] = [
    [10, "X"],
    [9, "IX"],
    [5, "V"],
    [4, "IV"],
    [1, "I"],
  ];
  let out = "";
  let rem = n;
  for (const [value, roman] of table) {
    while (rem >= value) {
      out += roman;
      rem -= value;
    }
  }
  return out;
}

function truncate(value: string, max: number) {
  return value.length > max ? `${value.slice(0, max - 3)}...` : value;
}
