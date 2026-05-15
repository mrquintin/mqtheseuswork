import { type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Reader guide (Round 21 — onboarding guide for outside readers).
 *
 * Three things under test, matching what the guide is judged on:
 *   - the guide page renders all seven stops, each with its reading-time
 *     annotation and its links out to the surface it indexes (snapshot +
 *     content assertions);
 *   - the reading-tour overlay renders correctly at every stop and at
 *     the completion state (a snapshot per step page — i.e. per tour
 *     stop view);
 *   - the tour state machine walks next / prev / dismiss / complete
 *     correctly, and only a completed tour produces an export record.
 *
 * The test environment is node (no jsdom): the page and overlay are
 * exercised via `renderToStaticMarkup`, and the navigation behaviour is
 * verified through the pure `tourReducer` and its selectors.
 */

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: {
    children: ReactNode;
    href: string;
    [key: string]: unknown;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/components/PublicHeader", () => ({
  default: ({ authed }: { authed: boolean }) => (
    <header data-authed={String(authed)}>Public header</header>
  ),
}));

vi.mock("@/components/SubscribeForm", () => ({
  default: ({ title }: { title: string }) => (
    <div data-subscribe-form>{title}</div>
  ),
}));

vi.mock("@/lib/auth", () => ({
  getFounder: vi.fn().mockResolvedValue(null),
}));

import ReaderGuidePage from "@/app/about/reader-guide/page";
import ReaderTourOverlay from "@/components/ReaderTourOverlay";
import {
  INITIAL_TOUR_STATE,
  READER_GUIDE_STEPS,
  currentTourStep,
  exportTourRecord,
  fastPathReadingMinutes,
  isTourComplete,
  tourProgressLabel,
  tourReducer,
  totalReadingMinutes,
  type TourState,
} from "@/lib/readerTour";

const noop = () => {};

/** React escapes text content when it renders; mirror that so a tour
 * note with an apostrophe still matches against the markup. */
function htmlText(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#x27;");
}

function overlayProps(state: TourState) {
  return {
    state,
    onNext: noop,
    onPrev: noop,
    onDismiss: noop,
    onRestart: noop,
    onExport: noop,
  };
}

describe("ReaderGuidePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("snapshots the full reader guide page", async () => {
    const html = renderToStaticMarkup(await ReaderGuidePage());
    expect(html).toMatchSnapshot();
  });

  it("renders all seven stops, each with a reading-time annotation", async () => {
    const html = renderToStaticMarkup(await ReaderGuidePage());

    for (const step of READER_GUIDE_STEPS) {
      expect(html).toContain(`id="step-${step.id}"`);
      expect(html).toContain(step.title);
      expect(html).toContain(`reading-time-${step.id}`);
      expect(html).toContain(`${step.readingMinutes} min read`);
    }
  });

  it("links every step out to the surface it indexes", async () => {
    const html = renderToStaticMarkup(await ReaderGuidePage());

    for (const step of READER_GUIDE_STEPS) {
      for (const link of step.links) {
        expect(html).toContain(`href="${link.href}"`);
      }
    }
    // The meta-method commitment is an external document.
    expect(html).toContain(
      'href="https://github.com/mrquintin/mqtheseuswork/blob/main/THE_META_METHOD.md"',
    );
  });

  it("states both the full path and the fast path reading budgets", async () => {
    const html = renderToStaticMarkup(await ReaderGuidePage());
    expect(html).toContain(`${totalReadingMinutes()} minutes`);
    expect(html).toContain(`${fastPathReadingMinutes()} minutes`);
  });

  it("renders the subscriber form and the tour entry point", async () => {
    const html = renderToStaticMarkup(await ReaderGuidePage());
    expect(html).toContain("data-subscribe-form");
    expect(html).toContain('id="subscribe"');
    expect(html).toContain('data-testid="reader-tour-start"');
  });
});

describe("ReaderTourOverlay — a snapshot per step page", () => {
  READER_GUIDE_STEPS.forEach((step, index) => {
    it(`snapshots the overlay at stop ${index + 1}: ${step.id}`, () => {
      const state: TourState = { status: "active", stepIndex: index };
      const html = renderToStaticMarkup(
        <ReaderTourOverlay {...overlayProps(state)} />,
      );
      expect(html).toMatchSnapshot();
      expect(html).toContain(htmlText(step.title));
      expect(html).toContain(htmlText(step.tourNote));
      expect(html).toContain(tourProgressLabel(state));
      // Every stop exposes next / prev / dismiss controls.
      expect(html).toContain('data-testid="reader-tour-next"');
      expect(html).toContain('data-testid="reader-tour-prev"');
      expect(html).toContain('data-testid="reader-tour-dismiss"');
    });
  });

  it("disables the previous control on the first stop only", () => {
    const first = renderToStaticMarkup(
      <ReaderTourOverlay {...overlayProps({ status: "active", stepIndex: 0 })} />,
    );
    expect(first).toMatch(/data-testid="reader-tour-prev"[^>]*disabled/);

    const second = renderToStaticMarkup(
      <ReaderTourOverlay {...overlayProps({ status: "active", stepIndex: 1 })} />,
    );
    expect(second).not.toMatch(/data-testid="reader-tour-prev"[^>]*disabled/);
  });

  it("labels the advance button 'Finish tour' on the last stop", () => {
    const last = renderToStaticMarkup(
      <ReaderTourOverlay
        {...overlayProps({
          status: "active",
          stepIndex: READER_GUIDE_STEPS.length - 1,
        })}
      />,
    );
    expect(last).toContain("Finish tour");
  });

  it("snapshots the completion state with an export control", () => {
    const state: TourState = {
      status: "complete",
      stepIndex: READER_GUIDE_STEPS.length - 1,
    };
    const html = renderToStaticMarkup(
      <ReaderTourOverlay {...overlayProps(state)} />,
    );
    expect(html).toMatchSnapshot();
    expect(html).toContain("completed the tour");
    expect(html).toContain('data-testid="reader-tour-export"');
    expect(html).toContain('data-testid="reader-tour-restart"');
  });

  it("renders nothing while idle or dismissed", () => {
    expect(
      renderToStaticMarkup(
        <ReaderTourOverlay {...overlayProps(INITIAL_TOUR_STATE)} />,
      ),
    ).toBe("");
    expect(
      renderToStaticMarkup(
        <ReaderTourOverlay
          {...overlayProps({ status: "dismissed", stepIndex: 3 })}
        />,
      ),
    ).toBe("");
  });
});

