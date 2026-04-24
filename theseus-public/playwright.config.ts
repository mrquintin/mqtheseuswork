import { defineConfig } from "@playwright/test";

/**
 * Prompt-17 opt-in smoke test config.
 *
 * This is NOT in the default `npm test` workflow — the smoke test is
 * intentionally isolated to `npm run test:e2e` so CI pipelines don't
 * pull Chromium on every unit-test run. The user runs `npm i` first to
 * pick up `@playwright/test` if they haven't already.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  use: {
    baseURL: "http://localhost:3001",
    trace: "on-first-retry",
  },
  webServer: {
    command: "npm run dev",
    port: 3001,
    timeout: 60_000,
    reuseExistingServer: !process.env.CI,
  },
});
