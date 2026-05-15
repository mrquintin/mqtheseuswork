/**
 * Client-side span emitter for the Codex frontend.
 *
 * The Python pipeline (noosphere) traces every method invocation, cascade
 * traversal, and external API call under a shared `traceId`. This module
 * is the browser-side counterpart: it emits page-load and API-call spans
 * and — crucially — propagates the trace id across the Next.js → noosphere
 * boundary so a single trace covers "user clicked → API route → pipeline".
 *
 * Design constraints (see prompt 44 follow-up):
 *   - No dependencies, no React. Pure TS so it stays well under the 5KB
 *     gzipped budget and can be imported from anywhere (RSC-safe: every
 *     entry point is a no-op when `window` is absent).
 *   - Privacy: spans carry structural metadata only — span name, URL
 *     *pathname* (never query strings), HTTP method, status, duration.
 *     No request/response bodies, no user utterances, no headers.
 *   - Best-effort delivery: spans buffer in memory and flush via
 *     `sendBeacon` on page-hide. A failed flush is swallowed — telemetry
 *     must never break the page.
 *
 * Boundary propagation: `tracedFetch` injects `X-Theseus-Trace-Id` and
 * `X-Theseus-Parent-Span-Id` on same-origin requests. A noosphere-backed
 * API route reads those and calls `start_trace(trace_id=...)` so the
 * server spans nest under the same trace. If the response echoes
 * `X-Theseus-Trace-Id` back, the client span records it as
 * `linked_trace_id` so the operator dashboard can jump straight to the
 * server-side trace.
 */

export const TRACE_ID_HEADER = "X-Theseus-Trace-Id";
export const PARENT_SPAN_ID_HEADER = "X-Theseus-Parent-Span-Id";

const FLUSH_ENDPOINT = "/api/ops/client-spans";
const MAX_BUFFER = 256;

export type ClientSpanStatus = "ok" | "error";

export interface ClientSpan {
  traceId: string;
  spanId: string;
  parentSpanId: string | null;
  name: string;
  /** Epoch ms. */
  start: number;
  /** Epoch ms; null while open. */
  end: number | null;
  status: ClientSpanStatus;
  attrs: Record<string, string | number | boolean>;
  errorKind?: string;
  errorMessage?: string;
}

interface TraceContext {
  traceId: string;
  spanId: string;
}

const buffer: ClientSpan[] = [];
let contextStack: TraceContext[] = [];
let listenersInstalled = false;

function hasWindow(): boolean {
  return typeof window !== "undefined";
}

function newId(prefix: string): string {
  const rand =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID().replace(/-/g, "").slice(0, 16)
      : Math.random().toString(16).slice(2, 18).padEnd(16, "0");
  return `${prefix}_${rand}`;
}

function record(span: ClientSpan): void {
  buffer.push(span);
  if (buffer.length > MAX_BUFFER) buffer.splice(0, buffer.length - MAX_BUFFER);
}

/** Handle returned by `startClientTrace` / `startClientSpan`. */
export class SpanHandle {
  readonly span: ClientSpan;
  private ended = false;

  constructor(span: ClientSpan) {
    this.span = span;
  }

  setAttr(key: string, value: string | number | boolean): this {
    this.span.attrs[key] = value;
    return this;
  }

  setError(err: unknown): this {
    this.span.status = "error";
    if (err instanceof Error) {
      this.span.errorKind = err.name;
      this.span.errorMessage = err.message.slice(0, 300);
    } else {
      this.span.errorKind = "Error";
      this.span.errorMessage = String(err).slice(0, 300);
    }
    return this;
  }

  /** Open a child span under this one. */
  child(name: string): SpanHandle {
    return openSpan(name, { traceId: this.span.traceId, spanId: this.span.spanId });
  }

  end(): ClientSpan {
    if (this.ended) return this.span;
    this.ended = true;
    this.span.end = Date.now();
    // Pop our context frame if it's on top (sync nesting); tolerate
    // out-of-order async ends by filtering.
    contextStack = contextStack.filter((c) => c.spanId !== this.span.spanId);
    record(this.span);
    return this.span;
  }
}

function openSpan(name: string, parent: TraceContext | null): SpanHandle {
  const traceId = parent ? parent.traceId : newId("trace");
  const spanId = newId("span");
  const span: ClientSpan = {
    traceId,
    spanId,
    parentSpanId: parent ? parent.spanId : null,
    name,
    start: Date.now(),
    end: null,
    status: "ok",
    attrs: {},
  };
  contextStack.push({ traceId, spanId });
  installFlushListeners();
  return new SpanHandle(span);
}

/** Begin a new trace. Pass `traceId` to attach to one started elsewhere. */
export function startClientTrace(
  name: string,
  opts: { traceId?: string } = {},
): SpanHandle {
  const handle = openSpan(name, null);
  if (opts.traceId) {
    handle.span.traceId = opts.traceId;
    const frame = contextStack[contextStack.length - 1];
    if (frame && frame.spanId === handle.span.spanId) {
      frame.traceId = opts.traceId;
    }
  }
  return handle;
}

