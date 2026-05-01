-- Forecast portfolio traceability and ad-hoc market watchlist.
-- Live trading remains controlled exclusively by existing operator gates.

CREATE TABLE IF NOT EXISTS "ForecastTrace" (
  "id" TEXT NOT NULL,
  "predictionId" TEXT NOT NULL,
  "marketId" TEXT NOT NULL,
  "organizationId" TEXT NOT NULL,
  "marketTitle" VARCHAR(280) NOT NULL,
  "principlesUsed" JSONB NOT NULL,
  "modelOutput" JSONB NOT NULL,
  "gateResults" JSONB NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT "ForecastTrace_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "ForecastTrace_predictionId_fkey"
    FOREIGN KEY ("predictionId") REFERENCES "ForecastPrediction"("id")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "ForecastTrace_marketId_fkey"
    FOREIGN KEY ("marketId") REFERENCES "ForecastMarket"("id")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "ForecastTrace_organizationId_fkey"
    FOREIGN KEY ("organizationId") REFERENCES "Organization"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS "ForecastTrace_predictionId_key"
  ON "ForecastTrace"("predictionId");

CREATE INDEX IF NOT EXISTS "ForecastTrace_marketId_idx"
  ON "ForecastTrace"("marketId");

CREATE INDEX IF NOT EXISTS "ForecastTrace_organizationId_createdAt_idx"
  ON "ForecastTrace"("organizationId", "createdAt");

CREATE TABLE IF NOT EXISTS "WatchedMarket" (
  "id" TEXT NOT NULL,
  "organizationId" TEXT NOT NULL,
  "source" "ForecastSource" NOT NULL,
  "url" TEXT NOT NULL,
  "externalId" TEXT,
  "status" TEXT NOT NULL DEFAULT 'ACTIVE',
  "notes" TEXT,
  "lastConsideredAt" TIMESTAMP(3),
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT "WatchedMarket_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "WatchedMarket_organizationId_fkey"
    FOREIGN KEY ("organizationId") REFERENCES "Organization"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS "WatchedMarket_organizationId_url_key"
  ON "WatchedMarket"("organizationId", "url");

CREATE INDEX IF NOT EXISTS "WatchedMarket_organizationId_status_createdAt_idx"
  ON "WatchedMarket"("organizationId", "status", "createdAt");

CREATE INDEX IF NOT EXISTS "WatchedMarket_source_status_idx"
  ON "WatchedMarket"("source", "status");
