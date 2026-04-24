-- Conclusion embedding (JSON-serialized float[]). Null for legacy rows.
ALTER TABLE "Conclusion" ADD COLUMN "embeddingJson" TEXT;
