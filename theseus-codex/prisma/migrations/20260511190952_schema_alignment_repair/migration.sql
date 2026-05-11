-- CreateEnum
CREATE TYPE "SourceStandingStatus" AS ENUM ('ACTIVE', 'RETRACTED', 'CORRECTED', 'DISPUTED', 'EXPIRED');

-- CreateEnum
CREATE TYPE "CredibilityOutcome" AS ENUM ('CONFIRMATION', 'FAILURE');

-- CreateEnum
CREATE TYPE "CredibilityEventKind" AS ENUM ('FORECAST_RESOLUTION', 'RETRACTION', 'PEER_REVIEW_VERDICT', 'MANUAL_OVERRIDE');

-- CreateEnum
CREATE TYPE "CitationRelation" AS ENUM ('SUPPORTS', 'CONTRADICTS', 'QUALIFIES', 'MENTIONS');

-- CreateEnum
CREATE TYPE "CitationVerdictLabel" AS ENUM ('ENTAILS', 'CONTRADICTS', 'NEUTRAL', 'AMBIGUOUS');

-- AlterEnum
ALTER TYPE "AbstentionReason" ADD VALUE 'ABSTAIN_OFF_DOMAIN';

-- DropForeignKey
ALTER TABLE "ConclusionDeletionRequest" DROP CONSTRAINT "ConclusionDeletionRequest_requesterId_fkey";

-- DropForeignKey
ALTER TABLE "Contradiction" DROP CONSTRAINT "Contradiction_resolvedById_fkey";

-- DropForeignKey
ALTER TABLE "DashboardDismissal" DROP CONSTRAINT "DashboardDismissal_founderId_fkey";

-- DropForeignKey
ALTER TABLE "DeletionRequest" DROP CONSTRAINT "DeletionRequest_requester_fkey";

-- DropForeignKey
ALTER TABLE "DeletionRequest" DROP CONSTRAINT "DeletionRequest_upload_fkey";

-- DropForeignKey
ALTER TABLE "RecalibrationOverride" DROP CONSTRAINT "RecalibrationOverride_founderId_fkey";

-- AlterTable
ALTER TABLE "Conclusion" ADD COLUMN     "updatedAt" TIMESTAMP(3);

-- AlterTable
ALTER TABLE "DriftEvent" ADD COLUMN     "baselineBrier" DOUBLE PRECISION,
ADD COLUMN     "baselineSlope" DOUBLE PRECISION,
ADD COLUMN     "brierMean" DOUBLE PRECISION,
ADD COLUMN     "calibrationSlope" DOUBLE PRECISION,
ADD COLUMN     "directionalBias" DOUBLE PRECISION,
ADD COLUMN     "evidence" JSONB,
ADD COLUMN     "methodDomain" TEXT,
ADD COLUMN     "methodName" TEXT,
ADD COLUMN     "methodVersion" TEXT,
ADD COLUMN     "pValue" DOUBLE PRECISION,
ADD COLUMN     "sampleSize" INTEGER,
ADD COLUMN     "seed" INTEGER,
ADD COLUMN     "severity" TEXT,
ADD COLUMN     "sigma" DOUBLE PRECISION,
ADD COLUMN     "windowDays" INTEGER;

-- AlterTable
ALTER TABLE "ForecastResolution" ADD COLUMN     "source" TEXT NOT NULL DEFAULT 'VENUE',
ADD COLUMN     "sourceUrl" TEXT;

-- AlterTable
ALTER TABLE "ForecastTrace" ALTER COLUMN "updatedAt" DROP DEFAULT;

-- AlterTable
ALTER TABLE "Founder" ADD COLUMN     "dailyDigestOptIn" BOOLEAN NOT NULL DEFAULT false;

-- AlterTable
ALTER TABLE "MethodologyProfile" ALTER COLUMN "updatedAt" DROP DEFAULT;

-- AlterTable
ALTER TABLE "OpinionCitation" ADD COLUMN     "justificationMetadata" JSONB NOT NULL DEFAULT '{}';

-- AlterTable
ALTER TABLE "PublicResponse" ADD COLUMN     "publishConsent" BOOLEAN NOT NULL DEFAULT false;

-- AlterTable
ALTER TABLE "RecalibrationOverride" ALTER COLUMN "updatedAt" DROP DEFAULT;

-- AlterTable
ALTER TABLE "UploadChunk" ALTER COLUMN "updatedAt" DROP DEFAULT;

-- AlterTable
ALTER TABLE "WatchedMarket" ALTER COLUMN "updatedAt" DROP DEFAULT;

