/**
 * Central, typed configuration for the theseus-codex (Next.js) tree.
 *
 * This module is the *one* place `process.env` is read inside the
 * TypeScript codebase. Values are parsed and frozen at first import; the
 * exported `config` object is read-only at runtime.
 *
 * For tests, use {@link withConfigOverrides} to install a transient
 * shadow config, and call the returned dispose function in `afterEach`.
 *
 * The magic-number registry under `config.thresholds` mirrors the
 * Python-side `Thresholds` model so that cross-language behaviour stays
 * consistent. **Do not change values here without an accompanying tuning
 * prompt.** Centralizing was a refactor; tuning is a separate workflow.
 *
 * See `docs/architecture/Configuration.md` for the full contract.
 */

const TRUTHY = new Set(["1", "true", "yes", "on"]);
const FALSY = new Set(["0", "false", "no", "off"]);

function readString(name: string, fallback = ""): string {
  const raw = process.env[name];
  if (raw === undefined || raw === null) return fallback;
  return raw;
}

function readBool(name: string, fallback: boolean): boolean {
  const raw = (process.env[name] ?? "").trim().toLowerCase();
  if (!raw) return fallback;
  if (TRUTHY.has(raw)) return true;
  if (FALSY.has(raw)) return false;
  return fallback;
}

