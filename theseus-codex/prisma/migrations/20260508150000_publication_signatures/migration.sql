-- Cryptographic publication signatures (provenance trail).
-- Signatures are minted by the noosphere CLI; the web app stores and serves them.

CREATE TABLE "PublicationSignature" (
    "id" TEXT NOT NULL,
    "publishedConclusionId" TEXT NOT NULL,
    "slug" TEXT NOT NULL,
    "version" INTEGER NOT NULL,
    "canonicalHash" TEXT NOT NULL,
    "signatureHex" TEXT NOT NULL,
    "keyFingerprint" TEXT NOT NULL,
    "signedAt" TEXT NOT NULL,
    "payloadJson" TEXT NOT NULL DEFAULT '{}',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "PublicationSignature_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "PublicationSignature_publishedConclusionId_key"
    ON "PublicationSignature"("publishedConclusionId");

CREATE INDEX "PublicationSignature_slug_version_idx"
    ON "PublicationSignature"("slug", "version");

CREATE INDEX "PublicationSignature_keyFingerprint_idx"
    ON "PublicationSignature"("keyFingerprint");

ALTER TABLE "PublicationSignature"
    ADD CONSTRAINT "PublicationSignature_publishedConclusionId_fkey"
    FOREIGN KEY ("publishedConclusionId")
    REFERENCES "PublishedConclusion"("id") ON DELETE CASCADE ON UPDATE CASCADE;
