// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  waitFor,
} from "@testing-library/react";
import { FollowupChat } from "@/app/currents/[id]/FollowupChat";
import type {
  PublicCitation,
  PublicFollowupMessage,
} from "@/lib/currentsTypes";
import type { StreamFrame } from "@/lib/currentsApi";
import {
  clearSessionId,
  saveSessionId,
} from "@/lib/followupSession";

vi.mock("@/lib/currentsApi", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/currentsApi")>(
      "@/lib/currentsApi",
    );
  return {
    ...actual,
    streamFollowup: vi.fn(),
    listFollowupMessages: vi.fn(),
  };
});

import { listFollowupMessages, streamFollowup } from "@/lib/currentsApi";

const streamFollowupMock = vi.mocked(streamFollowup);
const listFollowupMessagesMock = vi.mocked(listFollowupMessages);

beforeEach(() => {
  // jsdom doesn't implement scrollIntoView — stub it.
  Element.prototype.scrollIntoView = vi.fn() as unknown as (
    arg?: boolean | ScrollIntoViewOptions,
  ) => void;
  streamFollowupMock.mockReset();
  listFollowupMessagesMock.mockReset();
});

afterEach(() => {
  cleanup();
  try {
    sessionStorage.clear();
  } catch {
    /* noop */
  }
  vi.useRealTimers();
});

function framesGen(frames: StreamFrame[]) {
  return async function* () {
    for (const f of frames) yield f;
  };
}

function citation(sourceId: string): PublicCitation {
  return {
    source_kind: "conclusion",
    source_id: sourceId,
    quoted_span: "quoted",
    relevance_score: 0.8,
  };
}