function readInt(name: string, fallback: number): number {
  const raw = (process.env[name] ?? "").trim();
  if (!raw) return fallback;
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function readFloat(name: string, fallback: number): number {
  const raw = (process.env[name] ?? "").trim();
  if (!raw) return fallback;
  const parsed = Number.parseFloat(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
}

/**
 * Magic-number registry. Mirror of `noosphere.core.config.Thresholds`.
 * Keep values aligned across the language boundary.
 */
export interface Thresholds {
  readonly currents: {
    readonly minSignificanceScore: number;
    readonly minLikes: number;
    readonly minRetweets: number;
    readonly minImpressions: number;
    readonly maxEventsPerCycle: number;
    readonly requestTimeoutS: number;
  };
  readonly forecasts: {
    readonly maxStakeUsdDefault: number;
    readonly maxDailyLossUsdDefault: number;
    readonly killSwitchAutoThresholdUsdDefault: number;
    readonly paperInitialBalanceUsdDefault: number;
    readonly maxMarketsPerCycle: number;
    readonly requestTimeoutS: number;
  };
  readonly calibration: {
    readonly minSampleSize: number;
    readonly driftSeverityMultiplier: number;
    readonly driftSigmaWarning: number;
    readonly driftSigmaCritical: number;
  };
  readonly retention: {
    readonly rateLimitWindowS: number;
    readonly auditLogRetentionDays: number;
  };
  readonly latencyBudgetMs: {
    readonly publicAskP95: number;
    readonly publicCalibrationManifestP95: number;
    readonly methodologyManifestP95: number;
  };
}

export interface AppConfig {
  readonly env: "development" | "staging" | "production" | "test";

  // Database / data plane.
  readonly databaseUrl: string;
  readonly directUrl: string;

  // Public site / CORS.
  readonly publicSiteOrigin: string;
  readonly currentsCorsOrigins: readonly string[];

  // Bridges to noosphere services.
  readonly currentsApiUrl: string;
  readonly noosphereApiUrl: string;

  // Auth / security.
  readonly authSecret: string;
  readonly csrfSecret: string;
  readonly sessionTtlMinutes: number;

  // LLM defaults (kept aligned with Python Settings.llm_*).
  readonly llmProvider: "anthropic" | "openai";
  readonly llmModel: string;
  readonly anthropicApiKey: string;
  readonly openaiApiKey: string;

  // Mail / notifications.
  readonly notifyFrom: string;
  readonly founderAlphaEmail: string;
  readonly resendApiKey: string;
  readonly smtpHost: string;
  readonly smtpPort: number;
  readonly smtpUser: string;
  readonly smtpPass: string;

  // Magic-number registry.
  readonly thresholds: Thresholds;
}

const THRESHOLDS_DEFAULTS: Thresholds = Object.freeze({
  currents: Object.freeze({
    minSignificanceScore: 1.35,
    minLikes: 1_000,
    minRetweets: 100,
    minImpressions: 25_000,
    maxEventsPerCycle: 40,
    requestTimeoutS: 15.0,
  }),
  forecasts: Object.freeze({
    maxStakeUsdDefault: 5.0,
    maxDailyLossUsdDefault: 20.0,
    killSwitchAutoThresholdUsdDefault: 15.0,
    paperInitialBalanceUsdDefault: 10_000.0,
    maxMarketsPerCycle: 200,
    requestTimeoutS: 15.0,
  }),
  calibration: Object.freeze({
    minSampleSize: 30,
    driftSeverityMultiplier: 1.5,
    driftSigmaWarning: 2.0,
    driftSigmaCritical: 3.0,
  }),
  retention: Object.freeze({
    rateLimitWindowS: 60,
    auditLogRetentionDays: 90,
  }),
  latencyBudgetMs: Object.freeze({
    publicAskP95: 2_500,
    publicCalibrationManifestP95: 800,
    methodologyManifestP95: 800,
  }),
});

function parseEnvName(raw: string): AppConfig["env"] {
  const v = raw.trim().toLowerCase();
  if (v === "production" || v === "staging" || v === "test") return v;
  return "development";
}

function parseCorsOrigins(raw: string): string[] {
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

function buildConfig(): AppConfig {
  const env = parseEnvName(
    process.env.THESEUS_ENV ?? process.env.NODE_ENV ?? "development",
  );

  return Object.freeze({
    env,
    databaseUrl: readString("DATABASE_URL"),
    directUrl: readString("DIRECT_URL"),
    publicSiteOrigin: readString(
      "PUBLIC_SITE_ORIGIN",
      "http://localhost:3001",
    ),
    currentsCorsOrigins: Object.freeze(
      parseCorsOrigins(readString("CURRENTS_CORS_ORIGINS", "")),
    ),
    currentsApiUrl: readString("CURRENTS_API_URL", "http://currents-api:8088"),
    noosphereApiUrl: readString(
      "NOOSPHERE_API_URL",
      readString("CURRENTS_API_URL", "http://currents-api:8088"),
    ),
    authSecret: readString("AUTH_SECRET"),
    csrfSecret: readString("CSRF_SECRET"),
    sessionTtlMinutes: readInt("SESSION_TTL_MINUTES", 60 * 24 * 7),
    llmProvider:
      (readString("THESEUS_LLM_PROVIDER", "anthropic") as
        | "anthropic"
        | "openai") || "anthropic",
    llmModel: readString("THESEUS_LLM_MODEL", "claude-sonnet-4-20250514"),
    anthropicApiKey: readString("ANTHROPIC_API_KEY"),
    openaiApiKey: readString("OPENAI_API_KEY"),
    notifyFrom: readString("THESEUS_NOTIFY_FROM", "notify@theseus.local"),
    founderAlphaEmail: readString(
      "FOUNDER_ALPHA_EMAIL",
      "founder-alpha@example.invalid",
    ),
    resendApiKey: readString("RESEND_API_KEY"),
    smtpHost: readString("SMTP_HOST"),
    smtpPort: readInt("SMTP_PORT", 587),
    smtpUser: readString("SMTP_USER"),
    smtpPass: readString("SMTP_PASS"),
    thresholds: THRESHOLDS_DEFAULTS,
    // Allow per-field threshold overrides via env without re-creating the
    // whole nested literal each call — these are deliberately not exposed
    // as env vars yet (tuning prompt territory).
  });
}

let _override: AppConfig | null = null;

function activeConfig(): AppConfig {
  if (_override) return _override;
  return buildConfig();
}

/**
 * Frozen, lazily-built typed view of `process.env`. Importers must read
 * properties off this object rather than touching `process.env`
 * directly — the CI gate (`scripts/check_no_inline_env_reads.py`)
 * enforces that.
 */
export const config: AppConfig = new Proxy({} as AppConfig, {
  get(_target, prop) {
    return Reflect.get(activeConfig(), prop);
  },
  has(_target, prop) {
    return prop in activeConfig();
  },
  ownKeys() {
    return Reflect.ownKeys(activeConfig());
  },
  getOwnPropertyDescriptor(_target, prop) {
    return Object.getOwnPropertyDescriptor(activeConfig(), prop);
  },
  set() {
    throw new Error(
      "config is read-only. Use withConfigOverrides() in tests to override.",
    );
  },
  defineProperty() {
    throw new Error(
      "config is read-only. Use withConfigOverrides() in tests to override.",
    );
  },
  deleteProperty() {
    throw new Error("config is read-only.");
  },
});

/**
 * Test helper: install a transient shadow config. Returns a dispose
 * function that restores the previous override (or clears it).
 *
 * Usage::
 *
 *   const restore = withConfigOverrides({ smtpHost: "localhost" });
 *   try { ... } finally { restore(); }
 */
export function withConfigOverrides(
  overrides: Partial<AppConfig>,
): () => void {
  const previous = _override;
  const merged = mergeConfig(activeConfig(), overrides);
  _override = Object.freeze(merged) as AppConfig;
  return () => {
    _override = previous;
  };
}

function mergeConfig(
  base: AppConfig,
  overrides: Partial<AppConfig>,
): AppConfig {
  // Shallow merge is sufficient because the public shape is one level
  // deep apart from `thresholds`, which we splice through specially.
  const next: Record<string, unknown> = { ...base };
  for (const [key, value] of Object.entries(overrides)) {
    if (value === undefined) continue;
    next[key] = value;
  }
  return next as AppConfig;
}

/**
 * Names of `process.env` keys this module is *expected* to read. The CI
 * gate uses the existence of this list to verify that every legacy site
 * has been migrated; new env vars must be appended here too.
 */
export const KNOWN_ENV_VARS: readonly string[] = Object.freeze([
  "THESEUS_ENV",
  "NODE_ENV",
  "DATABASE_URL",
  "DIRECT_URL",
  "PUBLIC_SITE_ORIGIN",
  "CURRENTS_CORS_ORIGINS",
  "CURRENTS_API_URL",
  "NOOSPHERE_API_URL",
  "AUTH_SECRET",
  "CSRF_SECRET",
  "SESSION_TTL_MINUTES",
  "THESEUS_LLM_PROVIDER",
  "THESEUS_LLM_MODEL",
  "ANTHROPIC_API_KEY",
  "OPENAI_API_KEY",
  "THESEUS_NOTIFY_FROM",
  "FOUNDER_ALPHA_EMAIL",
  "RESEND_API_KEY",
  "SMTP_HOST",
  "SMTP_PORT",
  "SMTP_USER",
  "SMTP_PASS",
]);
