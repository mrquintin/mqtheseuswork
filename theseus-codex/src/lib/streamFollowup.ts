type FollowupKind = "meta" | "token" | "citation" | "done";

export interface FollowupStreamEvent {
  kind: FollowupKind;
  payload: any;
}

export class FollowupStreamError extends Error {
  status: number | null;
  retryAfter: string | null;
  payload: unknown;

  constructor(
    message: string,
    options: {
      status?: number | null;
      retryAfter?: string | null;
      payload?: unknown;
    } = {},
  ) {
    super(message);
    this.name = "FollowupStreamError";
    this.status = options.status ?? null;
    this.retryAfter = options.retryAfter ?? null;
    this.payload = options.payload;
  }
}

function requestBody(question: string, sessionId: string | null): string {
  const payload: { question: string; session_id?: string } = { question };
  if (sessionId) payload.session_id = sessionId;
  return JSON.stringify(payload);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isFollowupKind(value: unknown): value is FollowupKind {
  return value === "meta" || value === "token" || value === "citation" || value === "done";
}

function payloadMessage(payload: unknown): string | null {
  if (!isRecord(payload)) return null;
  const detail = payload.detail;
  if (typeof detail === "string") return detail;
  if (isRecord(detail)) {
    const reason = detail.reason;
    if (typeof reason === "string") return reason;
  }
  const reason = payload.reason;
  if (typeof reason === "string") return reason;
  const error = payload.error;
  if (typeof error === "string") return error;
  return null;
}

function retryAfterFromPayload(payload: unknown): string | null {
  if (!isRecord(payload)) return null;
  const detail = payload.detail;
  if (isRecord(detail)) {
    const retry = detail.retry_after_s ?? detail.retry_after;
    if (typeof retry === "string" || typeof retry === "number") return String(retry);
  }
  const retry = payload.retry_after_s ?? payload.retry_after;
  if (typeof retry === "string" || typeof retry === "number") return String(retry);
  return null;
}

async function errorFromResponse(response: Response): Promise<FollowupStreamError> {
  const raw = await response.text().catch(() => "");
  let payload: unknown = raw;
  if (raw) {
    try {
      payload = JSON.parse(raw);
    } catch {
      payload = raw;
    }
  }

  const message = payloadMessage(payload) ?? `Follow-up request failed with HTTP ${response.status}`;
  return new FollowupStreamError(message, {
    status: response.status,
    retryAfter: response.headers.get("retry-after") ?? retryAfterFromPayload(payload),
    payload,
  });
}

function frameBoundary(buffer: string): { index: number; length: number } | null {
  const match = /\r?\n\r?\n/.exec(buffer);
  if (!match || match.index === undefined) return null;
  return { index: match.index, length: match[0].length };
}

function parseJsonData(data: string): unknown {
  if (!data) return {};
  try {
    return JSON.parse(data);
  } catch {
    return data;
  }
}

function parseFrame(frame: string): FollowupStreamEvent | null {
  let eventName = "message";
  const dataLines: string[] = [];

  for (const line of frame.replace(/\r\n/g, "\n").split("\n")) {
    if (!line || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);

    if (field === "event") {
      eventName = value;
    } else if (field === "data") {
      dataLines.push(value);
    }
  }

  const parsed = parseJsonData(dataLines.join("\n"));
  const kind = isRecord(parsed) && isFollowupKind(parsed.kind) ? parsed.kind : eventName;
  const payload = isRecord(parsed) && "payload" in parsed ? parsed.payload : parsed;

  if (kind === "heartbeat") return null;
  if (kind === "error") {
    throw new FollowupStreamError(payloadMessage(payload) ?? "Follow-up stream failed", {
      status: null,
      retryAfter: retryAfterFromPayload(payload),
      payload,
    });
  }
  if (!isFollowupKind(kind)) return null;

  return { kind, payload };
}

export async function* streamFollowup(
  opinionId: string,
  question: string,
  sessionId: string | null,
): AsyncGenerator<FollowupStreamEvent> {
  const response = await fetch(`/api/currents/${encodeURIComponent(opinionId)}/follow-up`, {
    method: "POST",
    headers: {
      accept: "text/event-stream",
      "content-type": "application/json",
    },
    body: requestBody(question, sessionId),
    cache: "no-store",
  });

  if (!response.ok) {
    throw await errorFromResponse(response);
  }
  if (!response.body) {
    throw new FollowupStreamError("Follow-up response did not include a stream", {
      status: response.status,
      retryAfter: response.headers.get("retry-after"),
    });
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });

      let boundary = frameBoundary(buffer);
      while (boundary) {
        const rawFrame = buffer.slice(0, boundary.index);
        buffer = buffer.slice(boundary.index + boundary.length);
        const event = parseFrame(rawFrame);
        if (event) {
          yield event;
          if (event.kind === "done") return;
        }
        boundary = frameBoundary(buffer);
      }

      if (done) break;
    }

    const tail = buffer.trim();
    if (tail) {
      const event = parseFrame(tail);
      if (event) yield event;
    }
  } finally {
    reader.releaseLock();
  }
}