/** Open a child span under the current trace (or start one if none is open). */
export function startClientSpan(name: string): SpanHandle {
  const top = contextStack[contextStack.length - 1] ?? null;
  return openSpan(name, top);
}

/** The active (innermost) trace context, or null. */
export function currentContext(): TraceContext | null {
  return contextStack[contextStack.length - 1] ?? null;
}

/**
 * Emit a `page.load` span from the Navigation Timing API. Safe to call
 * once after hydration; a no-op on the server or when timing is
 * unavailable.
 */
export function recordPageLoad(routeName?: string): SpanHandle | null {
  if (!hasWindow() || typeof performance === "undefined") return null;
  const nav = performance.getEntriesByType?.(
    "navigation",
  )?.[0] as PerformanceNavigationTiming | undefined;
  const name = `page.load${routeName ? `:${routeName}` : ""}`;
  const handle = startClientTrace(name);
  if (nav) {
    handle.setAttr("dom_interactive_ms", Math.round(nav.domInteractive));
    handle.setAttr("dom_complete_ms", Math.round(nav.domComplete));
    handle.setAttr(
      "load_event_ms",
      Math.round(nav.loadEventEnd - nav.startTime),
    );
    handle.setAttr("transfer_size", nav.transferSize || 0);
    handle.setAttr("type", nav.type);
  }
  if (hasWindow()) handle.setAttr("path", window.location.pathname);
  handle.end();
  return handle;
}

function isSameOrigin(url: string): boolean {
  if (url.startsWith("/")) return true;
  if (!hasWindow()) return false;
  try {
    return new URL(url, window.location.href).origin === window.location.origin;
  } catch {
    return false;
  }
}

function pathnameOf(url: string): string {
  try {
    return new URL(url, hasWindow() ? window.location.href : "http://x").pathname;
  } catch {
    // Strip any query string defensively — never record it.
    return url.split("?")[0];
  }
}

/**
 * `fetch` wrapper that emits an `api.call` span and propagates the trace
 * id to same-origin requests. Drop-in: same signature as `fetch`.
 *
 * Only the URL *pathname* and HTTP method are recorded — never the query
 * string, headers, or body.
 */
export async function tracedFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  const url =
    typeof input === "string"
      ? input
      : input instanceof URL
        ? input.toString()
        : input.url;
  const method = (init.method || "GET").toUpperCase();
  const handle = startClientSpan(`api.call ${method} ${pathnameOf(url)}`);
  handle.setAttr("http.method", method);
  handle.setAttr("http.path", pathnameOf(url));

  const headers = new Headers(init.headers || {});
  if (isSameOrigin(url)) {
    headers.set(TRACE_ID_HEADER, handle.span.traceId);
    headers.set(PARENT_SPAN_ID_HEADER, handle.span.spanId);
    handle.setAttr("boundary_propagated", true);
  }

  try {
    const res = await fetch(input, { ...init, headers });
    handle.setAttr("http.status_code", res.status);
    if (!res.ok) {
      handle.span.status = "error";
      handle.span.errorKind = `HTTP ${res.status}`;
    }
    const linked = res.headers.get(TRACE_ID_HEADER);
    if (linked) handle.setAttr("linked_trace_id", linked);
    return res;
  } catch (err) {
    handle.setError(err);
    throw err;
  } finally {
    handle.end();
  }
}

// ── Buffer drain / flush ────────────────────────────────────────────────────

/** Snapshot the buffered spans without clearing (tests, debugging). */
export function getBufferedSpans(): ClientSpan[] {
  return buffer.slice();
}

/** Remove and return every buffered span. */
export function drainClientSpans(): ClientSpan[] {
  return buffer.splice(0, buffer.length);
}

/**
 * Ship buffered spans to the ops ingest endpoint. Best-effort: uses
 * `sendBeacon` when available (survives page unload), falls back to a
 * keepalive `fetch`. Any failure is swallowed and the spans are
 * re-buffered so a later flush can retry.
 */
export function flushClientSpans(endpoint: string = FLUSH_ENDPOINT): void {
  if (!hasWindow() || buffer.length === 0) return;
  const batch = drainClientSpans();
  const payload = JSON.stringify({ spans: batch });
  try {
    if (navigator.sendBeacon) {
      const ok = navigator.sendBeacon(
        endpoint,
        new Blob([payload], { type: "application/json" }),
      );
      if (!ok) batch.forEach(record);
      return;
    }
    void fetch(endpoint, {
      method: "POST",
      body: payload,
      headers: { "Content-Type": "application/json" },
      keepalive: true,
    }).catch(() => batch.forEach(record));
  } catch {
    batch.forEach(record);
  }
}

function installFlushListeners(): void {
  if (listenersInstalled || !hasWindow()) return;
  listenersInstalled = true;
  // `pagehide` + `visibilitychange` together cover bfcache, tab close,
  // and tab switch — the standard "last chance to flush" trio.
  window.addEventListener("pagehide", () => flushClientSpans());
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") flushClientSpans();
  });
}
