import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { computeProjection } from "@/lib/embeddingAxes";
import { requireTenantContext } from "@/lib/tenant";

export async function GET() {
  const tenant = await requireTenantContext();
  if (!tenant) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const conclusions = await db.conclusion.findMany({
    where: {
      organizationId: tenant.organizationId,
      embeddingJson: { not: null },
    },
    select: {
      id: true,
      text: true,
      topicHint: true,
      confidenceTier: true,
      embeddingJson: true,
    },
    take: 2000,
  });

  if (conclusions.length < 3) {
    return NextResponse.json({
      conclusions: [],
      axes: [],
      error:
        "Need at least 3 conclusions with embeddings for a projection. " +
        "Run the ingestion pipeline with the embedding bridge enabled to populate embeddings.",
    });
  }

  const projection = computeProjection(conclusions);
  return NextResponse.json(projection);
}
