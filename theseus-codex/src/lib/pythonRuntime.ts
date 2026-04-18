/**
 * Helpers for talking to the local Noosphere Python CLI from the Next.js
 * API routes.
 *
 * Context: the Codex web app ships in two very different runtimes.
 *
 *   - Local / Docker / self-hosted:  Node sits next to a Python interpreter
 *     and the `noosphere/` package is importable. The upload flow can
 *     legitimately run `python3 -m noosphere ingest` and stream stdout back
 *     to the client.
 *   - Vercel serverless:  there is no Python binary in the Node runtime.
 *     Any `spawn("python", ...)` call fails immediately with
 *     `Error: spawn python3 ENOENT` (the exact error the user saw in the
 *     process log for the upload route).
 *
 * Rather than sprinkle try/catch blocks through every route, this module
 * exposes a single `runNoospherePython` that either:
 *   (a) returns the expected {code, out} tuple after a successful spawn, or
 *   (b) returns a synthetic "noosphere-unavailable" result with a helpful
 *       message the caller can surface to the user / save in the upload log.
 *
 * The "is Python reachable?" check is explicit rather than heuristic. We
 * check the `NOOSPHERE_PYTHON_DISABLED` env var first (set by the Vercel
 * deploy; can also be set locally for testing), then fall back to detecting
 * `VERCEL=1` (Vercel sets this automatically in every serverless invocation),
 * then attempt the spawn and catch ENOENT. That ordering means we save a
 * failed-spawn round trip in the common Vercel case while still discovering
 * a missing Python on other hosts.
 */

import { spawn } from "child_process";

export interface NoosphereRunResult {
  /** Non-null when the process actually ran; null when we never spawned. */
  code: number | null;
  /** Combined stdout + stderr. On graceful-skip this holds the explanatory message. */
  out: string;
  /** True if we tried to spawn and Python/the module wasn't available. */
  skipped: boolean;
  /** Short reason string for logs / API responses. */
  reason?: "no-python" | "disabled-by-env" | "ok";
}

/** Message shown everywhere Noosphere isn't reachable — kept in one place so it stays consistent. */
export const NOOSPHERE_UNAVAILABLE_MESSAGE =
  "Noosphere processing is not available in this deployment. The upload / " +
  "request has been saved; run `python -m noosphere ingest` (or the relevant " +
  "command) against the database locally to process it.";

/** Cheap synchronous check: can we skip the spawn entirely? */
export function isNoosphereLikelyUnavailable(): boolean {
  if (process.env.NOOSPHERE_PYTHON_DISABLED === "1") return true;
  // Vercel sets VERCEL=1 on every serverless invocation. Netlify sets
  // NETLIFY=1. Both lack Python by default; if you ever self-host one
  // with Python alongside, unset the flag via NOOSPHERE_PYTHON_DISABLED=0.
  if (process.env.VERCEL === "1" && process.env.NOOSPHERE_PYTHON_DISABLED !== "0") return true;
  if (process.env.NETLIFY === "1" && process.env.NOOSPHERE_PYTHON_DISABLED !== "0") return true;
  return false;
}

/**
 * Run `python -m noosphere <args>` (or whatever `NOOSPHERE_PYTHON` is set
 * to). Streams output via `onChunk` if provided. Resolves with a
 * `NoosphereRunResult` that's safe to act on even when Python is unavailable.
 */
export function runNoospherePython(
  args: string[],
  opts: {
    cwd?: string;
    envExtra?: Record<string, string>;
    onChunk?: (s: string) => void | Promise<void>;
  } = {},
): Promise<NoosphereRunResult> {
  const python = process.env.NOOSPHERE_PYTHON || "python3";

  if (isNoosphereLikelyUnavailable()) {
    return Promise.resolve({
      code: null,
      out: NOOSPHERE_UNAVAILABLE_MESSAGE,
      skipped: true,
      reason: "disabled-by-env",
    });
  }

  return new Promise((resolve) => {
    const env = {
      ...process.env,
      ...(opts.envExtra || {}),
      PYTHONUNBUFFERED: "1",
    };

    let proc: ReturnType<typeof spawn>;
    try {
      proc = spawn(python, args, { env, cwd: opts.cwd });
    } catch (err) {
      // `spawn` itself rarely throws synchronously; the common failure is an
      // async 'error' event below. We still guard for completeness.
      resolve({
        code: null,
        out: `${NOOSPHERE_UNAVAILABLE_MESSAGE}\n[spawn threw] ${String(err)}`,
        skipped: true,
        reason: "no-python",
      });
      return;
    }

    let out = "";
    const chunk = async (d: Buffer) => {
      const s = d.toString();
      out += s;
      if (opts.onChunk) {
        try {
          await opts.onChunk(s);
        } catch {
          // Swallow — logging the log is not load-bearing.
        }
      }
    };
    proc.stdout?.on("data", (d) => {
      void chunk(d);
    });
    proc.stderr?.on("data", (d) => {
      void chunk(d);
    });
    proc.on("close", (code) => {
      resolve({ code, out, skipped: false, reason: "ok" });
    });
    proc.on("error", (err: NodeJS.ErrnoException) => {
      // ENOENT on Vercel / container-without-python. Treat as graceful skip
      // rather than a hard failure — the caller can still mark the DB row
      // as queued-for-offline-ingest and let the user run the CLI locally.
      const enoent = err && err.code === "ENOENT";
      resolve({
        code: null,
        out: enoent
          ? `${NOOSPHERE_UNAVAILABLE_MESSAGE}\n[spawn error] ${String(err)}`
          : `[spawn error] ${String(err)}`,
        skipped: enoent,
        reason: enoent ? "no-python" : "ok",
      });
    });
  });
}

/**
 * Call `python -m noosphere <args>`, expect JSON on stdout, return a shape
 * suitable for `NextResponse.json(...)`. Condenses the ~25-line spawn/parse
 * block that was duplicated across every Round-3 route handler.
 *
 * Returns both the payload and the recommended HTTP status code so callers
 * can do `return NextResponse.json(r, { status: r.status })` without
 * branching themselves.
 */
export interface NoosphereJsonCall<T = unknown> {
  ok: boolean;
  data?: T;
  error?: string;
  /** Recommended HTTP status: 200 on success, 501 when Python unavailable, 500 on other failures. */
  status: 200 | 500 | 501;
}

export async function callNoosphereJson<T = unknown>(
  args: string[],
  failureLabel = "Noosphere command failed",
): Promise<NoosphereJsonCall<T>> {
  const res = await runNoospherePython(["-m", "noosphere", ...args]);
  if (res.skipped) {
    return { ok: false, error: NOOSPHERE_UNAVAILABLE_MESSAGE, status: 501 };
  }
  if (res.code === 0) {
    try {
      return { ok: true, data: JSON.parse(res.out) as T, status: 200 };
    } catch {
      // Some commands (e.g. docgen) print non-JSON diagnostics on success;
      // hand the raw stdout back rather than pretending it was structured.
      return { ok: true, data: res.out as unknown as T, status: 200 };
    }
  }
  return { ok: false, error: res.out.trim() || failureLabel, status: 500 };
}
