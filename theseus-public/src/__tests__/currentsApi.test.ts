import { afterEach, describe, expect, it, vi } from "vitest";
import {
  listCurrents,
  parseSseFrame,
  streamFollowup,
} from "@/lib/currentsApi";
import type { PaginatedOpinions, PublicOpinion } from "@/lib/currentsTypes";

function makeOpinion(id: string): PublicOpinion {
  return {
    id,
    event_id: `evt-${id}`,
    event_source_url: "https://x.example/status/1",
    event_author_handle: "author",
    event_captured_at: "2026-04-20T00:00:00Z",
    topic_hint: null,
    stance: "agrees",
    confidence: 0.5,
    headline: "h",
    body_markdown: "b",
    uncertainty_notes: [],
    generated_at: "2026-04-20T00:00:01Z",
    citations: [],
    revoked: false,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("listCurrents", () => {
  it("parses paginated response", async () => {
    const payload: PaginatedOpinions = {
      items: [makeOpinion("op-1"), makeOpinion("op-2")],
      next_cursor: "abc",
    };
    const fakeFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fakeFetch);

    const result = await listCurrents({ limit: 2 });
    expect(result.items).toHaveLength(2);
    expect(result.items[0].id).toBe("op-1");
    expect(result.next_cursor).toBe("abc");
    expect(fakeFetch).toHaveBeenCalledOnce();
    const calledUrl = String(fakeFetch.mock.calls[0][0]);
    expect(calledUrl).toContain("limit=2");
  });
});

describe("parseSseFrame", () => {
  it("parses a token frame with string data", () => {
    const frame = parseSseFrame("event: token\ndata: hello");
    expect(frame).toEqual({ kind: "token", data: "hello" });
  });

  it("parses a citation frame with JSON data", () => {
    const frame = parseSseFrame(
      'event: citation\ndata: {"source_kind":"conclusion","source_id":"c1","quoted_span":"x","relevance_score":0.8}',
    );
    expect(frame).toEqual({
      kind: "citation",
      data: {
        source_kind: "conclusion",
        source_id: "c1",
        quoted_span: "x",
        relevance_score: 0.8,
      },
    });
  });

  it("parses a done frame", () => {
    const frame = parseSseFrame(
      'event: done\ndata: {"refused":false,"refusal_reason":null}',
    );
    expect(frame).toEqual({
      kind: "done",
      data: { refused: false, refusal_reason: null },
    });
  });
});

function sseBodyStream(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  let i = 0;
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (i >= chunks.length) {
        controller.close();
        return;
      }
      controller.enqueue(encoder.encode(chunks[i++]));
    },
  });
}

describe("streamFollowup", () => {
  it("yields frames in order from a single chunk", async () => {
    const body =
      'event: meta\ndata: {"session_id":"s1","opinion_id":"op-1"}\n\n' +
      "event: token\ndata: hello\n\n" +
      "event: token\ndata: world\n\n" +
      'event: done\ndata: {"refused":false,"refusal_reason":null}\n\n';
    const fakeFetch = vi.fn().mockResolvedValue(
      new Response(sseBodyStream([body]), {
        status: 200,
        headers: { "content-type": "text/event-stream" },
      }),
    );
    vi.stubGlobal("fetch", fakeFetch);

    const frames: unknown[] = [];
    for await (const frame of streamFollowup("op-1", { question: "why?" })) {
      frames.push(frame);
    }
    expect(frames).toEqual([
      { kind: "meta", data: { session_id: "s1", opinion_id: "op-1" } },
      { kind: "token", data: "hello" },
      { kind: "token", data: "world" },
      { kind: "done", data: { refused: false, refusal_reason: null } },
    ]);
  });

  it("handles partial frames split across chunks", async () => {
    const full =
      'event: meta\ndata: {"session_id":"s1","opinion_id":"op-1"}\n\n' +
      "event: token\ndata: hello\n\n" +
      'event: done\ndata: {"refused":false,"refusal_reason":null}\n\n';
    // Split mid-frame so the buffer must stitch it together.
    const cut = Math.floor(full.length / 2);
    const chunk1 = full.slice(0, cut);
    const chunk2 = full.slice(cut);

    const fakeFetch = vi.fn().mockResolvedValue(
      new Response(sseBodyStream([chunk1, chunk2]), {
        status: 200,
        headers: { "content-type": "text/event-stream" },
      }),
    );
    vi.stubGlobal("fetch", fakeFetch);

    const kinds: string[] = [];
    for await (const frame of streamFollowup("op-1", { question: "why?" })) {
      kinds.push(frame.kind);
    }
    expect(kinds).toEqual(["meta", "token", "done"]);
  });
});
