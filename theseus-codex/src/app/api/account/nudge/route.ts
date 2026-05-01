import { NextResponse } from "next/server";
import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";

export async function PATCH() {
  const founder = await getFounder();
  if (!founder) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const dismissedAt = new Date();
  await db.founder.update({
    where: { id: founder.id },
    data: { accountNudgeDismissedAt: dismissedAt },
    select: { id: true },
  });

  return NextResponse.json({
    ok: true,
    accountNudgeDismissedAt: dismissedAt.toISOString(),
  });
}
