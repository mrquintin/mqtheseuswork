-- CreateSchema
CREATE SCHEMA IF NOT EXISTS "public";

-- CreateTable
CREATE TABLE "Organization" (
    "id" TEXT NOT NULL,
    "slug" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "deletedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Organization_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Founder" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "username" TEXT NOT NULL,
    "email" TEXT NOT NULL,
    "passwordHash" TEXT NOT NULL,
    "role" TEXT NOT NULL DEFAULT 'founder',
    "bio" TEXT,
    "avatar" TEXT,
    "noosphereId" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Founder_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Session" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "founderId" TEXT NOT NULL,
    "token" TEXT NOT NULL,
    "expiresAt" TIMESTAMP(3) NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Session_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Upload" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "founderId" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "description" TEXT,
    "sourceType" TEXT NOT NULL DEFAULT 'written',
    "originalName" TEXT NOT NULL,
    "mimeType" TEXT NOT NULL,
    "filePath" TEXT NOT NULL,
    "fileSize" INTEGER NOT NULL,
    "textContent" TEXT,
    "status" TEXT NOT NULL DEFAULT 'pending',
    "processLog" TEXT NOT NULL DEFAULT '',
    "claimsCount" INTEGER,
    "methodCount" INTEGER,
    "substCount" INTEGER,
    "principleCount" INTEGER,
    "errorMessage" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Upload_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Conclusion" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "noosphereId" TEXT,
    "text" TEXT NOT NULL,
    "confidenceTier" TEXT NOT NULL,
    "rationale" TEXT NOT NULL DEFAULT '',
    "supportingPrincipleIds" TEXT NOT NULL DEFAULT '[]',
    "evidenceChainClaimIds" TEXT NOT NULL DEFAULT '[]',
    "dissentClaimIds" TEXT NOT NULL DEFAULT '[]',
    "confidence" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "topicHint" TEXT NOT NULL DEFAULT '',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "attributedFounderId" TEXT,

    CONSTRAINT "Conclusion_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "PublicationReview" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "conclusionId" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'queued',
    "checklistJson" TEXT NOT NULL DEFAULT '{}',
    "reviewerNotes" TEXT NOT NULL DEFAULT '',
    "declineReason" TEXT NOT NULL DEFAULT '',
    "revisionAsk" TEXT NOT NULL DEFAULT '',
    "reviewerFounderId" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "PublicationReview_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "PublishedConclusion" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "sourceConclusionId" TEXT NOT NULL,
    "slug" TEXT NOT NULL,
    "version" INTEGER NOT NULL DEFAULT 1,
    "discountedConfidence" DOUBLE PRECISION NOT NULL,
    "statedConfidence" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "calibrationDiscountReason" TEXT NOT NULL DEFAULT '',
    "payloadJson" TEXT NOT NULL DEFAULT '{}',
    "doi" TEXT NOT NULL DEFAULT '',
    "zenodoRecordId" TEXT NOT NULL DEFAULT '',
    "publishedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "PublishedConclusion_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "PublicResponse" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "publishedConclusionId" TEXT NOT NULL,
    "kind" TEXT NOT NULL,
    "body" TEXT NOT NULL,
    "citationUrl" TEXT NOT NULL DEFAULT '',
    "submitterEmail" TEXT NOT NULL DEFAULT '',
    "orcid" TEXT NOT NULL DEFAULT '',
    "pseudonymous" BOOLEAN NOT NULL DEFAULT false,
    "status" TEXT NOT NULL DEFAULT 'pending',
    "moderatorNote" TEXT NOT NULL DEFAULT '',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "PublicResponse_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Contradiction" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "claimAId" TEXT NOT NULL,
    "claimBId" TEXT NOT NULL,
    "severity" DOUBLE PRECISION NOT NULL,
    "sixLayerJson" TEXT,
    "narrative" TEXT NOT NULL DEFAULT '',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Contradiction_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "DriftEvent" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "noosphereId" TEXT,
    "targetId" TEXT NOT NULL,
    "targetKind" TEXT NOT NULL DEFAULT 'principle',
    "episodeId" TEXT NOT NULL DEFAULT '',
    "observedAt" TIMESTAMP(3) NOT NULL,
    "driftScore" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "notes" TEXT NOT NULL DEFAULT '',
    "claimSequenceIdsJson" TEXT NOT NULL DEFAULT '[]',
    "naturalLanguageSummary" TEXT NOT NULL DEFAULT '',
    "earliestInconsistentClaimId" TEXT NOT NULL DEFAULT '',
    "authorTopicKey" TEXT NOT NULL DEFAULT '',
    "topicId" TEXT NOT NULL DEFAULT '',

    CONSTRAINT "DriftEvent_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ResearchSuggestion" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "noosphereId" TEXT,
    "title" TEXT NOT NULL,
    "summary" TEXT NOT NULL DEFAULT '',
    "rationale" TEXT NOT NULL DEFAULT '',
    "readingUris" TEXT NOT NULL DEFAULT '[]',
    "sessionLabel" TEXT NOT NULL DEFAULT '',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "suggestedForFounderId" TEXT,

    CONSTRAINT "ResearchSuggestion_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ReviewItem" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "noosphereId" TEXT,
    "claimAId" TEXT NOT NULL,
    "claimBId" TEXT NOT NULL,
    "reason" TEXT NOT NULL DEFAULT '',
    "layerVerdictsJson" TEXT NOT NULL DEFAULT '{}',
    "severity" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "status" TEXT NOT NULL DEFAULT 'open',
    "aggregatorVerdict" TEXT,
    "priorScoresJson" TEXT,
    "humanVerdict" TEXT,
    "humanOverrule" BOOLEAN NOT NULL DEFAULT false,
    "resolutionNote" TEXT NOT NULL DEFAULT '',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "resolvedAt" TIMESTAMP(3),
    "resolvedByFounderId" TEXT,

    CONSTRAINT "ReviewItem_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "OpenQuestion" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "noosphereId" TEXT,
    "summary" TEXT NOT NULL,
    "claimAId" TEXT NOT NULL,
    "claimBId" TEXT NOT NULL,
    "unresolvedReason" TEXT NOT NULL DEFAULT '',
    "layerDisagreementSummary" TEXT NOT NULL DEFAULT '',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "OpenQuestion_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "AuditEvent" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "founderId" TEXT NOT NULL,
    "uploadId" TEXT,
    "action" TEXT NOT NULL,
    "detail" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "AuditEvent_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ApiKey" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "founderId" TEXT NOT NULL,
    "label" TEXT NOT NULL,
    "prefix" TEXT NOT NULL,
    "keyHash" TEXT NOT NULL,
    "scopes" TEXT NOT NULL DEFAULT '',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "lastUsedAt" TIMESTAMP(3),
    "revokedAt" TIMESTAMP(3),

    CONSTRAINT "ApiKey_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "Organization_slug_key" ON "Organization"("slug");

-- CreateIndex
CREATE INDEX "Founder_organizationId_idx" ON "Founder"("organizationId");

-- CreateIndex
CREATE UNIQUE INDEX "Founder_organizationId_email_key" ON "Founder"("organizationId", "email");

-- CreateIndex
CREATE UNIQUE INDEX "Founder_organizationId_username_key" ON "Founder"("organizationId", "username");

-- CreateIndex
CREATE UNIQUE INDEX "Session_token_key" ON "Session"("token");

-- CreateIndex
CREATE INDEX "Session_organizationId_idx" ON "Session"("organizationId");

-- CreateIndex
CREATE INDEX "Session_founderId_idx" ON "Session"("founderId");

-- CreateIndex
CREATE INDEX "Upload_organizationId_idx" ON "Upload"("organizationId");

-- CreateIndex
CREATE INDEX "Upload_founderId_idx" ON "Upload"("founderId");

-- CreateIndex
CREATE UNIQUE INDEX "Conclusion_noosphereId_key" ON "Conclusion"("noosphereId");

-- CreateIndex
CREATE INDEX "Conclusion_organizationId_idx" ON "Conclusion"("organizationId");

-- CreateIndex
CREATE INDEX "PublicationReview_organizationId_idx" ON "PublicationReview"("organizationId");

-- CreateIndex
CREATE INDEX "PublicationReview_conclusionId_idx" ON "PublicationReview"("conclusionId");

-- CreateIndex
CREATE INDEX "PublicationReview_status_idx" ON "PublicationReview"("status");

-- CreateIndex
CREATE INDEX "PublishedConclusion_organizationId_idx" ON "PublishedConclusion"("organizationId");

-- CreateIndex
CREATE INDEX "PublishedConclusion_slug_idx" ON "PublishedConclusion"("slug");

-- CreateIndex
CREATE UNIQUE INDEX "PublishedConclusion_slug_version_key" ON "PublishedConclusion"("slug", "version");

-- CreateIndex
CREATE INDEX "PublicResponse_organizationId_idx" ON "PublicResponse"("organizationId");

-- CreateIndex
CREATE INDEX "PublicResponse_publishedConclusionId_idx" ON "PublicResponse"("publishedConclusionId");

-- CreateIndex
CREATE INDEX "PublicResponse_status_idx" ON "PublicResponse"("status");

-- CreateIndex
CREATE INDEX "Contradiction_organizationId_idx" ON "Contradiction"("organizationId");

-- CreateIndex
CREATE UNIQUE INDEX "DriftEvent_noosphereId_key" ON "DriftEvent"("noosphereId");

-- CreateIndex
CREATE INDEX "DriftEvent_organizationId_idx" ON "DriftEvent"("organizationId");

-- CreateIndex
CREATE UNIQUE INDEX "ResearchSuggestion_noosphereId_key" ON "ResearchSuggestion"("noosphereId");

-- CreateIndex
CREATE INDEX "ResearchSuggestion_organizationId_idx" ON "ResearchSuggestion"("organizationId");

-- CreateIndex
CREATE UNIQUE INDEX "ReviewItem_noosphereId_key" ON "ReviewItem"("noosphereId");

-- CreateIndex
CREATE INDEX "ReviewItem_organizationId_idx" ON "ReviewItem"("organizationId");

-- CreateIndex
CREATE UNIQUE INDEX "OpenQuestion_noosphereId_key" ON "OpenQuestion"("noosphereId");

-- CreateIndex
CREATE INDEX "OpenQuestion_organizationId_idx" ON "OpenQuestion"("organizationId");

-- CreateIndex
CREATE INDEX "AuditEvent_organizationId_idx" ON "AuditEvent"("organizationId");

-- CreateIndex
CREATE INDEX "ApiKey_organizationId_idx" ON "ApiKey"("organizationId");

-- CreateIndex
CREATE INDEX "ApiKey_founderId_idx" ON "ApiKey"("founderId");

-- CreateIndex
CREATE INDEX "ApiKey_prefix_idx" ON "ApiKey"("prefix");

-- AddForeignKey
ALTER TABLE "Founder" ADD CONSTRAINT "Founder_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Session" ADD CONSTRAINT "Session_founderId_fkey" FOREIGN KEY ("founderId") REFERENCES "Founder"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Session" ADD CONSTRAINT "Session_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Upload" ADD CONSTRAINT "Upload_founderId_fkey" FOREIGN KEY ("founderId") REFERENCES "Founder"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Upload" ADD CONSTRAINT "Upload_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Conclusion" ADD CONSTRAINT "Conclusion_attributedFounderId_fkey" FOREIGN KEY ("attributedFounderId") REFERENCES "Founder"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Conclusion" ADD CONSTRAINT "Conclusion_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "PublicationReview" ADD CONSTRAINT "PublicationReview_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "PublicationReview" ADD CONSTRAINT "PublicationReview_conclusionId_fkey" FOREIGN KEY ("conclusionId") REFERENCES "Conclusion"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "PublicationReview" ADD CONSTRAINT "PublicationReview_reviewerFounderId_fkey" FOREIGN KEY ("reviewerFounderId") REFERENCES "Founder"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "PublishedConclusion" ADD CONSTRAINT "PublishedConclusion_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "PublicResponse" ADD CONSTRAINT "PublicResponse_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "PublicResponse" ADD CONSTRAINT "PublicResponse_publishedConclusionId_fkey" FOREIGN KEY ("publishedConclusionId") REFERENCES "PublishedConclusion"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Contradiction" ADD CONSTRAINT "Contradiction_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "DriftEvent" ADD CONSTRAINT "DriftEvent_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ResearchSuggestion" ADD CONSTRAINT "ResearchSuggestion_suggestedForFounderId_fkey" FOREIGN KEY ("suggestedForFounderId") REFERENCES "Founder"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ResearchSuggestion" ADD CONSTRAINT "ResearchSuggestion_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ReviewItem" ADD CONSTRAINT "ReviewItem_resolvedByFounderId_fkey" FOREIGN KEY ("resolvedByFounderId") REFERENCES "Founder"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ReviewItem" ADD CONSTRAINT "ReviewItem_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "OpenQuestion" ADD CONSTRAINT "OpenQuestion_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "AuditEvent" ADD CONSTRAINT "AuditEvent_founderId_fkey" FOREIGN KEY ("founderId") REFERENCES "Founder"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "AuditEvent" ADD CONSTRAINT "AuditEvent_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "AuditEvent" ADD CONSTRAINT "AuditEvent_uploadId_fkey" FOREIGN KEY ("uploadId") REFERENCES "Upload"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ApiKey" ADD CONSTRAINT "ApiKey_founderId_fkey" FOREIGN KEY ("founderId") REFERENCES "Founder"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ApiKey" ADD CONSTRAINT "ApiKey_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

