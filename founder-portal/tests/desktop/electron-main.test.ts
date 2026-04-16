import { afterEach, describe, expect, it, vi } from "vitest";
import path from "path";
import fs from "fs";
import os from "os";

const fakeUserData = fs.mkdtempSync(path.join(os.tmpdir(), "founder-portal-test-"));

vi.mock("electron", () => ({
  app: {
    getPath: (key: string) => {
      if (key === "userData") return fakeUserData;
      throw new Error(`unexpected app.getPath key: ${key}`);
    },
  },
}));

const dbPathModule = await import("../../desktop/db-path");
const nextServerModule = await import("../../desktop/next-server");

afterEach(() => {
  vi.restoreAllMocks();
});

describe("db-path", () => {
  it("getDbPath returns a path ending in founder-portal.db", () => {
    const p = dbPathModule.getDbPath();
    expect(p.endsWith("founder-portal.db")).toBe(true);
    expect(fs.existsSync(path.dirname(p))).toBe(true);
  });

  it("getDatabaseUrl returns a string starting with file:", () => {
    const url = dbPathModule.getDatabaseUrl();
    expect(url.startsWith("file:")).toBe(true);
    expect(url).toContain("founder-portal.db");
  });
});

describe("next-server", () => {
  it("findFreePort returns a port in the valid TCP range", async () => {
    const port = await nextServerModule.findFreePort(3000);
    expect(typeof port).toBe("number");
    expect(port).toBeGreaterThanOrEqual(1024);
    expect(port).toBeLessThanOrEqual(65535);
  });

  it("findFreePort skips a port that is already in use", async () => {
    const net = await import("net");
    const blocker = net.createServer();
    await new Promise<void>((resolve) => blocker.listen(0, "127.0.0.1", () => resolve()));
    const addr = blocker.address();
    if (!addr || typeof addr === "string") {
      blocker.close();
      throw new Error("no port");
    }
    const busy = addr.port;
    try {
      const found = await nextServerModule.findFreePort(busy);
      expect(found).not.toBe(busy);
      expect(found).toBeGreaterThan(busy);
    } finally {
      blocker.close();
    }
  });
});
