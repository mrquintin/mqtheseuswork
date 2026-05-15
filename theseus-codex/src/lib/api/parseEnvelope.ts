import {
  type ApiErrorCode,
  type ApiFailure,
  type ApiResponse,
  type ApiSuccess,
  isApiFailure,
  isApiSuccess,
} from "./envelope";

/**
 * Client-side counterpart to `withApiHandler`. Replaces the ad-hoc
 * `response.json()` + shape probing scattered across the per-feature
 * API clients (`currentsApi.ts`, `critiquesApi.ts`, etc.).
 *
 * The returned `data` is whatever sat under `data` in the envelope. On
 * failure, throws `EnvelopeError` carrying the typed error code and the
 * server-side correlation id — useful when the user reports a bug.
 *
 * Backwards-compatibility note: while routes are mid-migration, an
 * un-enveloped 2xx body is returned as-is (cast to `T`). Once every
 * route is migrated and the alias window has elapsed, strict-mode
 * callers can pass `{ strict: true }` to refuse legacy shapes.
 */

export class EnvelopeError extends Error {
  readonly code: ApiErrorCode | "envelope_invalid" | "transport_error";
  readonly correlationId: string | null;
  readonly status: number;
  readonly details?: unknown;

  constructor(
    code: ApiErrorCode | "envelope_invalid" | "transport_error",
    message: string,
    opts: { correlationId?: string | null; status?: number; details?: unknown } = {},
  ) {
    super(message);
    this.name = "EnvelopeError";
    this.code = code;
    this.correlationId = opts.correlationId ?? null;
    this.status = opts.status ?? 0;
    this.details = opts.details;
  }
}

export type ParseEnvelopeOptions = {
  /** Refuse legacy/un-enveloped bodies even on 2xx responses. */
  strict?: boolean;
};

export async function parseEnvelope<T>(
  response: Response,
  opts: ParseEnvelopeOptions = {},
): Promise<{ data: T; meta?: ApiSuccess<T>["meta"] }> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new EnvelopeError("envelope_invalid", "Response was not valid JSON", {
      status: response.status,
    });
  }

  if (isApiSuccess<T>(body)) {
    const env = body as ApiSuccess<T>;
    return env.meta ? { data: env.data, meta: env.meta } : { data: env.data };
  }

  if (isApiFailure(body)) {
    const err = (body as ApiFailure).error;
    throw new EnvelopeError(err.code, err.message, {
      correlationId: err.correlationId,
      status: response.status,
      details: err.details,
    });
  }

  if (response.ok && !opts.strict) {
    // Pre-envelope or legacy-alias response — return the raw body.
    return { data: body as T };
  }

  throw new EnvelopeError(
    "envelope_invalid",
    `Unexpected response shape (status ${response.status})`,
    { status: response.status, details: body },
  );
}

/**
 * Lightweight variant for tests / introspection — returns the raw
 * envelope rather than unwrapping `data`.
 */
export async function readEnvelope<T>(response: Response): Promise<ApiResponse<T>> {
  const body = (await response.json()) as ApiResponse<T>;
  return body;
}
