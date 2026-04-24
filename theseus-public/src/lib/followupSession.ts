// Persists follow-up session ids keyed by opinion id.
//
// sessionStorage is deliberate: scoped to the current browser tab and cleared
// when the tab closes. The server also enforces a 24h TTL on session rows, so
// anything more persistent would lie about durability.

const PREFIX = "theseus.followup.session.";

export function loadSessionId(opinionId: string): string | null {
  if (typeof sessionStorage === "undefined") return null;
  try {
    return sessionStorage.getItem(PREFIX + opinionId);
  } catch {
    return null;
  }
}

export function saveSessionId(opinionId: string, sessionId: string): void {
  if (typeof sessionStorage === "undefined") return;
  try {
    sessionStorage.setItem(PREFIX + opinionId, sessionId);
  } catch {
    /* quota or denied — silent */
  }
}

export function clearSessionId(opinionId: string): void {
  if (typeof sessionStorage === "undefined") return;
  try {
    sessionStorage.removeItem(PREFIX + opinionId);
  } catch {
    /* silent */
  }
}
