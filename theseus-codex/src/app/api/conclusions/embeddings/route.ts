import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { computeProjection } from "@/lib/embeddingAxes";
import {
  activeEmbeddingModelName,
  conclusionJsonEmbeddingRows,
  conclusionEmbeddingRows,
  decodeFloat32Vector,
  embeddedConclusionCount,
} from "@/lib/embeddingHealth";
import { canWrite } from "@/lib/roles";
import { requireTenantContext } from "@/lib/tenant";

export async function GET() {
  const tenant = await requireTenantContext();
  if (!tenant) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  // The Explorer's "rebuild index" affordance is a write-class action;
  // surface whether this caller may use it so the client can gate the
  // button without a second round-trip. The API itself re-checks.
  const canRebuild = canWrite(tenant.role);

  const modelName = await activeEmbeddingModelName();
  const [totalCount, storedEmbeddedCount, embeddingRows, jsonEmbeddingRows] = await Promise.all([
    db.conclusion.count({ where: { organizationId: tenant.organizationId } }),
    embeddedConclusionCount(tenant.organizationId, modelName),
    conclusionEmbeddingRows(tenant.organizationId, modelName),
    conclusionJsonEmbeddingRows(tenant.organizationId),
  ]);

  let conclusions = embeddingRows
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
  const jsonConclusionCount = jsonEmbeddingRows.length;
  const embeddedCount = Math.max(storedEmbeddedCount, jsonConclusionCount);

  if (conclusions.length < 3 && jsonEmbeddingRows.length >= 3) {
    conclusions = jsonEmbeddingRows
      .filter((row): row is typeof row & { embeddingJson: string } => Boolean(row.embeddingJson))
      .map((row) => ({
        id: row.id,
        text: row.text,
        topicHint: row.topicHint || "",
        confidenceTier: row.confidenceTier,
        embeddingJson: row.embeddingJson,
      }));
  }

  if (conclusions.length < 3) {
    return NextResponse.json({
      conclusions: [],
      axes: [],
      error: null,
      status: "warming-up",
      embeddedCount,
      totalCount,
      canRebuild,
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
      canRebuild,
    });
  }
  return NextResponse.json({
    ...projection,
    error: null,
    status: "ready",
    embeddedCount,
    totalCount,
    canRebuild,
  });
}
