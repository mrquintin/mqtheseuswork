import { NextResponse } from "next/server";

import { getFounder } from "@/lib/auth";
import { buildPublicExportBundle } from "@/lib/publicationService";

export async function GET() {
  const founder = await getFounder();
  if (!founder) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const bundle = await buildPublicExportBundle(founder.organizationId);
  return NextResponse.json(bundle);
}