describe("FollowupChat", () => {
  it("renders the input and does not fetch history when there is no stored session", () => {
    clearSessionId("op-1");
    const { getByTestId } = render(<FollowupChat opinionId="op-1" />);
    expect(getByTestId("followup-input")).toBeTruthy();
    expect(listFollowupMessagesMock).not.toHaveBeenCalled();
  });

  it("loads prior history when a session id is stored", async () => {
    saveSessionId("op-1", "sess-prior");
    const history: PublicFollowupMessage[] = [
      {
        id: "m1",
        role: "user",
        created_at: "2026-04-20T00:00:00Z",
        content: "earlier question",
        citations: [],
        refused: false,
        refusal_reason: null,
      },
      {
        id: "m2",
        role: "assistant",
        created_at: "2026-04-20T00:00:01Z",
        content: "earlier answer",
        citations: [],
        refused: false,
        refusal_reason: null,
      },
    ];
    listFollowupMessagesMock.mockResolvedValue(history);

    const { findByText } = render(<FollowupChat opinionId="op-1" />);
    expect(listFollowupMessagesMock).toHaveBeenCalledWith("op-1", "sess-prior");
    await findByText("earlier question");
    await findByText("earlier answer");
  });

  it("streams tokens and renders the final assistant message with a citation chip", async () => {
    streamFollowupMock.mockImplementation(
      framesGen([
        { kind: "meta", data: { session_id: "sess-new", opinion_id: "op-1" } },
        { kind: "token", data: "Hello " },
        { kind: "token", data: "there" },
        { kind: "token", data: "." },
        { kind: "citation", data: citation("src-xyz") },
        { kind: "done", data: { refused: false, refusal_reason: null } },
      ]),
    );

    const { getByTestId, getAllByTestId } = render(
      <FollowupChat opinionId="op-1" />,
    );
    const input = getByTestId("followup-input") as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "why?" } });
    fireEvent.submit(getByTestId("followup-form"));

    await waitFor(() => {
      expect(getAllByTestId("followup-asst-msg")).toHaveLength(1);
    });
    const asst = getAllByTestId("followup-asst-msg")[0];
    expect(asst.textContent).toContain("Hello there.");
    const chips = getAllByTestId("followup-citation-chip");
    expect(chips).toHaveLength(1);
    expect(chips[0].getAttribute("href")).toBe("#src-src-xyz");
  });

  it("renders an error line when the stream yields an error frame", async () => {
    streamFollowupMock.mockImplementation(
      framesGen([
        { kind: "meta", data: { session_id: "s", opinion_id: "op-1" } },
        {
          kind: "error",
          data: { error: "model_failure", reason: "model transport failed" },
        },
      ]),
    );

    const { getByTestId, getAllByTestId } = render(
      <FollowupChat opinionId="op-1" />,
    );
    fireEvent.change(getByTestId("followup-input"), {
      target: { value: "test" },
    });
    fireEvent.submit(getByTestId("followup-form"));

    await waitFor(() => {
      expect(getAllByTestId("followup-asst-msg")).toHaveLength(1);
    });
    const asst = getAllByTestId("followup-asst-msg")[0];
    expect(asst.textContent).toContain("model transport failed");
    expect(asst.getAttribute("data-role")).toBe("assistant");
  });

  it("shows the rate-limit copy when streamFollowup throws 429", async () => {
    streamFollowupMock.mockImplementation(async function* () {
      const err = new Error("rate") as Error & { status?: number };
      err.status = 429;
      throw err;
      // eslint-disable-next-line no-unreachable
      yield { kind: "token", data: "" } as StreamFrame;
    });

    const { getByTestId, getAllByTestId } = render(
      <FollowupChat opinionId="op-1" />,
    );
    fireEvent.change(getByTestId("followup-input"), {
      target: { value: "why?" },
    });
    fireEvent.submit(getByTestId("followup-form"));

    await waitFor(() => {
      expect(getAllByTestId("followup-asst-msg")).toHaveLength(1);
    });
    expect(getAllByTestId("followup-asst-msg")[0].textContent).toContain(
      "You've hit the follow-up rate limit. Try again in a few minutes.",
    );
  });

  it("submits on Enter and inserts a newline on Shift+Enter", async () => {
    streamFollowupMock.mockImplementation(
      framesGen([
        { kind: "meta", data: { session_id: "s", opinion_id: "op-1" } },
        { kind: "token", data: "ok" },
        { kind: "done", data: { refused: false, refusal_reason: null } },
      ]),
    );

    const { getByTestId, getAllByTestId } = render(
      <FollowupChat opinionId="op-1" />,
    );
    const input = getByTestId("followup-input") as HTMLTextAreaElement;

    // Shift+Enter -> newline inserted in the controlled value.
    fireEvent.change(input, { target: { value: "line1" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
    // The handler must not call preventDefault on Shift+Enter; simulate the
    // native newline the browser would insert.
    fireEvent.change(input, { target: { value: "line1\nline2" } });
    expect(input.value).toContain("\n");
    expect(streamFollowupMock).not.toHaveBeenCalled();

    // Enter (no shift) -> submits.
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false });
    await waitFor(() => {
      expect(streamFollowupMock).toHaveBeenCalledTimes(1);
    });
    const [, body] = streamFollowupMock.mock.calls[0];
    expect(body.question).toBe("line1\nline2");
    // Final assistant message renders.
    await waitFor(() => {
      expect(getAllByTestId("followup-asst-msg")).toHaveLength(1);
    });
  });

  it("enforces a client-side rate limit of 1 message per 2s", async () => {
    streamFollowupMock.mockImplementation(
      framesGen([
        { kind: "meta", data: { session_id: "s", opinion_id: "op-1" } },
        { kind: "token", data: "ok" },
        { kind: "done", data: { refused: false, refusal_reason: null } },
      ]),
    );

    const { getByTestId, queryByTestId } = render(
      <FollowupChat opinionId="op-1" />,
    );
    const input = getByTestId("followup-input") as HTMLTextAreaElement;

    // First send
    fireEvent.change(input, { target: { value: "first?" } });
    fireEvent.submit(getByTestId("followup-form"));

    // Wait for the stream to finish so the assistant message materializes
    // (this also means `busy` is false again).
    await waitFor(() => {
      expect(streamFollowupMock).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      // Input is cleared after a successful send; reselect for certainty.
      expect((getByTestId("followup-input") as HTMLTextAreaElement).disabled)
        .toBe(false);
    });

    // Immediately try again (within the 2s cooldown).
    fireEvent.change(getByTestId("followup-input"), {
      target: { value: "second?" },
    });
    await act(async () => {
      fireEvent.submit(getByTestId("followup-form"));
    });

    // No second call to streamFollowup yet.
    expect(streamFollowupMock).toHaveBeenCalledTimes(1);
    const inlineErr = queryByTestId("followup-inline-error");
    expect(inlineErr?.textContent).toContain(
      "Slow down — wait a couple of seconds between messages.",
    );
  });
});
