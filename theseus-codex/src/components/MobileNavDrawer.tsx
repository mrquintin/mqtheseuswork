"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";

import ThemeToggle from "./ThemeToggle";

/**
 * Mobile drawer for the public site nav. Below 720px the PublicHeader
 * collapses its inline link list and exposes a single hamburger control;
 * tapping it mounts this drawer.
 *
 * Closes on:
 *   - explicit close button
 *   - tap on the scrim outside the drawer body
 *   - Escape key
 *   - route change (pathname effect)
 *
 * Focus is moved into the drawer on open and trapped between the first
 * and last focusable element, then restored to the trigger on close.
 */

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])';

export default function MobileNavDrawer({ authed }: { authed: boolean }) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const drawerRef = useRef<HTMLDivElement | null>(null);
  const pathname = usePathname();
  const drawerId = useId().replace(/:/g, "");

  useEffect(() => {
    if (!open) return;
    setOpen(false);
    // pathname-only dependency: close on route change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  useEffect(() => {
    if (!open) return;

    const previouslyFocused =
      typeof document !== "undefined" ? document.activeElement : null;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const drawer = drawerRef.current;
      if (!drawer) return;
      const focusables = Array.from(
        drawer.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      ).filter((el) => !el.hasAttribute("disabled") && el.tabIndex !== -1);
      if (!focusables.length) {
        event.preventDefault();
        drawer.focus();
        return;
      }
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", onKeyDown);

    const frame = window.requestAnimationFrame(() => {
      const drawer = drawerRef.current;
      if (!drawer) return;
      const [first] = Array.from(
        drawer.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      ).filter((el) => !el.hasAttribute("disabled") && el.tabIndex !== -1);
      (first ?? drawer).focus();
    });

    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      if (
        previouslyFocused &&
        previouslyFocused instanceof HTMLElement &&
        document.contains(previouslyFocused)
      ) {
        previouslyFocused.focus();
      } else {
        triggerRef.current?.focus();
      }
    };
  }, [open]);

  return (
    <>
      <button
        aria-controls={drawerId}
        aria-expanded={open}
        aria-label={open ? "Close navigation menu" : "Open navigation menu"}
        className="public-nav-trigger"
        data-testid="public-nav-trigger"
        onClick={() => setOpen((prev) => !prev)}
        ref={triggerRef}
        type="button"
      >
        <span aria-hidden="true" className="public-nav-trigger-bars">
          <span />
          <span />
          <span />
        </span>
      </button>

      {open ? (
        <div
          className="public-nav-scrim"
          data-testid="public-nav-scrim"
          onClick={(event) => {
            if (event.target === event.currentTarget) setOpen(false);
          }}
        >
          <div
            aria-label="Public navigation"
            aria-modal="true"
            className="public-nav-drawer"
            data-testid="public-nav-drawer"
            id={drawerId}
            onKeyDown={(event) => event.stopPropagation()}
            ref={drawerRef}
            role="dialog"
            tabIndex={-1}
          >
            <div className="public-nav-drawer-head">
              <span className="mono public-nav-drawer-title">Theseus</span>
              <button
                aria-label="Close navigation menu"
                className="public-nav-drawer-close"
                onClick={() => setOpen(false)}
                type="button"
              >
                ×
              </button>
            </div>

            <nav aria-label="Site sections" className="public-nav-drawer-list">
              <Link className="public-nav-drawer-link mono" href="/">
                Home
              </Link>
              <Link className="public-nav-drawer-link mono" href="/about">
                About
              </Link>
              <Link className="public-nav-drawer-link mono" href="/methodology">
                Methodology
              </Link>
              <Link className="public-nav-drawer-link mono" href="/currents">
                Currents
              </Link>
              <Link className="public-nav-drawer-link mono" href="/forecasts">
                Forecasts
              </Link>
            </nav>

            <div className="public-nav-drawer-foot">
              <ThemeToggle size={30} />
              <Link
                className="mono public-nav-drawer-cta"
                href={authed ? "/dashboard" : "/login"}
              >
                {authed ? "Founder Portal →" : "Founder login →"}
              </Link>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