-- CreateTable
CREATE TABLE "Addendum" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "articleSlug" TEXT NOT NULL,
    "noosphereArticleId" TEXT,
    "findingId" TEXT NOT NULL DEFAULT '',
    "summary" TEXT NOT NULL,
    "body" TEXT NOT NULL DEFAULT '',
    "status" TEXT NOT NULL DEFAULT 'pending',
    "reviewerConfig" TEXT NOT NULL DEFAULT '',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "publishedAt" TIMESTAMP(3),
    "dismissedAt" TIMESTAMP(3),
    "dismissedReason" TEXT NOT NULL DEFAULT '',

    CONSTRAINT "Addendum_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "CritiqueSubmission" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "articleSlug" TEXT NOT NULL,
    "publishedConclusionId" TEXT,
    "targetClaim" TEXT NOT NULL,
    "counterEvidence" TEXT NOT NULL,
    "derivationMethod" TEXT NOT NULL,
    "citations" TEXT NOT NULL DEFAULT '',
    "submitterEmail" TEXT NOT NULL,
    "displayName" TEXT NOT NULL DEFAULT '',
    "publicUrl" TEXT NOT NULL DEFAULT '',
    "bio" TEXT NOT NULL DEFAULT '',
    "orcid" TEXT NOT NULL DEFAULT '',
    "status" TEXT NOT NULL DEFAULT 'pending',
    "moderatorNote" TEXT NOT NULL DEFAULT '',
    "severityLabel" TEXT NOT NULL DEFAULT '',
    "severityValue" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "decidedById" TEXT,
    "decidedAt" TIMESTAMP(3),
    "triggeredRevisionId" TEXT,
    "addendumId" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "CritiqueSubmission_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "CritiqueBountyPayout" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "critiqueSubmissionId" TEXT NOT NULL,
    "amountUsd" INTEGER NOT NULL DEFAULT 500,
    "payoutMode" TEXT NOT NULL DEFAULT 'self',
    "destination" TEXT NOT NULL DEFAULT '',
    "status" TEXT NOT NULL DEFAULT 'pending_founder_confirmation',
    "cancellationNote" TEXT NOT NULL DEFAULT '',
    "confirmedById" TEXT,
    "confirmedAt" TIMESTAMP(3),
    "externalRef" TEXT NOT NULL DEFAULT '',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "CritiqueBountyPayout_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "MethodologyQualityScore" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "conclusionId" TEXT NOT NULL,
    "progressivity" DOUBLE PRECISION NOT NULL,
    "severity" DOUBLE PRECISION NOT NULL,
    "aimMethodFit" DOUBLE PRECISION NOT NULL,
    "compressibility" DOUBLE PRECISION NOT NULL,
    "domainSensitivity" DOUBLE PRECISION NOT NULL,
    "composite" DOUBLE PRECISION NOT NULL,
    "evidence" JSONB NOT NULL,
    "modelName" TEXT NOT NULL DEFAULT 'stub',
    "promptVersion" TEXT NOT NULL DEFAULT 'mqs-prompt-v1.0',
    "scoredAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "MethodologyQualityScore_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ResolutionOverride" (
    "id" TEXT NOT NULL,
    "predictionId" TEXT NOT NULL,
    "outcome" "ForecastOutcome" NOT NULL,
    "resolvedAt" TIMESTAMP(3) NOT NULL,
    "reason" TEXT NOT NULL,
    "citationUrl" TEXT NOT NULL,
    "founderId" TEXT NOT NULL,
    "rawSettlement" JSONB,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ResolutionOverride_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ResolutionMismatch" (
    "id" TEXT NOT NULL,
    "predictionId" TEXT NOT NULL,
    "venue" TEXT NOT NULL,
    "venueOutcome" TEXT NOT NULL,
    "venueResolvedAt" TIMESTAMP(3),
    "venueSourceUrl" TEXT,
    "rawVenuePayload" JSONB,
    "reason" TEXT NOT NULL,
    "kind" TEXT NOT NULL,
    "reviewedAt" TIMESTAMP(3),
    "reviewedBy" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ResolutionMismatch_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ResolutionRevision" (
    "id" TEXT NOT NULL,
    "resolutionId" TEXT NOT NULL,
    "newOutcome" "ForecastOutcome" NOT NULL,
    "newResolvedAt" TIMESTAMP(3) NOT NULL,
    "reason" TEXT NOT NULL,
    "rawSettlement" JSONB,
    "source" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ResolutionRevision_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ResponseTriage" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "publicResponseId" TEXT NOT NULL,
    "label" TEXT NOT NULL,
    "manualLabel" TEXT NOT NULL DEFAULT '',
    "spamReason" TEXT NOT NULL DEFAULT '',
    "manualReason" TEXT NOT NULL DEFAULT '',
    "confidence" DOUBLE PRECISION NOT NULL,
    "impliedObjection" TEXT NOT NULL DEFAULT '',
    "rationale" TEXT NOT NULL DEFAULT '',
    "usedLlm" BOOLEAN NOT NULL DEFAULT false,
    "senderHash" TEXT NOT NULL DEFAULT '',
    "elevatedSenderFlag" BOOLEAN NOT NULL DEFAULT false,
    "severityInputsJson" TEXT NOT NULL DEFAULT '{}',
    "severityValue" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "archivedAt" TIMESTAMP(3),
    "archiveNote" TEXT NOT NULL DEFAULT '',

    CONSTRAINT "ResponseTriage_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "PublicReply" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "publicResponseId" TEXT NOT NULL,
    "founderId" TEXT NOT NULL,
    "visibility" TEXT NOT NULL DEFAULT 'private',
    "body" TEXT NOT NULL,
    "publishConfirmed" BOOLEAN NOT NULL DEFAULT false,
    "publishConfirmedAt" TIMESTAMP(3),
    "promotedToReview" BOOLEAN NOT NULL DEFAULT false,
    "triggeredRevisionId" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "PublicReply_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "RevisionEvent" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "planId" TEXT NOT NULL,
    "founderId" TEXT NOT NULL,
    "inputsJson" TEXT NOT NULL,
    "planJson" TEXT NOT NULL,
    "preConfidenceSnapshot" TEXT NOT NULL,
    "affectedConclusionIds" TEXT NOT NULL DEFAULT '[]',
    "typedConfirmation" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "revertedAt" TIMESTAMP(3),

    CONSTRAINT "RevisionEvent_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ConclusionMethod" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "conclusionId" TEXT NOT NULL,
    "methodName" TEXT NOT NULL,
    "methodVersion" TEXT NOT NULL,
    "weight" DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    "domain" TEXT NOT NULL DEFAULT '',
    "rationale" TEXT NOT NULL DEFAULT '',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "ConclusionMethod_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "MethodVersion" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "methodName" TEXT NOT NULL,
    "methodVersion" TEXT NOT NULL,
    "contentHash" TEXT NOT NULL,
    "source" TEXT NOT NULL,
    "rationale" TEXT NOT NULL,
    "failuresPublicYaml" TEXT NOT NULL DEFAULT '',
    "domainBoundJson" TEXT NOT NULL DEFAULT '',
    "capturedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "MethodVersion_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "MethodTrackRecord" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "methodName" TEXT NOT NULL,
    "methodVersion" TEXT NOT NULL,
    "domain" TEXT NOT NULL DEFAULT '',
    "sampleSize" INTEGER NOT NULL,
    "weightedBrier" DOUBLE PRECISION,
    "calibrationSlope" DOUBLE PRECISION,
    "calibrationSlopeCiLow" DOUBLE PRECISION,
    "calibrationSlopeCiHigh" DOUBLE PRECISION,
    "severityPassRate" DOUBLE PRECISION,
    "evidence" JSONB NOT NULL,
    "computedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "MethodTrackRecord_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "AnchorRevision" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "methodName" TEXT NOT NULL,
    "methodVersion" TEXT NOT NULL,
    "revisionId" TEXT NOT NULL,
    "embeddingModel" TEXT NOT NULL,
    "anchors" JSONB NOT NULL,
    "inRadius" DOUBLE PRECISION NOT NULL,
    "edgeRadius" DOUBLE PRECISION NOT NULL,
    "notes" TEXT NOT NULL DEFAULT '',
    "active" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "AnchorRevision_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "DomainBoundVerdict" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "conclusionId" TEXT NOT NULL,
    "methodName" TEXT NOT NULL,
    "methodVersion" TEXT NOT NULL,
    "status" TEXT NOT NULL,
    "margin" DOUBLE PRECISION NOT NULL,
    "reason" TEXT NOT NULL DEFAULT '',
    "anchorRevisionId" TEXT,
    "matchedTags" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "embeddingModel" TEXT,
    "evidence" JSONB,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "DomainBoundVerdict_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "SourceStanding" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "sourceId" TEXT NOT NULL,
    "status" "SourceStandingStatus" NOT NULL,
    "reason" TEXT NOT NULL DEFAULT '',
    "poller" TEXT NOT NULL,
    "noticeSourceId" TEXT,
    "rawPayload" JSONB,
    "observedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "SourceStanding_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "SourceTriageItem" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "trigger" TEXT NOT NULL DEFAULT 'standing',
    "standingId" TEXT NOT NULL DEFAULT '',
    "verdictId" TEXT NOT NULL DEFAULT '',
    "sourceId" TEXT NOT NULL,
    "conclusionId" TEXT NOT NULL,
    "status" "SourceStandingStatus" NOT NULL DEFAULT 'ACTIVE',
    "decision" TEXT NOT NULL DEFAULT 'pending',
    "decisionNote" TEXT,
    "decidedById" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "decidedAt" TIMESTAMP(3),

    CONSTRAINT "SourceTriageItem_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "SourceCredibilityUpdate" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "sourceId" TEXT NOT NULL,
    "sourceType" TEXT NOT NULL,
    "conclusionId" TEXT NOT NULL,
    "outcome" "CredibilityOutcome" NOT NULL,
    "kind" "CredibilityEventKind" NOT NULL,
    "weight" DOUBLE PRECISION NOT NULL,
    "posteriorAlpha" DOUBLE PRECISION NOT NULL,
    "posteriorBeta" DOUBLE PRECISION NOT NULL,
    "nUpdates" INTEGER NOT NULL,
    "nConfirmations" INTEGER NOT NULL,
    "nFailures" INTEGER NOT NULL,
    "note" TEXT NOT NULL DEFAULT '',
    "rawPayload" JSONB,
    "observedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "SourceCredibilityUpdate_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "CitationVerdict" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "citationKind" TEXT NOT NULL,
    "citationId" TEXT NOT NULL,
    "sourceId" TEXT NOT NULL,
    "relation" "CitationRelation" NOT NULL,
    "relationHolds" "CitationVerdictLabel" NOT NULL,
    "confidence" DOUBLE PRECISION NOT NULL,
    "excerptUsed" TEXT NOT NULL,
    "statedClaim" TEXT NOT NULL,
    "modelVersion" TEXT NOT NULL,
    "cascadeWeight" DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    "overriddenById" TEXT,
    "overrideReason" TEXT,
    "overriddenAt" TIMESTAMP(3),
    "rawPayload" JSONB,
    "computedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "CitationVerdict_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "AttentionAction" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "founderId" TEXT NOT NULL,
    "queue" TEXT NOT NULL,
    "itemId" TEXT NOT NULL,
    "action" TEXT NOT NULL,
    "snoozedUntil" TIMESTAMP(3),
    "reason" TEXT NOT NULL DEFAULT '',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "AttentionAction_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Subscriber" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "email" TEXT NOT NULL,
    "scope" TEXT NOT NULL,
    "scopeKey" TEXT NOT NULL DEFAULT '',
    "status" TEXT NOT NULL DEFAULT 'pending',
    "cadence" TEXT NOT NULL DEFAULT 'weekly',
    "confirmToken" TEXT NOT NULL DEFAULT '',
    "unsubscribeToken" TEXT NOT NULL,
    "confirmedAt" TIMESTAMP(3),
    "unsubscribedAt" TIMESTAMP(3),
    "unsubscribeReason" TEXT NOT NULL DEFAULT '',
    "lastSentAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Subscriber_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Principle" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "text" TEXT NOT NULL,
    "domainsJson" TEXT NOT NULL DEFAULT '[]',
    "clusterConclusionIds" TEXT NOT NULL DEFAULT '[]',
    "citedConclusionIds" TEXT NOT NULL DEFAULT '[]',
    "status" TEXT NOT NULL DEFAULT 'draft',
    "triageReason" TEXT NOT NULL DEFAULT '',
    "mergedIntoId" TEXT,
    "convictionScore" DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    "domainBreadth" INTEGER NOT NULL DEFAULT 0,
    "clusterCentroidSimilarity" DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    "publicVisible" BOOLEAN NOT NULL DEFAULT false,
    "driftReason" TEXT,
    "reviewedByFounderId" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    "reviewedAt" TIMESTAMP(3),
    "publishedAt" TIMESTAMP(3),

    CONSTRAINT "Principle_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Span" (
    "id" TEXT NOT NULL,
    "traceId" TEXT NOT NULL,
    "parentSpanId" TEXT,
    "name" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'ok',
    "startedAt" TIMESTAMP(3) NOT NULL,
    "endedAt" TIMESTAMP(3),
    "durationMs" DOUBLE PRECISION,
    "errorKind" TEXT,
    "errorMessage" TEXT,
    "attrs" JSONB NOT NULL DEFAULT '{}',
    "costUsd" DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    "organizationId" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Span_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "MethodMetricRollup" (
    "id" TEXT NOT NULL,
    "method" TEXT NOT NULL,
    "windowStart" TIMESTAMP(3) NOT NULL,
    "windowEnd" TIMESTAMP(3) NOT NULL,
    "count" INTEGER NOT NULL,
    "errorCount" INTEGER NOT NULL,
    "p50Ms" DOUBLE PRECISION NOT NULL,
    "p95Ms" DOUBLE PRECISION NOT NULL,
    "errorRate" DOUBLE PRECISION NOT NULL,
    "costUsd" DOUBLE PRECISION NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "MethodMetricRollup_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "AlertRule" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "metric" TEXT NOT NULL,
    "threshold" DOUBLE PRECISION NOT NULL,
    "method" TEXT NOT NULL DEFAULT '*',
    "windowMinutes" INTEGER NOT NULL DEFAULT 15,
    "minSamples" INTEGER NOT NULL DEFAULT 5,
    "webhookUrl" TEXT,
    "enabled" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "AlertRule_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "AlertEvent" (
    "id" TEXT NOT NULL,
    "ruleName" TEXT NOT NULL,
    "method" TEXT NOT NULL,
    "metric" TEXT NOT NULL,
    "value" DOUBLE PRECISION NOT NULL,
    "threshold" DOUBLE PRECISION NOT NULL,
    "firedAt" TIMESTAMP(3) NOT NULL,
    "acknowledgedAt" TIMESTAMP(3),
    "acknowledgedBy" TEXT,
    "deliveredTo" JSONB NOT NULL DEFAULT '[]',

    CONSTRAINT "AlertEvent_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "Addendum_organizationId_articleSlug_status_idx" ON "Addendum"("organizationId", "articleSlug", "status");

-- CreateIndex
CREATE INDEX "Addendum_articleSlug_status_publishedAt_idx" ON "Addendum"("articleSlug", "status", "publishedAt");

-- CreateIndex
CREATE INDEX "CritiqueSubmission_organizationId_idx" ON "CritiqueSubmission"("organizationId");

-- CreateIndex
CREATE INDEX "CritiqueSubmission_organizationId_status_idx" ON "CritiqueSubmission"("organizationId", "status");

-- CreateIndex
CREATE INDEX "CritiqueSubmission_organizationId_articleSlug_status_idx" ON "CritiqueSubmission"("organizationId", "articleSlug", "status");

-- CreateIndex
CREATE INDEX "CritiqueSubmission_severityValue_idx" ON "CritiqueSubmission"("severityValue");

-- CreateIndex
CREATE UNIQUE INDEX "CritiqueBountyPayout_critiqueSubmissionId_key" ON "CritiqueBountyPayout"("critiqueSubmissionId");

-- CreateIndex
CREATE INDEX "CritiqueBountyPayout_organizationId_idx" ON "CritiqueBountyPayout"("organizationId");

-- CreateIndex
CREATE INDEX "CritiqueBountyPayout_organizationId_status_idx" ON "CritiqueBountyPayout"("organizationId", "status");

-- CreateIndex
CREATE UNIQUE INDEX "MethodologyQualityScore_conclusionId_key" ON "MethodologyQualityScore"("conclusionId");

-- CreateIndex
CREATE INDEX "MethodologyQualityScore_organizationId_scoredAt_idx" ON "MethodologyQualityScore"("organizationId", "scoredAt");

-- CreateIndex
CREATE INDEX "MethodologyQualityScore_organizationId_composite_idx" ON "MethodologyQualityScore"("organizationId", "composite");

-- CreateIndex
CREATE UNIQUE INDEX "ResolutionOverride_predictionId_key" ON "ResolutionOverride"("predictionId");

-- CreateIndex
CREATE INDEX "ResolutionOverride_founderId_idx" ON "ResolutionOverride"("founderId");

-- CreateIndex
CREATE INDEX "ResolutionOverride_resolvedAt_idx" ON "ResolutionOverride"("resolvedAt");

-- CreateIndex
CREATE INDEX "ResolutionMismatch_predictionId_createdAt_idx" ON "ResolutionMismatch"("predictionId", "createdAt");

-- CreateIndex
CREATE INDEX "ResolutionMismatch_reviewedAt_idx" ON "ResolutionMismatch"("reviewedAt");

-- CreateIndex
CREATE INDEX "ResolutionRevision_resolutionId_createdAt_idx" ON "ResolutionRevision"("resolutionId", "createdAt");

-- CreateIndex
CREATE UNIQUE INDEX "ResponseTriage_publicResponseId_key" ON "ResponseTriage"("publicResponseId");

-- CreateIndex
CREATE INDEX "ResponseTriage_organizationId_idx" ON "ResponseTriage"("organizationId");

-- CreateIndex
CREATE INDEX "ResponseTriage_organizationId_label_idx" ON "ResponseTriage"("organizationId", "label");

-- CreateIndex
CREATE INDEX "ResponseTriage_organizationId_archivedAt_severityValue_idx" ON "ResponseTriage"("organizationId", "archivedAt", "severityValue");

-- CreateIndex
CREATE INDEX "ResponseTriage_senderHash_idx" ON "ResponseTriage"("senderHash");

-- CreateIndex
CREATE UNIQUE INDEX "PublicReply_publicResponseId_key" ON "PublicReply"("publicResponseId");

-- CreateIndex
CREATE INDEX "PublicReply_organizationId_idx" ON "PublicReply"("organizationId");

-- CreateIndex
CREATE INDEX "PublicReply_organizationId_visibility_publishConfirmed_idx" ON "PublicReply"("organizationId", "visibility", "publishConfirmed");

-- CreateIndex
CREATE INDEX "RevisionEvent_organizationId_idx" ON "RevisionEvent"("organizationId");

-- CreateIndex
CREATE INDEX "RevisionEvent_organizationId_createdAt_idx" ON "RevisionEvent"("organizationId", "createdAt");

-- CreateIndex
CREATE INDEX "RevisionEvent_planId_idx" ON "RevisionEvent"("planId");

-- CreateIndex
CREATE INDEX "ConclusionMethod_organizationId_methodName_methodVersion_idx" ON "ConclusionMethod"("organizationId", "methodName", "methodVersion");

-- CreateIndex
CREATE INDEX "ConclusionMethod_methodName_methodVersion_idx" ON "ConclusionMethod"("methodName", "methodVersion");

-- CreateIndex
CREATE UNIQUE INDEX "ConclusionMethod_conclusionId_methodName_methodVersion_key" ON "ConclusionMethod"("conclusionId", "methodName", "methodVersion");

-- CreateIndex
CREATE INDEX "MethodVersion_methodName_capturedAt_idx" ON "MethodVersion"("methodName", "capturedAt");

-- CreateIndex
CREATE INDEX "MethodVersion_organizationId_methodName_methodVersion_idx" ON "MethodVersion"("organizationId", "methodName", "methodVersion");

-- CreateIndex
CREATE UNIQUE INDEX "MethodVersion_organizationId_methodName_contentHash_key" ON "MethodVersion"("organizationId", "methodName", "contentHash");

-- CreateIndex
CREATE INDEX "MethodTrackRecord_methodName_methodVersion_idx" ON "MethodTrackRecord"("methodName", "methodVersion");

-- CreateIndex
CREATE INDEX "MethodTrackRecord_organizationId_computedAt_idx" ON "MethodTrackRecord"("organizationId", "computedAt");

-- CreateIndex
CREATE UNIQUE INDEX "MethodTrackRecord_organizationId_methodName_methodVersion_d_key" ON "MethodTrackRecord"("organizationId", "methodName", "methodVersion", "domain");

-- CreateIndex
CREATE INDEX "AnchorRevision_organizationId_methodName_methodVersion_acti_idx" ON "AnchorRevision"("organizationId", "methodName", "methodVersion", "active");

-- CreateIndex
CREATE UNIQUE INDEX "AnchorRevision_organizationId_methodName_methodVersion_revi_key" ON "AnchorRevision"("organizationId", "methodName", "methodVersion", "revisionId");

-- CreateIndex
CREATE INDEX "DomainBoundVerdict_organizationId_methodName_methodVersion_idx" ON "DomainBoundVerdict"("organizationId", "methodName", "methodVersion");

-- CreateIndex
CREATE INDEX "DomainBoundVerdict_status_idx" ON "DomainBoundVerdict"("status");

-- CreateIndex
CREATE UNIQUE INDEX "DomainBoundVerdict_conclusionId_methodName_methodVersion_key" ON "DomainBoundVerdict"("conclusionId", "methodName", "methodVersion");

-- CreateIndex
CREATE INDEX "SourceStanding_organizationId_sourceId_observedAt_idx" ON "SourceStanding"("organizationId", "sourceId", "observedAt");

-- CreateIndex
CREATE INDEX "SourceStanding_organizationId_status_observedAt_idx" ON "SourceStanding"("organizationId", "status", "observedAt");

-- CreateIndex
CREATE INDEX "SourceStanding_sourceId_idx" ON "SourceStanding"("sourceId");

-- CreateIndex
CREATE INDEX "SourceTriageItem_organizationId_decision_createdAt_idx" ON "SourceTriageItem"("organizationId", "decision", "createdAt");

-- CreateIndex
CREATE INDEX "SourceTriageItem_conclusionId_idx" ON "SourceTriageItem"("conclusionId");

-- CreateIndex
CREATE INDEX "SourceTriageItem_sourceId_idx" ON "SourceTriageItem"("sourceId");

-- CreateIndex
CREATE INDEX "SourceTriageItem_standingId_idx" ON "SourceTriageItem"("standingId");

-- CreateIndex
CREATE INDEX "SourceTriageItem_verdictId_idx" ON "SourceTriageItem"("verdictId");

-- CreateIndex
CREATE INDEX "SourceTriageItem_organizationId_trigger_decision_idx" ON "SourceTriageItem"("organizationId", "trigger", "decision");

-- CreateIndex
CREATE INDEX "SourceCredibilityUpdate_organizationId_sourceId_observedAt_idx" ON "SourceCredibilityUpdate"("organizationId", "sourceId", "observedAt");

-- CreateIndex
CREATE INDEX "SourceCredibilityUpdate_sourceId_observedAt_idx" ON "SourceCredibilityUpdate"("sourceId", "observedAt");

-- CreateIndex
CREATE INDEX "SourceCredibilityUpdate_organizationId_sourceId_conclusionI_idx" ON "SourceCredibilityUpdate"("organizationId", "sourceId", "conclusionId", "kind", "outcome");

-- CreateIndex
CREATE INDEX "SourceCredibilityUpdate_conclusionId_idx" ON "SourceCredibilityUpdate"("conclusionId");

-- CreateIndex
CREATE INDEX "CitationVerdict_organizationId_sourceId_idx" ON "CitationVerdict"("organizationId", "sourceId");

-- CreateIndex
CREATE INDEX "CitationVerdict_organizationId_citationKind_citationId_comp_idx" ON "CitationVerdict"("organizationId", "citationKind", "citationId", "computedAt");

-- CreateIndex
CREATE INDEX "CitationVerdict_organizationId_relationHolds_computedAt_idx" ON "CitationVerdict"("organizationId", "relationHolds", "computedAt");

-- CreateIndex
CREATE INDEX "CitationVerdict_sourceId_computedAt_idx" ON "CitationVerdict"("sourceId", "computedAt");

-- CreateIndex
CREATE INDEX "AttentionAction_founderId_queue_itemId_createdAt_idx" ON "AttentionAction"("founderId", "queue", "itemId", "createdAt");

-- CreateIndex
CREATE INDEX "AttentionAction_organizationId_queue_action_createdAt_idx" ON "AttentionAction"("organizationId", "queue", "action", "createdAt");

-- CreateIndex
CREATE INDEX "AttentionAction_organizationId_founderId_createdAt_idx" ON "AttentionAction"("organizationId", "founderId", "createdAt");

-- CreateIndex
CREATE UNIQUE INDEX "Subscriber_unsubscribeToken_key" ON "Subscriber"("unsubscribeToken");

-- CreateIndex
CREATE INDEX "Subscriber_organizationId_status_cadence_idx" ON "Subscriber"("organizationId", "status", "cadence");

-- CreateIndex
CREATE INDEX "Subscriber_scope_scopeKey_idx" ON "Subscriber"("scope", "scopeKey");

-- CreateIndex
CREATE UNIQUE INDEX "Subscriber_organizationId_email_scope_scopeKey_key" ON "Subscriber"("organizationId", "email", "scope", "scopeKey");

-- CreateIndex
CREATE INDEX "Principle_organizationId_idx" ON "Principle"("organizationId");

-- CreateIndex
CREATE INDEX "Principle_organizationId_status_idx" ON "Principle"("organizationId", "status");

-- CreateIndex
CREATE INDEX "Principle_organizationId_publicVisible_idx" ON "Principle"("organizationId", "publicVisible");

-- CreateIndex
CREATE INDEX "Span_traceId_idx" ON "Span"("traceId");

-- CreateIndex
CREATE INDEX "Span_name_startedAt_idx" ON "Span"("name", "startedAt");

-- CreateIndex
CREATE INDEX "Span_startedAt_idx" ON "Span"("startedAt");

-- CreateIndex
CREATE INDEX "Span_status_startedAt_idx" ON "Span"("status", "startedAt");

-- CreateIndex
CREATE INDEX "MethodMetricRollup_method_windowStart_idx" ON "MethodMetricRollup"("method", "windowStart");

-- CreateIndex
CREATE INDEX "MethodMetricRollup_windowStart_idx" ON "MethodMetricRollup"("windowStart");

-- CreateIndex
CREATE UNIQUE INDEX "MethodMetricRollup_method_windowStart_windowEnd_key" ON "MethodMetricRollup"("method", "windowStart", "windowEnd");

-- CreateIndex
CREATE UNIQUE INDEX "AlertRule_name_key" ON "AlertRule"("name");

-- CreateIndex
CREATE INDEX "AlertEvent_firedAt_idx" ON "AlertEvent"("firedAt");

-- CreateIndex
CREATE INDEX "AlertEvent_ruleName_firedAt_idx" ON "AlertEvent"("ruleName", "firedAt");

-- CreateIndex
CREATE INDEX "AlertEvent_acknowledgedAt_idx" ON "AlertEvent"("acknowledgedAt");

-- CreateIndex
CREATE INDEX "DriftEvent_organizationId_methodName_methodVersion_methodDo_idx" ON "DriftEvent"("organizationId", "methodName", "methodVersion", "methodDomain", "observedAt");

-- CreateIndex
CREATE INDEX "DriftEvent_targetKind_observedAt_idx" ON "DriftEvent"("targetKind", "observedAt");

-- AddForeignKey
ALTER TABLE "DeletionRequest" ADD CONSTRAINT "DeletionRequest_uploadId_fkey" FOREIGN KEY ("uploadId") REFERENCES "Upload"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "DeletionRequest" ADD CONSTRAINT "DeletionRequest_requesterId_fkey" FOREIGN KEY ("requesterId") REFERENCES "Founder"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Addendum" ADD CONSTRAINT "Addendum_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "CritiqueSubmission" ADD CONSTRAINT "CritiqueSubmission_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "CritiqueSubmission" ADD CONSTRAINT "CritiqueSubmission_decidedById_fkey" FOREIGN KEY ("decidedById") REFERENCES "Founder"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "CritiqueBountyPayout" ADD CONSTRAINT "CritiqueBountyPayout_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "CritiqueBountyPayout" ADD CONSTRAINT "CritiqueBountyPayout_critiqueSubmissionId_fkey" FOREIGN KEY ("critiqueSubmissionId") REFERENCES "CritiqueSubmission"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "CritiqueBountyPayout" ADD CONSTRAINT "CritiqueBountyPayout_confirmedById_fkey" FOREIGN KEY ("confirmedById") REFERENCES "Founder"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "MethodologyQualityScore" ADD CONSTRAINT "MethodologyQualityScore_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "MethodologyQualityScore" ADD CONSTRAINT "MethodologyQualityScore_conclusionId_fkey" FOREIGN KEY ("conclusionId") REFERENCES "Conclusion"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ResolutionOverride" ADD CONSTRAINT "ResolutionOverride_predictionId_fkey" FOREIGN KEY ("predictionId") REFERENCES "ForecastPrediction"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ResolutionMismatch" ADD CONSTRAINT "ResolutionMismatch_predictionId_fkey" FOREIGN KEY ("predictionId") REFERENCES "ForecastPrediction"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ResolutionRevision" ADD CONSTRAINT "ResolutionRevision_resolutionId_fkey" FOREIGN KEY ("resolutionId") REFERENCES "ForecastResolution"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ResponseTriage" ADD CONSTRAINT "ResponseTriage_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ResponseTriage" ADD CONSTRAINT "ResponseTriage_publicResponseId_fkey" FOREIGN KEY ("publicResponseId") REFERENCES "PublicResponse"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "PublicReply" ADD CONSTRAINT "PublicReply_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "PublicReply" ADD CONSTRAINT "PublicReply_publicResponseId_fkey" FOREIGN KEY ("publicResponseId") REFERENCES "PublicResponse"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "PublicReply" ADD CONSTRAINT "PublicReply_founderId_fkey" FOREIGN KEY ("founderId") REFERENCES "Founder"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Contradiction" ADD CONSTRAINT "Contradiction_resolvedById_fkey" FOREIGN KEY ("resolvedById") REFERENCES "Founder"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ConclusionDeletionRequest" ADD CONSTRAINT "ConclusionDeletionRequest_requesterId_fkey" FOREIGN KEY ("requesterId") REFERENCES "Founder"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "DashboardDismissal" ADD CONSTRAINT "DashboardDismissal_founderId_fkey" FOREIGN KEY ("founderId") REFERENCES "Founder"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "RevisionEvent" ADD CONSTRAINT "RevisionEvent_founderId_fkey" FOREIGN KEY ("founderId") REFERENCES "Founder"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "RevisionEvent" ADD CONSTRAINT "RevisionEvent_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ConclusionMethod" ADD CONSTRAINT "ConclusionMethod_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ConclusionMethod" ADD CONSTRAINT "ConclusionMethod_conclusionId_fkey" FOREIGN KEY ("conclusionId") REFERENCES "Conclusion"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "MethodVersion" ADD CONSTRAINT "MethodVersion_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "MethodTrackRecord" ADD CONSTRAINT "MethodTrackRecord_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "AnchorRevision" ADD CONSTRAINT "AnchorRevision_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "DomainBoundVerdict" ADD CONSTRAINT "DomainBoundVerdict_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "DomainBoundVerdict" ADD CONSTRAINT "DomainBoundVerdict_conclusionId_fkey" FOREIGN KEY ("conclusionId") REFERENCES "Conclusion"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "DomainBoundVerdict" ADD CONSTRAINT "DomainBoundVerdict_anchorRevisionId_fkey" FOREIGN KEY ("anchorRevisionId") REFERENCES "AnchorRevision"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "RecalibrationOverride" ADD CONSTRAINT "RecalibrationOverride_founderId_fkey" FOREIGN KEY ("founderId") REFERENCES "Founder"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "SourceStanding" ADD CONSTRAINT "SourceStanding_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "SourceTriageItem" ADD CONSTRAINT "SourceTriageItem_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "SourceCredibilityUpdate" ADD CONSTRAINT "SourceCredibilityUpdate_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "CitationVerdict" ADD CONSTRAINT "CitationVerdict_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "AttentionAction" ADD CONSTRAINT "AttentionAction_founderId_fkey" FOREIGN KEY ("founderId") REFERENCES "Founder"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "AttentionAction" ADD CONSTRAINT "AttentionAction_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Subscriber" ADD CONSTRAINT "Subscriber_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Principle" ADD CONSTRAINT "Principle_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
