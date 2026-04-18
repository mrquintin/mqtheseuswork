/**
 * GET /api/auth/whoami
 *
 * Returns the founder + organization a credential resolves to. Used
 * by desktop apps (Dialectic) and CLIs (Noosphere) to validate stored
 * API keys at launch time — no point letting a user think they're
 * logged in if the key has been revoked.
 *
 * Auth: cookie session OR `Authorization: Bearer tcx_…` API key.
 * Unauthed → 401 with a clear message (so the CLI can instruct the
 * user to run `noosphere login` instead of guessing).
 */
import { NextResponse } from "next/server";
import { getFounderFromAuth } from "@/lib/apiKeyAuth";

export async function GET(req: Request) {
  const founder = await getFounderFromAuth(req);
  if (!founder) {
    return NextResponse.json(
      {
        error: "Not authenticated",
        hint:
          "Set Authorization: Bearer tcx_… or sign in via the browser. " +
          "CLI: run `noosphere login`. Desktop: relaunch and sign in.",
      },
      { status: 401 },
    );
  }
  // `founder` is the Prisma row + (if API-key auth) the
  // __authMethod / __apiKeyId markers. We expose the authMethod so
  // the caller can tell "session" from "api key" usage.
  const authMethod = (founder as unknown as { __authMethod?: string })
    .__authMethod || "session";

  return NextResponse.json({
    ok: true,
    founder: {
      id: founder.id,
      name: founder.name,
      username: founder.username,
      email: founder.email,
      role: founder.role,
    },
    organizationId: founder.organizationId,
    authMethod,
  });
}
