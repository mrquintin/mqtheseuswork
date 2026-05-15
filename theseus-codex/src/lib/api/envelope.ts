/**
 * Unified API envelope.
 *
 * Round 17 added a fan of routes that each invented their own response
 * shape: some returned `{ data, error }`, some `{ ok, ...payload }`,
 * some raw JSON. This module defines the single envelope every new
 * Theseus API route is expected to use. See
 * `docs/architecture/API_Envelope_Contract.md` for the full contract.
 *
 * Success:  `{ ok: true, data, meta? }`
 * Failure:  `{ ok: false, error: { code, message, details?, correlationId } }`
 */

export const ENVELOPE_CONTRACT_VERSION = 1;

export type ApiErrorCode =
  | "validation_error"
  | "unauthorized"
  | "forbidden"
  | "not_found"
  | "method_not_allowed"
  | "bad_json"
  | "body_too_large"
  | "challenge_required"
  | "rate_limited"
  | "service_unavailable"
  | "internal_error";

export type ApiMeta = {
  /** Cursor for the next page; `null` when there is no next page. */
  nextCursor?: string | null;
  /** Whether more pages exist beyond the current one. */
  hasMore?: boolean;
  /**
   * Total row count, when the route can compute it cheaply. Opt-in:
   * routes that would have to issue a second expensive count query
   * should omit `total` rather than serve a stale or expensive number.
   */
  total?: number;
  /** Payload schema version. Pin against this from external consumers. */
  schemaVersion?: number;
  /** Wall-clock generation time, ISO-8601. */
  generatedAt?: string;
  /** Free-form per-route extensions. */
  [key: string]: unknown;
};

export type ApiSuccess<T> = {
  ok: true;
  data: T;
  meta?: ApiMeta;
};

export type ApiFailure = {
  ok: false;
  error: {
    code: ApiErrorCode;
    message: string;
    details?: unknown;
    correlationId: string;
  };
};

export type ApiResponse<T> = ApiSuccess<T> | ApiFailure;

const STATUS_BY_CODE: Record<ApiErrorCode, number> = {
  validation_error: 400,
  bad_json: 400,
  unauthorized: 401,
  forbidden: 403,
  not_found: 404,
  method_not_allowed: 405,
  body_too_large: 413,
  challenge_required: 428,
  rate_limited: 429,
  service_unavailable: 503,
  internal_error: 500,
};

export function statusForErrorCode(code: ApiErrorCode): number {
  return STATUS_BY_CODE[code] ?? 500;
}

/**
 * Errors thrown inside a handler that should surface as enveloped
 * failures with a specific code. Anything else thrown becomes an
 * `internal_error`.
 */
export class ApiError extends Error {
  readonly code: ApiErrorCode;
  readonly status: number;
  readonly details?: unknown;
  readonly extraHeaders?: Record<string, string>;

  constructor(
    code: ApiErrorCode,
    message: string,
    opts: { details?: unknown; status?: number; headers?: Record<string, string> } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = opts.status ?? statusForErrorCode(code);
    this.details = opts.details;
    this.extraHeaders = opts.headers;
  }
}

export function isApiSuccess<T>(body: unknown): body is ApiSuccess<T> {
  return !!body && typeof body === "object" && (body as ApiResponse<T>).ok === true;
}

export function isApiFailure(body: unknown): body is ApiFailure {
  return !!body && typeof body === "object" && (body as ApiResponse<unknown>).ok === false;
}
