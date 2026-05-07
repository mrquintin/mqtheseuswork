-- Add nullable X significance metrics captured by the Python Currents ingestor.
ALTER TABLE "CurrentEvent" ADD COLUMN "metrics" JSONB;
