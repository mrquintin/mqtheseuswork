import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import fs from "node:fs";
import path from "node:path";

import { _testing } from "@/lib/audio-recorder";

/**
 * QuickRecorder tests.
 *
 * The recorder UI itself requires a DOM + a `MediaRecorder`
 * implementation, neither of which the node-env vitest profile
 * provides. Rather than pull in jsdom + a polyfill matrix for one
 * widget, these tests cover the contract surfaces that DO matter
 * for correctness:
 *
 *   1. The recorder is mounted ONLY in the authed layout and ONLY
 *      behind a `canWrite(role)` gate. We assert this by reading
 *      the layout source — a public-side layout that accidentally
 *      imports QuickRecorder would fail the regex check.
 *
 *   2. The audio-recorder lib's codec / extension picker prefers
 *      webm/opus and falls back through ogg/mp4 cleanly. This is
 *      the cross-browser contract the founder relies on.
 *
 *   3. The VAD-style leading-silence trim does NOT clobber the
 *      container header — webm's first chunk carries codec
 *      configuration bytes, dropping it would yield an
 *      unplayable file that Whisper rejects.
 *
 *   4. The voice-memo upload path calls
 *      `/api/upload/signed/prepare` with `sourceType="voice_memo"`
 *      and `visibility="private"`, then PUTs the bytes and calls
 *      finalize. We mock fetch + XHR and assert the request
 *      bodies match the contract the noosphere voice-memo
 *      handler depends on for routing.
 */

const REPO_ROOT = path.resolve(__dirname, "..");

// ── 1. mount-gate contract ────────────────────────────────────────────────

describe("QuickRecorder mount gating", () => {
  it("authed layout renders QuickRecorder only behind canWrite(role)", () => {
    const src = fs.readFileSync(
      path.join(REPO_ROOT, "src/app/(authed)/layout.tsx"),
      "utf-8",
    );
    expect(src).toContain("QuickRecorder");
    expect(src).toContain("canWrite(founder.role)");
    // The gate must be inside the JSX, not behind a guard that
    // could be tree-shaken — assert the conditional is keyed on
    // the founder's role.
    expect(src).toMatch(/canWrite\(founder\.role\)\s*\?\s*<QuickRecorder/);
  });

  it("no public-side layout imports QuickRecorder", () => {
    // Walk the app router. Any layout file under (home), about,
    // post, ask, etc. that pulled in QuickRecorder would render
    // it to visitors — a privacy violation (mic prompt on a
    // visitor page).
    const layouts = listAllLayouts(path.join(REPO_ROOT, "src/app"));
    const publicLayouts = layouts.filter(
      (p) => !p.includes(path.join("app", "(authed)")),
    );
    expect(publicLayouts.length).toBeGreaterThan(0);
    for (const layoutPath of publicLayouts) {
      const text = fs.readFileSync(layoutPath, "utf-8");
      expect(text, `unexpected QuickRecorder import in ${layoutPath}`).not.toContain(
        "QuickRecorder",
      );
    }
  });
});

function listAllLayouts(root: string): string[] {
  const out: string[] = [];
  const stack: string[] = [root];
  while (stack.length) {
    const dir = stack.pop()!;
    let entries: fs.Dirent[];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "node_modules") continue;
        stack.push(full);
      } else if (entry.isFile() && entry.name === "layout.tsx") {
        out.push(full);
      }
    }
  }
  return out;
}

// ── 2. codec / extension picker ──────────────────────────────────────────

describe("audio-recorder codec selection", () => {
  const realIsTypeSupported =
    typeof globalThis.MediaRecorder !== "undefined"
      ? globalThis.MediaRecorder.isTypeSupported
      : undefined;

  afterEach(() => {
    if (realIsTypeSupported && typeof globalThis.MediaRecorder !== "undefined") {
      globalThis.MediaRecorder.isTypeSupported = realIsTypeSupported;
    }
  });

  it("prefers webm/opus when supported", () => {
    installFakeMediaRecorder((mime) =>
      mime.startsWith("audio/webm;codecs=opus"),
    );
    expect(_testing.pickMimeType()).toBe("audio/webm;codecs=opus");
  });

  it("falls back to mp4 on Safari-shaped support matrix", () => {
    installFakeMediaRecorder((mime) => mime.startsWith("audio/mp4"));
    expect(_testing.pickMimeType()).toBe("audio/mp4;codecs=mp4a.40.2");
  });

  it("returns null when no codec is supported", () => {
    installFakeMediaRecorder(() => false);
    expect(_testing.pickMimeType()).toBe(null);
  });

  it("maps mime types to ingestible extensions", () => {
    expect(_testing.extensionFor("audio/webm;codecs=opus")).toBe("webm");
    expect(_testing.extensionFor("audio/ogg;codecs=opus")).toBe("ogg");
    expect(_testing.extensionFor("audio/mp4;codecs=mp4a.40.2")).toBe("m4a");
    expect(_testing.extensionFor("audio/unknown")).toBe("bin");
  });
});

function installFakeMediaRecorder(predicate: (mime: string) => boolean): void {
  (globalThis as unknown as { MediaRecorder: unknown }).MediaRecorder = {
    isTypeSupported: predicate,
  };
}

// ── 3. VAD-style leading-silence trim ────────────────────────────────────

