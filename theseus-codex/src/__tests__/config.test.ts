/**
 * Tests for the consolidated TypeScript configuration module
 * (`src/lib/config.ts`).
 *
 * Covers:
 * - The frozen `config` proxy reflects current `process.env` at access
 *   time and parses the documented type for each field.
 * - `withConfigOverrides` installs a transient shadow config and the
 *   returned dispose function restores the previous override.
 * - The `config` object is read-only at runtime — assignment throws.
 * - The threshold registry is frozen at every level (no in-place
 *   mutation).
 * - `KNOWN_ENV_VARS` is non-empty and includes the canonical inputs
 *   the gate counterpart enforces (used as a smoke check that the
 *   list and the env-reader stay in sync).
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  KNOWN_ENV_VARS,
  config,
  withConfigOverrides,
} from "../lib/config";

const ENV_KEYS_TO_RESTORE = [
  "THESEUS_ENV",
  "DATABASE_URL",
  "PUBLIC_SITE_ORIGIN",
  "CURRENTS_CORS_ORIGINS",
  "CURRENTS_API_URL",
  "SMTP_PORT",
  "ANTHROPIC_API_KEY",
  "RESEND_API_KEY",
  "THESEUS_NOTIFY_FROM",
] as const;

describe("config (typed env)", () => {
  const original: Record<string, string | undefined> = {};

  beforeEach(() => {
    for (const key of ENV_KEYS_TO_RESTORE) {
      original[key] = process.env[key];
      delete process.env[key];
    }
  });

  afterEach(() => {
    for (const key of ENV_KEYS_TO_RESTORE) {
      const prev = original[key];
      if (prev === undefined) delete process.env[key];
      else process.env[key] = prev;
    }
  });

  it("reads strings, ints, and CSV lists from process.env at access time", () => {
    process.env.DATABASE_URL = "postgres://example/test";
    process.env.PUBLIC_SITE_ORIGIN = "https://test.theseus.app";
    process.env.CURRENTS_CORS_ORIGINS =
      "https://test.theseus.app, https://www.theseus.app ,";
    process.env.SMTP_PORT = "2525";

    expect(config.databaseUrl).toBe("postgres://example/test");
    expect(config.publicSiteOrigin).toBe("https://test.theseus.app");
    expect(config.smtpPort).toBe(2525);
    expect(config.currentsCorsOrigins).toEqual([
      "https://test.theseus.app",
      "https://www.theseus.app",
    ]);
  });

  it("returns documented defaults when env is unset", () => {
    expect(config.publicSiteOrigin).toBe("http://localhost:3001");
    expect(config.smtpPort).toBe(587);
    expect(config.notifyFrom).toBe("notify@theseus.local");
    expect(config.llmProvider).toBe("anthropic");
  });

  it("falls back to NODE_ENV when THESEUS_ENV is unset and clamps unknowns to 'development'", () => {
    delete process.env.THESEUS_ENV;
    process.env.NODE_ENV = "production";
    expect(config.env).toBe("production");

    process.env.THESEUS_ENV = "weirdvalue";
    expect(config.env).toBe("development");
  });

  it("parses invalid SMTP_PORT back to the default", () => {
    process.env.SMTP_PORT = "not-a-number";
    expect(config.smtpPort).toBe(587);
  });

  it("config object is read-only at runtime (top-level assignments throw)", () => {
    expect(() => {
      // @ts-expect-error — verifying runtime guard
      config.databaseUrl = "should-fail";
    }).toThrow(/read-only/);
  });

  it("threshold registry is deeply frozen", () => {
    expect(Object.isFrozen(config.thresholds)).toBe(true);
    expect(Object.isFrozen(config.thresholds.currents)).toBe(true);
    expect(Object.isFrozen(config.thresholds.forecasts)).toBe(true);
    expect(() => {
      // @ts-expect-error — verifying runtime guard
      config.thresholds.currents.minLikes = 0;
    }).toThrow();
  });

  it("threshold values match the published Round 17 defaults", () => {
    expect(config.thresholds.currents.minSignificanceScore).toBeCloseTo(1.35);
    expect(config.thresholds.currents.minLikes).toBe(1_000);
    expect(config.thresholds.forecasts.maxStakeUsdDefault).toBeCloseTo(5);
    expect(config.thresholds.calibration.minSampleSize).toBe(30);
    expect(config.thresholds.latencyBudgetMs.publicAskP95).toBe(2_500);
  });
});

describe("withConfigOverrides", () => {
  it("installs a transient shadow config and the dispose restores the previous state", () => {
    const initial = config.publicSiteOrigin;

    const restoreA = withConfigOverrides({
      publicSiteOrigin: "https://override-a.example",
    });
    expect(config.publicSiteOrigin).toBe("https://override-a.example");

    const restoreB = withConfigOverrides({
      publicSiteOrigin: "https://override-b.example",
      smtpHost: "smtp.example",
    });
    expect(config.publicSiteOrigin).toBe("https://override-b.example");
    expect(config.smtpHost).toBe("smtp.example");

    restoreB();
    expect(config.publicSiteOrigin).toBe("https://override-a.example");

    restoreA();
    expect(config.publicSiteOrigin).toBe(initial);
  });

  it("threshold values flow through unmodified when only top-level keys are overridden", () => {
    const restore = withConfigOverrides({ smtpPort: 2_525 });
    try {
      expect(config.smtpPort).toBe(2_525);
      expect(config.thresholds.currents.minLikes).toBe(1_000);
    } finally {
      restore();
    }
  });
});

describe("KNOWN_ENV_VARS", () => {
  it("includes the canonical inputs", () => {
    expect(KNOWN_ENV_VARS).toContain("DATABASE_URL");
    expect(KNOWN_ENV_VARS).toContain("PUBLIC_SITE_ORIGIN");
    expect(KNOWN_ENV_VARS).toContain("CURRENTS_API_URL");
    expect(KNOWN_ENV_VARS).toContain("ANTHROPIC_API_KEY");
  });

  it("is frozen so contributors cannot extend it implicitly", () => {
    expect(Object.isFrozen(KNOWN_ENV_VARS)).toBe(true);
  });
});
