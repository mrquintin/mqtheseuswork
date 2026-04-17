/**
 * Background ingestion: local dev runs `processUpload` in-process; cloud mode
 * enqueues to Redis for the Noosphere worker (`python -m noosphere.worker_main`).
 */

import { processUpload } from "@/lib/ingest";

export async function enqueueIngestJob(uploadId: string): Promise<void> {
  const redisUrl = process.env.REDIS_URL;
  if (redisUrl && process.env.USE_JOB_QUEUE === "1") {
    const { default: Redis } = await import("ioredis");
    const client = new Redis(redisUrl, { maxRetriesPerRequest: 1, lazyConnect: false });
    try {
      await client.lpush(
        process.env.NOOSPHERE_JOB_QUEUE_KEY || "noosphere:jobs",
        JSON.stringify({ type: "ingest_upload", uploadId }),
      );
    } finally {
      client.disconnect();
    }
    return;
  }
  await processUpload(uploadId);
}
