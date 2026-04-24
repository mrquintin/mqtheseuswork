import { PrismaClient } from "@prisma/client";

import { createSqlAdapter } from "@/lib/prismaAdapter";

const globalForPrisma = globalThis as unknown as { prisma: PrismaClient };

function createClient(): PrismaClient {
  if (!process.env.DATABASE_URL) {
    throw new Error("DATABASE_URL must be set (see theseus-codex/.env.example)");
  }
  return new PrismaClient({ adapter: createSqlAdapter() });
}

export const db = globalForPrisma.prisma || createClient();

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = db;
