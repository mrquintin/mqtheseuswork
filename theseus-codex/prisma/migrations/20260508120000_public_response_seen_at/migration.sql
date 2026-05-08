ALTER TABLE "PublicResponse" ADD COLUMN "seenAt" TIMESTAMP(3);

CREATE INDEX "PublicResponse_seenAt_idx" ON "PublicResponse"("seenAt");
