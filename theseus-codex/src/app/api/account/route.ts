import { NextResponse } from "next/server";
import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";
import {
  founderDisplayName,
  validateDisplayNameInput,
} from "@/lib/founderDisplay";
import { sanitizeAndCap } from "@/lib/sanitizeText";

export async function PATCH(req: Request) {
  const founder = await getFounder();
  if (!founder) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const body = (await req.json().catch(() => ({}))) as {
    displayName?: unknown;
    roleTitle?: unknown;
    publicUrl?: unknown;
    bio?: unknown;
  };

  const displayName = validateDisplayNameInput(body.displayName);
  if (!displayName.ok) {
    return NextResponse.json({ error: displayName.error }, { status: 400 });
  }

  if (body.bio != null && typeof body.bio !== "string") {
    return NextResponse.json({ error: "Bio must be text." }, { status: 400 });
  }
  const roleTitle = validateOptionalShortText(
    body.roleTitle,
    80,
    "Public role title",
  );
  if (!roleTitle.ok) {
    return NextResponse.json({ error: roleTitle.error }, { status: 400 });
  }

  const publicUrl = validateOptionalPublicUrl(body.publicUrl);
  if (!publicUrl.ok) {
    return NextResponse.json({ error: publicUrl.error }, { status: 400 });
  }

  const bio = typeof body.bio === "string" ? body.bio : "";
  if (bio.length > 500) {
    return NextResponse.json(
      { error: "Bio must be 500 characters or fewer." },
      { status: 400 },
    );
  }

  const updated = await db.founder.update({
    where: { id: founder.id },
    data: {
      displayName: displayName.value,
      roleTitle: roleTitle.value,
      publicUrl: publicUrl.value,
      bio: sanitizeAndCap(bio, 500),
    },
    select: {
      id: true,
      email: true,
      username: true,
      name: true,
      displayName: true,
      roleTitle: true,
      publicUrl: true,
      bio: true,
    },
  });

  return NextResponse.json({
    ok: true,
    founder: {
      ...updated,
      publicName: founderDisplayName(updated),
    },
  });
}

function validateOptionalShortText(
  value: unknown,
  maxLength: number,
  label: string,
): { ok: true; value: string | null } | { ok: false; error: string } {
  if (value == null) return { ok: true, value: null };
  if (typeof value !== "string") {
    return { ok: false, error: `${label} must be text.` };
  }
  const trimmed = sanitizeAndCap(value, maxLength + 1).trim();
  if (trimmed.length > maxLength) {
    return {
      ok: false,
      error: `${label} must be ${maxLength} characters or fewer.`,
    };
  }
  return { ok: true, value: trimmed || null };
}

function validateOptionalPublicUrl(
  value: unknown,
): { ok: true; value: string | null } | { ok: false; error: string } {
  if (value == null) return { ok: true, value: null };
  if (typeof value !== "string") {
    return { ok: false, error: "Public link must be text." };
  }
  const trimmed = sanitizeAndCap(value, 2049).trim();
  if (!trimmed) return { ok: true, value: null };
  if (trimmed.length > 2048) {
    return {
      ok: false,
      error: "Public link must be 2048 characters or fewer.",
    };
  }

  try {
    const url = new URL(trimmed);
    if (url.protocol !== "https:" && url.protocol !== "http:") {
      return { ok: false, error: "Public link must use http or https." };
    }
    return { ok: true, value: url.toString() };
  } catch {
    return { ok: false, error: "Public link must be a valid URL." };
  }
}
