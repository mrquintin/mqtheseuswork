import path from "node:path";
import { defineConfig, env } from "prisma/config";

/** Prisma 7+ — connection URL lives here, not in schema.prisma. */
export default defineConfig({
  schema: path.join("prisma", "schema.prisma"),
  migrations: {
    path: path.join("prisma", "migrations"),
    seed: "tsx prisma/seed.ts",
  },
  datasource: {
    url: env("DATABASE_URL"),
  },
});
