-- Round 19 prompt 11: InvestmentMemo (the canonical memo artifact).
--
-- Adds the InvestmentMemo table + two supporting enums. Mirrors the
-- noosphere-side alembic revision 020_investment_memo. Additive only.

-- 1. Enums.
CREATE TYPE "MemoStatus" AS ENUM (
    'DRAFT',
    'UNDER_REVIEW',
    'SENT',
    'ARCHIVED',
    'PUBLIC'
);

CREATE TYPE "MemoQuestionType" AS ENUM (
    'INVESTMENT_DECISION',
    'FORECAST',
    'EXPLANATORY',
    'STRATEGIC'
);

-- 2. The memo table.
CREATE TABLE "InvestmentMemo" (
    "id" TEXT NOT NULL,
    "organizationId" TEXT NOT NULL,
    "synthesizerResultId" TEXT,

    "title" TEXT NOT NULL DEFAULT '',
    "slug" TEXT NOT NULL DEFAULT '',

    "status" "MemoStatus" NOT NULL DEFAULT 'DRAFT',
    "questionType" "MemoQuestionType" NOT NULL DEFAULT 'EXPLANATORY',
    "addressee" TEXT NOT NULL DEFAULT '',

    "mdPath" TEXT,
    "pdfPath" TEXT,

    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    "sentAt" TIMESTAMP(3),
    "acknowledgedAt" TIMESTAMP(3),
    "publishedAt" TIMESTAMP(3),
    "archivedAt" TIMESTAMP(3),

    "synthesizerVersion" TEXT NOT NULL DEFAULT 'synthesizer/v1',
    "payloadJson" TEXT NOT NULL DEFAULT '{}',

    CONSTRAINT "InvestmentMemo_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "InvestmentMemo_org_status_idx"
    ON "InvestmentMemo"("organizationId", "status");

CREATE INDEX "InvestmentMemo_org_createdAt_idx"
    ON "InvestmentMemo"("organizationId", "createdAt" DESC);

CREATE INDEX "InvestmentMemo_slug_idx"
    ON "InvestmentMemo"("slug");

ALTER TABLE "InvestmentMemo"
    ADD CONSTRAINT "InvestmentMemo_organizationId_fkey"
    FOREIGN KEY ("organizationId")
    REFERENCES "Organization"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE;