describe("audio-recorder leading-silence trim", () => {
  it("keeps the container header even when trimming a silent prefix", () => {
    const header = makeBlob(8_000, "audio/webm"); // ~8 KB container header
    const silence = makeBlob(400, "audio/webm"); // tiny — below the 1.5 KB threshold
    const speech = makeBlob(50_000, "audio/webm");
    const trimmed = _testing.trimLeadingSilence(
      [header, silence, speech],
      "audio/webm",
    );
    // Header must NOT be dropped — otherwise webm playback breaks.
    expect(trimmed).not.toBeNull();
    expect(trimmed!.size).toBeGreaterThanOrEqual(header.size + speech.size);
    expect(trimmed!.size).toBeLessThan(header.size + silence.size + speech.size);
  });

  it("returns null when the second chunk is already speech-bearing", () => {
    const header = makeBlob(8_000, "audio/webm");
    const speech = makeBlob(40_000, "audio/webm");
    expect(
      _testing.trimLeadingSilence([header, speech], "audio/webm"),
    ).toBeNull();
  });

  it("returns null when there is nothing to trim (≤ 1 chunk)", () => {
    expect(
      _testing.trimLeadingSilence([makeBlob(8_000, "audio/webm")], "audio/webm"),
    ).toBeNull();
    expect(_testing.trimLeadingSilence([], "audio/webm")).toBeNull();
  });
});

function makeBlob(byteLen: number, mime: string): Blob {
  return new Blob([new Uint8Array(byteLen)], { type: mime });
}

// ── 4. upload contract: voice memo round-trip ────────────────────────────

describe("uploadVoiceMemo contract", () => {
  let prepareCall: { url: string; body: Record<string, unknown> } | null = null;
  let finalizeCall: { url: string; body: Record<string, unknown> } | null = null;
  let putCall: { url: string; bytes: number } | null = null;

  beforeEach(() => {
    prepareCall = null;
    finalizeCall = null;
    putCall = null;
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      const body = init?.body ? JSON.parse(String(init.body)) : {};
      if (url.endsWith("/api/upload/signed/prepare")) {
        prepareCall = { url, body };
        return jsonResponse({
          uploadId: "upl_voice_test",
          signedUrl: "https://storage.example/put?token=abc",
          headers: { "Content-Type": "audio/webm" },
        });
      }
      if (url.includes("/api/upload/signed/finalize/")) {
        finalizeCall = { url, body };
        return jsonResponse({ ok: true, audioUrl: "https://cdn.example/v.webm" });
      }
      throw new Error(`unexpected fetch: ${url}`);
    }) as unknown as typeof fetch;

    (globalThis as unknown as { XMLHttpRequest: unknown }).XMLHttpRequest = class FakeXHR {
      // Minimal subset of the XHR surface the uploader uses.
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      onabort: (() => void) | null = null;
      upload = {};
      status = 200;
      responseText = "";
      _url = "";
      open(_method: string, url: string) {
        this._url = url;
      }
      setRequestHeader() {
        /* no-op */
      }
      send(body: Blob) {
        putCall = { url: this._url, bytes: body.size };
        // Settle on next tick so the caller's `await` resolves.
        queueMicrotask(() => this.onload?.());
      }
    };
  });

  afterEach(() => {
    delete (globalThis as unknown as { XMLHttpRequest?: unknown }).XMLHttpRequest;
  });

  it("posts a voice_memo, private upload with quick_capture marker", async () => {
    const { uploadVoiceMemo } = await import(
      "@/components/capture/QuickRecorder"
    );
    const blob = makeBlob(123_456, "audio/webm");
    const id = await uploadVoiceMemo({
      blob,
      mimeType: "audio/webm;codecs=opus",
      durationMs: 12_500,
      extension: "webm",
    });
    expect(id).toBe("upl_voice_test");

    // prepare contract: voice_memo provenance + private visibility +
    // quick_capture marker live where the noosphere voice-memo
    // handler can route on them.
    expect(prepareCall).not.toBeNull();
    const prep = prepareCall!.body;
    expect(prep.sourceType).toBe("voice_memo");
    expect(prep.visibility).toBe("private");
    expect(prep.publishAsPost).toBe(false);
    expect(prep.mimeType).toBe("audio/webm");
    expect(prep.size).toBe(blob.size);
    expect(prep.audioDurationSec).toBe(13);
    expect(String(prep.description ?? "")).toContain("quick_capture=true");
    expect(String(prep.filename ?? "")).toMatch(/\.webm$/);

    // PUT happened with the bytes.
    expect(putCall).not.toBeNull();
    expect(putCall!.bytes).toBe(blob.size);

    // finalize called with the assigned upload id.
    expect(finalizeCall).not.toBeNull();
    expect(finalizeCall!.url).toContain("upl_voice_test");
  });

  it("surfaces prepare errors verbatim", async () => {
    globalThis.fetch = vi.fn(async () =>
      jsonResponse({ error: "quota exceeded" }, 413),
    ) as unknown as typeof fetch;
    const { uploadVoiceMemo } = await import(
      "@/components/capture/QuickRecorder"
    );
    await expect(
      uploadVoiceMemo({
        blob: makeBlob(1024, "audio/webm"),
        mimeType: "audio/webm",
        durationMs: 1000,
        extension: "webm",
      }),
    ).rejects.toThrow(/quota exceeded/);
  });
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