describe("tourReducer — next / prev / dismiss navigation", () => {
  it("starts the tour at the first stop", () => {
    const started = tourReducer(INITIAL_TOUR_STATE, { type: "start" });
    expect(started).toEqual({ status: "active", stepIndex: 0 });
    expect(currentTourStep(started)?.id).toBe(READER_GUIDE_STEPS[0].id);
  });

  it("advances forward one stop at a time", () => {
    let state = tourReducer(INITIAL_TOUR_STATE, { type: "start" });
    state = tourReducer(state, { type: "next" });
    expect(state).toEqual({ status: "active", stepIndex: 1 });
    state = tourReducer(state, { type: "next" });
    expect(state).toEqual({ status: "active", stepIndex: 2 });
  });

  it("steps back with prev and clamps at the first stop", () => {
    let state: TourState = { status: "active", stepIndex: 2 };
    state = tourReducer(state, { type: "prev" });
    expect(state).toEqual({ status: "active", stepIndex: 1 });
    state = tourReducer(state, { type: "prev" });
    expect(state).toEqual({ status: "active", stepIndex: 0 });
    // Already at the first stop — prev is a no-op, not an underflow.
    state = tourReducer(state, { type: "prev" });
    expect(state).toEqual({ status: "active", stepIndex: 0 });
  });

  it("completes the tour when advancing past the last stop", () => {
    let state: TourState = {
      status: "active",
      stepIndex: READER_GUIDE_STEPS.length - 1,
    };
    state = tourReducer(state, { type: "next" });
    expect(state.status).toBe("complete");
    expect(isTourComplete(state)).toBe(true);
    expect(state.stepIndex).toBe(READER_GUIDE_STEPS.length - 1);
  });

  it("walks the whole tour start-to-finish", () => {
    let state = tourReducer(INITIAL_TOUR_STATE, { type: "start" });
    // One "next" per stop: the last advances past the final stop and
    // completes the tour.
    for (let i = 0; i < READER_GUIDE_STEPS.length; i += 1) {
      expect(state.status).toBe("active");
      state = tourReducer(state, { type: "next" });
    }
    expect(isTourComplete(state)).toBe(true);
  });

  it("dismisses from any stop and keeps the stop index", () => {
    const dismissed = tourReducer(
      { status: "active", stepIndex: 4 },
      { type: "dismiss" },
    );
    expect(dismissed).toEqual({ status: "dismissed", stepIndex: 4 });
  });

  it("ignores next and prev unless the tour is active", () => {
    const dismissed: TourState = { status: "dismissed", stepIndex: 2 };
    expect(tourReducer(dismissed, { type: "next" })).toBe(dismissed);
    expect(tourReducer(dismissed, { type: "prev" })).toBe(dismissed);

    const complete: TourState = { status: "complete", stepIndex: 6 };
    expect(tourReducer(complete, { type: "next" })).toBe(complete);

    expect(tourReducer(INITIAL_TOUR_STATE, { type: "next" })).toBe(
      INITIAL_TOUR_STATE,
    );
  });

  it("restarts a dismissed or completed tour back at the first stop", () => {
    const fromDismissed = tourReducer(
      { status: "dismissed", stepIndex: 5 },
      { type: "restart" },
    );
    expect(fromDismissed).toEqual({ status: "active", stepIndex: 0 });

    const fromComplete = tourReducer(
      { status: "complete", stepIndex: 6 },
      { type: "restart" },
    );
    expect(fromComplete).toEqual({ status: "active", stepIndex: 0 });
  });

  it("reports progress as 'Stop N of total' across the tour", () => {
    expect(tourProgressLabel({ status: "active", stepIndex: 0 })).toBe(
      `Stop 1 of ${READER_GUIDE_STEPS.length}`,
    );
    expect(
      tourProgressLabel({
        status: "active",
        stepIndex: READER_GUIDE_STEPS.length - 1,
      }),
    ).toBe(`Stop ${READER_GUIDE_STEPS.length} of ${READER_GUIDE_STEPS.length}`);
  });
});

describe("exportTourRecord — completion produces a record, nothing else does", () => {
  it("returns null for a tour that has not completed", () => {
    expect(exportTourRecord(INITIAL_TOUR_STATE)).toBeNull();
    expect(exportTourRecord({ status: "active", stepIndex: 3 })).toBeNull();
    expect(exportTourRecord({ status: "dismissed", stepIndex: 6 })).toBeNull();
  });

  it("returns an exportable record once the tour is complete", () => {
    const now = new Date("2026-05-14T12:00:00.000Z");
    const record = exportTourRecord(
      { status: "complete", stepIndex: READER_GUIDE_STEPS.length - 1 },
      now,
    );
    expect(record).toEqual({
      completedAt: now.toISOString(),
      stepsViewed: READER_GUIDE_STEPS.length,
      steps: READER_GUIDE_STEPS.map((step) => step.id),
    });
  });
});
