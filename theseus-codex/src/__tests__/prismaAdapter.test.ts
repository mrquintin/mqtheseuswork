import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { PrismaPgMock } = vi.hoisted(() => ({
  PrismaPgMock: vi.fn(),
}));

vi.mock("@prisma/adapter-pg", () => ({
  PrismaPg: PrismaPgMock,
}));

describe("createSqlAdapter", () => {
  beforeEach(() => {
    vi.resetModules();
    PrismaPgMock.mockClear();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("uses one pg connection per serverless/pooler instance by default", async () => {
    vi.stubEnv(
      "DATABASE_URL",
      "postgresql://postgres.ref:secret@aws-0-us-west-2.pooler.supabase.com:6543/postgres?pgbouncer=true",
    );

    const { createSqlAdapter } = await import("@/lib/prismaAdapter");
    createSqlAdapter();

    expect(PrismaPgMock).toHaveBeenCalledWith({
      connectionString:
        "postgresql://postgres.ref:secret@aws-0-us-west-2.pooler.supabase.com:6543/postgres?pgbouncer=true",
      max: 1,
    });
  });

  it("honors an explicit pool max override", async () => {
    vi.stubEnv("DATABASE_URL", "postgresql://theseus:theseus@localhost:5432/theseus");
    vi.stubEnv("DATABASE_POOL_MAX", "3");

    const { createSqlAdapter } = await import("@/lib/prismaAdapter");
    createSqlAdapter();

    expect(PrismaPgMock).toHaveBeenCalledWith({
      connectionString: "postgresql://theseus:theseus@localhost:5432/theseus",
      max: 3,
    });
  });

  it("keeps local non-pooler Postgres on pg defaults unless configured", async () => {
    vi.stubEnv("DATABASE_URL", "postgresql://theseus:theseus@localhost:5432/theseus");

    const { createSqlAdapter } = await import("@/lib/prismaAdapter");
    createSqlAdapter();

    expect(PrismaPgMock).toHaveBeenCalledWith({
      connectionString: "postgresql://theseus:theseus@localhost:5432/theseus",
    });
  });
});
