import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { computeProjection } from "@/lib/embeddingAxes";
import {
  activeEmbeddingModelName,
  conclusionEmbeddingRows,
  decodeFloat32Vector,
  embeddedConclusionCount,
} from "@/lib/embeddingHealth";
import { requireTenantContext } from "@/lib/tenant";

export async function GET() {
  const tenant = await requireTenantContext();
  if (!tenant) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const modelName = await activeEmbeddingModelName();
  const [totalCount, embeddedCount, embeddingRows] = await Promise.all([
    db.conclusion.count({ where: { organizationId: tenant.organizationId } }),
    embeddedConclusionCount(tenant.organizationId, modelName),
    conclusionEmbeddingRows(tenant.organizationId, modelName),
  ]);

  const conclusions = embeddingRows
    .map((row) => {
      const vector = decodeFloat32Vector(row.vector, row.dimension);
      if (vector.length === 0) return null;
      return {
        id: row.id,
        text: row.text,
        topicHint: row.topicHint || "",
        confidenceTier: row.confidenceTier,
        embeddingJson: JSON.stringify(vector),
      };
    })
    .filter((row): row is NonNullable<typeof row> => row !== null);

  if (conclusions.length < 3) {
    return NextResponse.json({
      conclusions: [],
      axes: [],
      error: null,
      status: "warming-up",
      embeddedCount,
      totalCount,
    });
  }

  const projection = computeProjection(conclusions);
  if (projection.conclusions.length < 3) {
    return NextResponse.json({
      conclusions: [],
      axes: [],
      error: null,
      status: "warming-up",
      embeddedCount,
      totalCount,
    });
  }
  return NextResponse.json({
    ...projection,
    error: null,
    status: "ready",
    embeddedCount,
    totalCount,
  });
}
