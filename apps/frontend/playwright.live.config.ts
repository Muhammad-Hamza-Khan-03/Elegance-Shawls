import { defineConfig, devices } from '@playwright/test';

// Acceptance tests against a running stack (real Next.js, FastAPI and PostgreSQL),
// e.g. the local HTTPS stack from compose.local.yaml. No mocks; see e2e-live/live.ts
// for the required LIVE_* environment variables.
export default defineConfig({
  testDir: './e2e-live',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report-live' }]],
  use: {
    baseURL: process.env.LIVE_SITE_URL,
    // The local stack uses Caddy's private CA; never set this against production.
    ignoreHTTPSErrors: process.env.LIVE_IGNORE_HTTPS_ERRORS === '1',
    trace: 'retain-on-failure',
    screenshot: 'on',
    video: 'retain-on-failure',
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
});
