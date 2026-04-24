/**
 * Fire a GitHub `repository_dispatch` webhook so the
 * `noosphere-process-uploads.yml` workflow picks up a freshly-created
 * upload within seconds. This is the default "auto-process" path.
 *
 * Failures are *non-fatal*. If the token is missing, the target repo
 * is misconfigured, or GitHub is having a bad day, we swallow the
 * error and log it — the scheduled sweep on the same workflow will
 * catch the upload on its next 10-minute pass, so nothing gets lost.
 *
 * Required env (set on Vercel → Settings → Environment Variables):
 *
 *   GITHUB_DISPATCH_TOKEN   — a Personal Access Token (classic) with
 *                             the `repo` scope, or a fine-grained
 *                             PAT with `contents:write` on the
 *                             target repo. Without it this module
 *                             is a no-op.
 *
 *   GITHUB_DISPATCH_REPO    — "owner/repo" slug, e.g.
 *                             "mrquintin/mqtheseuswork". Defaults to
 *                             the published repo slug below so a
 *                             vanilla deploy works without config.
 *
 * The workflow itself tolerates running without this trigger — the
 * 10-minute cron gives us a belt-and-suspenders guarantee that
 * nothing stays in `queued_offline` for more than ~10 minutes.
 */

const DEFAULT_REPO = "mrquintin/mqtheseuswork";

export interface DispatchResult {
  /** True if we successfully hit GitHub's dispatch endpoint (204 No Content). */
  dispatched: boolean;
  /** Short human-readable note; fed back to the UI via processLog. */
  note: string;
  /** HTTP status code if we got a response; null on network error. */
  status: number | null;
}

/** Check env without making a network call. Useful for UI gating. */
export function isAutoProcessConfigured(): boolean {
  return Boolean(process.env.GITHUB_DISPATCH_TOKEN);
}

/**
 * POST to GitHub's repository_dispatch endpoint.
 *
 * Promise resolves with a `DispatchResult` — it never throws. The
 * caller should treat any `dispatched: false` outcome as "the cron
 * will pick it up" rather than a user-visible failure.
 */
export async function triggerNoosphereProcessing(
  uploadId: string,
  options: { organizationId?: string; withLlm?: boolean } = {},
): Promise<DispatchResult> {
  const token = process.env.GITHUB_DISPATCH_TOKEN;
  const repo = process.env.GITHUB_DISPATCH_REPO || DEFAULT_REPO;

  if (!token) {
    return {
      dispatched: false,
      note:
        "Auto-processing skipped: GITHUB_DISPATCH_TOKEN not set on Vercel. " +
        "The 10-minute cron sweep will pick this upload up on its next pass.",
      status: null,
    };
  }

  const url = `https://api.github.com/repos/${repo}/dispatches`;
  const body = {
    event_type: "process-upload",
    client_payload: {
      upload_id: uploadId,
      organization_id: options.organizationId || null,
      with_llm: options.withLlm ?? true,
      triggered_at: new Date().toISOString(),
    },
  };

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${token}`,
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
        "User-Agent": "theseus-codex/1.0 (+auto-process)",
      },
      body: JSON.stringify(body),
    });

    // GitHub returns 204 on success. Any 2xx we treat as success.
    if (response.status >= 200 && response.status < 300) {
      return {
        dispatched: true,
        note: `Auto-processing dispatched to ${repo} (HTTP ${response.status}). Results appear in /conclusions within 1–2 minutes.`,
        status: response.status,
      };
    }

    // Read the error body for diagnostics (GitHub returns JSON here).
    let errBody = "";
    try {
      const text = await response.text();
      errBody = text.slice(0, 300);
    } catch {
      errBody = "<unreadable>";
    }
    return {
      dispatched: false,
      note:
        `GitHub dispatch returned HTTP ${response.status}. ` +
        `Body: ${errBody}. ` +
        `The scheduled cron sweep will retry within 10 minutes.`,
      status: response.status,
    };
  } catch (err) {
    return {
      dispatched: false,
      note:
        `GitHub dispatch network error: ${err instanceof Error ? err.message : String(err)}. ` +
        `The scheduled cron sweep will retry within 10 minutes.`,
      status: null,
    };
  }
}
