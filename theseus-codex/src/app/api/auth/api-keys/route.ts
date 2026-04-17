import { NextResponse } from "next/server";
import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";
import { generateApiKeyPlaintext } from "@/lib/apiKeyAuth";

/**
 * GET  /api/auth/api-keys         → list non-revoked keys for the current founder
 *   Response: [{ id, label, prefix, createdAt, lastUsedAt }]
 *
 * POST /api/auth/api-keys         → mint a new key
 *   Body: { label: string }       (human label shown in the UI — e.g. "Dialectic on laptop")
 *   Response: { id, plaintext, prefix, label, createdAt }
 *   The `plaintext` field is returned ONCE and never again. Copy it immediately.
 *
 * DELETE /api/auth/api-keys?id=   → revoke (soft-delete) a key
 *
 * All three handlers require a cookie session (intentionally — you shouldn't
 * use an API key to mint more API keys).
 */
export async function GET() {
  const founder = await getFounder();
  if (!founder) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }
  const keys = await db.apiKey.findMany({
    where: { founderId: founder.id, revokedAt: null },
    select: {
      id: true,
      label: true,
      prefix: true,
      createdAt: true,
      lastUsedAt: true,
      scopes: true,
    },
    orderBy: { createdAt: "desc" },
  });
  return NextResponse.json(keys);
}

export async function POST(req: Request) {
  const founder = await getFounder();
  if (!founder) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }
  let body: { label?: string; scopes?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }
  const label = (body.label || "").trim();
  if (!label) {
    return NextResponse.json(
      { error: "`label` is required (e.g. \"Dialectic on laptop\")" },
      { status: 400 },
    );
  }

  const { plaintext, prefix, keyHash } = await generateApiKeyPlaintext();
  const key = await db.apiKey.create({
    data: {
      organizationId: founder.organizationId,
      founderId: founder.id,
      label,
      prefix,
      keyHash,
      scopes: body.scopes || "",
    },
    select: { id: true, label: true, prefix: true, createdAt: true },
  });

  await db.auditEvent.create({
    data: {
      organizationId: founder.organizationId,
      founderId: founder.id,
      action: "api_key.create",
      detail: `Minted API key '${label}' (${prefix}…)`,
    },
  });

  return NextResponse.json({ ...key, plaintext });
}

export async function DELETE(req: Request) {
  const founder = await getFounder();
  if (!founder) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }
  const url = new URL(req.url);
  const id = url.searchParams.get("id");
  if (!id) {
    return NextResponse.json({ error: "`id` query param is required" }, { status: 400 });
  }
  const key = await db.apiKey.findFirst({
    where: { id, founderId: founder.id, revokedAt: null },
  });
  if (!key) {
    return NextResponse.json({ error: "Key not found" }, { status: 404 });
  }
  await db.apiKey.update({
    where: { id: key.id },
    data: { revokedAt: new Date() },
  });
  await db.auditEvent.create({
    data: {
      organizationId: founder.organizationId,
      founderId: founder.id,
      action: "api_key.revoke",
      detail: `Revoked API key '${key.label}' (${key.prefix}…)`,
    },
  });
  return NextResponse.json({ ok: true });
}
