/**
 * Redis-backed ingest worker (see `docs/Operations_Manual.md` cloud section).
 *
 *   REDIS_URL=redis://localhost:6379 DATABASE_URL=... npx tsx --tsconfig tsconfig.json src/worker/dequeue-ingest.ts
 */

import Redis from "ioredis";
import { processUpload } from "@/lib/ingest";

async function main() {
  const url = process.env.REDIS_URL;
  if (!url) {
    throw new Error("REDIS_URL is required");
  }
  const key = process.env.NOOSPHERE_JOB_QUEUE_KEY || "noosphere:jobs";
  const client = new Redis(url);
  process.stderr.write(`ingest worker listening on ${key}\n`);
  for (;;) {
    const out = await client.brpop(key, 0);
    if (!out) continue;
    const raw = out[1];
    let job: { type?: string; uploadId?: string };
    try {
      job = JSON.parse(raw) as { type?: string; uploadId?: string };
    } catch {
      process.stderr.write(`skip invalid job json: ${raw.slice(0, 120)}\n`);
      continue;
    }
    if (job.type === "ingest_upload" && job.uploadId) {
      await processUpload(job.uploadId);
    }
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
