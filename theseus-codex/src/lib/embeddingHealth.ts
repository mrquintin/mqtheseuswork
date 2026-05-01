import { db } from "@/lib/db";

export type EmbeddingHealth = {
  embeddedCount: number;
  totalCount: number;
  backlog: number;
  status: "green" | "amber" | "red";
  lastBackfillFailed: boolean;
};

type CountRow = { count: number | bigint | string };
type ModelRow = { modelName: string };

export type ConclusionEmbeddingRow = {
  id: string;
  text: string;
  topicHint: string | null;
  confidenceTier: string;
  vector: unknown;
  dimension: number;
};

const EMBEDDING_BACKFILL_KEY = "embedding_backfill";
const DEFAULT_EMBEDDING_MODEL = "all-mpnet-base-v2";

function toNumber(value: number | bigint | string | null | undefined): number {
  if (typeof value === "bigint") return Number(value);
  if (typeof value === "string") return Number.parseInt(value, 10) || 0;
  return value ?? 0;
}

export function decodeFloat32Vector(value: unknown, dimension?: number): number[] {
  if (!value) return [];
  const bytes = Buffer.isBuffer(value)
    ? value
    : value instanceof Uint8Array
      ? Buffer.from(value)
      : Array.isArray(value)
        ? Buffer.from(value)
        : null;
  if (!bytes || bytes.length % 4 !== 0) return [];
  const count = dimension && dimension > 0 ? Math.min(dimension, bytes.length / 4) : bytes.length / 4;
  const out: number[] = [];
  for (let i = 0; i < count; i++) {
    out.push(bytes.readFloatLE(i * 4));
  }
  return out;
}

export async function activeEmbeddingModelName(): Promise<string> {
  try {
    const rows = await db.$queryRaw<ModelRow[]>`
      SELECT model_name AS "modelName"
      FROM embedding_model_version
      WHERE effective_from <= NOW()
      ORDER BY effective_from DESC
      LIMIT 1
    `;
    return rows[0]?.modelName || process.env.THESEUS_EMBEDDING_MODEL_NAME || DEFAULT_EMBEDDING_MODEL;
  } catch {
    return process.env.THESEUS_EMBEDDING_MODEL_NAME || DEFAULT_EMBEDDING_MODEL;
  }
}

export async function embeddedConclusionCount(
  organizationId: string,
  modelName: string,
): Promise<number> {
  try {
    const rows = await db.$queryRaw<CountRow[]>`
      SELECT COUNT(DISTINCT e.ref_claim_id)::int AS count
      FROM embedding e
      INNER JOIN "Conclusion" c ON c.id = e.ref_claim_id
      WHERE c."organizationId" = ${organizationId}
        AND e.model_name = ${modelName}
    `;
    return toNumber(rows[0]?.count);
  } catch {
    return 0;
  }
}

export async function conclusionEmbeddingRows(
  organizationId: string,
  modelName: string,
  limit = 2000,
): Promise<ConclusionEmbeddingRow[]> {
  try {
    return await db.$queryRaw<ConclusionEmbeddingRow[]>`
      SELECT c.id,
             c.text,
             c."topicHint",
             c."confidenceTier",
             e.vector,
             e.dimension
      FROM "Conclusion" c
      INNER JOIN embedding e ON e.ref_claim_id = c.id
      WHERE c."organizationId" = ${organizationId}
        AND e.model_name = ${modelName}
      ORDER BY c."createdAt" DESC
      LIMIT ${limit}
    `;
  } catch {
    return [];
  }
}

function backfillFailed(value: unknown): boolean {
  if (!value || typeof value !== "object") return false;
  const record = value as { status?: unknown; ok?: unknown; errors?: unknown };
  if (record.status === "failed") return true;
  if (record.ok === false) return true;
  return Array.isArray(record.errors) && record.errors.length > 0;
}

export async function embeddingHealth(organizationId: string): Promise<EmbeddingHealth> {
  const modelName = await activeEmbeddingModelName();
  const [totalCount, embeddedCount, backfill] = await Promise.all([
    db.conclusion.count({ where: { organizationId } }).catch(() => 0),
    embeddedConclusionCount(organizationId, modelName),
    db.operatorState
      .findUnique({
        where: {
          organizationId_key: {
            organizationId,
            key: EMBEDDING_BACKFILL_KEY,
          },
        },
        select: { value: true },
      })
      .catch(() => null),
  ]);
  const backlog = Math.max(0, totalCount - embeddedCount);
  const lastBackfillFailed = backfillFailed(backfill?.value);
  return {
    embeddedCount,
    totalCount,
    backlog,
    lastBackfillFailed,
    status: lastBackfillFailed ? "red" : backlog > 50 ? "amber" : "green",
  };
}
