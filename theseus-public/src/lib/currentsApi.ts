import type {
  PublicCitation,
  PublicFollowupMessage,
  PublicOpinion,
  PublicSource,
  PaginatedOpinions,
} from "./currentsTypes";

const API = process.env.NEXT_PUBLIC_CURRENTS_PROXY_BASE ?? "/api/currents";

export async function listCurrents(
  params: {
    cursor?: string;
    limit?: number;
    topic?: string;
    stance?: string;
    since?: string;
  } = {},
): Promise<PaginatedOpinions> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v != null) qs.set(k, String(v));
  }
  const url = `${API}${qs.toString() ? `?${qs}` : ""}`;
  const resp = await fetch(url, { cache: "no-store" });
  if (!resp.ok) throw new Error(`listCurrents ${resp.status}`);
  return resp.json();
}

export async function getCurrent(id: string): Promise<PublicOpinion> {
  const resp = await fetch(`${API}/${encodeURIComponent(id)}`, {
    cache: "no-store",
  });
  if (!resp.ok) throw new Error(`getCurrent ${resp.status}`);
  return resp.json();
}

export async function getSources(id: string): Promise<PublicSource[]> {
  const resp = await fetch(`${API}/${encodeURIComponent(id)}/sources`, {
    cache: "no-store",
  });
  if (!resp.ok) throw new Error(`getSources ${resp.status}`);
  return resp.json();
}

export async function listFollowupMessages(
  id: string,
  session: string,
): Promise<PublicFollowupMessage[]> {
  const resp = await fetch(
    `${API}/${encodeURIComponent(id)}/follow-up/${encodeURIComponent(session)}/messages`,
    { cache: "no-store" },
  );
  if (!resp.ok) throw new Error(`listFollowupMessages ${resp.status}`);
  return resp.json();
}

export function openCurrentsStream(
  onOpinion: (op: PublicOpinion) => void,
  onError: (err: unknown) => void,
): () => void {
  const es = new EventSource(`${API}/stream`);
  es.addEventListener("opinion", (ev: MessageEvent) => {
    try {
      onOpinion(JSON.parse(ev.data));
    } catch (e) {
      onError(e);
    }
  });
  es.addEventListener("heartbeat", () => {
    /* keep-alive */
  });
  es.onerror = onError;
  return () => es.close();
}

export type StreamFrame =
  | { kind: "meta"; data: { session_id: string; opinion_id: string } }
  | { kind: "token"; data: string }
  | { kind: "citation"; data: PublicCitation }
  | { kind: "done"; data: { refused: boolean; refusal_reason: string | null } }
  | { kind: "error"; data: { error: string; reason?: string } };

export async function* streamFollowup(
  id: string,
  body: { question: string; session_id?: string },
): AsyncGenerator<StreamFrame> {
  const resp = await fetch(`${API}/${encodeURIComponent(id)}/follow-up`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      accept: "text/event-stream",
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const err = new Error(`streamFollowup ${resp.status}`) as Error & {
      status?: number;
    };
    err.status = resp.status;
    throw err;
  }
  if (!resp.body) throw new Error("no response body");
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) return;
    buf += decoder.decode(value, { stream: true });
    let sepIdx: number;
    while ((sepIdx = buf.indexOf("\n\n")) !== -1) {
      const raw = buf.slice(0, sepIdx);
      buf = buf.slice(sepIdx + 2);
      const frame = parseSseFrame(raw);
      if (frame) yield frame;
    }
  }
}

export function parseSseFrame(raw: string): StreamFrame | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event: ")) event = line.slice(7).trim();
    else if (line.startsWith("data: ")) dataLines.push(line.slice(6));
  }
  const dataStr = dataLines.join("\n");
  if (!dataStr && event !== "done") return null;
  let data: unknown = dataStr;
  try {
    data = JSON.parse(dataStr);
  } catch {
    /* keep raw string */
  }
  switch (event) {
    case "meta":
      return {
        kind: "meta",
        data: data as { session_id: string; opinion_id: string },
      };
    case "token":
      return {
        kind: "token",
        data: typeof data === "string" ? data : dataStr,
      };
    case "citation":
      return { kind: "citation", data: data as PublicCitation };
    case "done":
      return {
        kind: "done",
        data:
          (data as { refused: boolean; refusal_reason: string | null }) ?? {
            refused: false,
            refusal_reason: null,
          },
      };
    case "error":
      return {
        kind: "error",
        data: data as { error: string; reason?: string },
      };
    default:
      return null;
  }
}
