const KEY_PREFIX = "currents.followup.";
const TTL_MS = 24 * 60 * 60 * 1000;

interface StoredFollowupSession {
  session_id: string;
  expires_at: number;
}

function sessionStorageForRuntime(): Storage | null {
  try {
    if (typeof window !== "undefined" && window.sessionStorage) {
      return window.sessionStorage;
    }
    return (globalThis as { sessionStorage?: Storage }).sessionStorage ?? null;
  } catch {
    return null;
  }
}

export function followupSessionKey(opinionId: string): string {
  return `${KEY_PREFIX}${encodeURIComponent(opinionId)}`;
}

export function loadSession(opinionId: string): string | null {
  const storage = sessionStorageForRuntime();
  if (!storage) return null;

  const key = followupSessionKey(opinionId);
  const raw = storage.getItem(key);
  if (!raw) return null;

  try {
    const parsed = JSON.parse(raw) as Partial<StoredFollowupSession>;
    const sessionId = typeof parsed.session_id === "string" ? parsed.session_id.trim() : "";
    const expiresAt = Number(parsed.expires_at);

    if (!sessionId || !Number.isFinite(expiresAt)) {
      storage.removeItem(key);
      return null;
    }

    if (Date.now() >= expiresAt) {
      storage.removeItem(key);
      return null;
    }

    return sessionId;
  } catch {
    storage.removeItem(key);
    return null;
  }
}

export function saveSession(opinionId: string, sessionId: string): void {
  const storage = sessionStorageForRuntime();
  const normalizedSessionId = sessionId.trim();
  if (!storage || !normalizedSessionId) return;

  const payload: StoredFollowupSession = {
    session_id: normalizedSessionId,
    expires_at: Date.now() + TTL_MS,
  };

  storage.setItem(followupSessionKey(opinionId), JSON.stringify(payload));
}

export function clearSession(opinionId: string): void {
  const storage = sessionStorageForRuntime();
  if (!storage) return;
  storage.removeItem(followupSessionKey(opinionId));
}
