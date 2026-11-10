import { defineConfig, devices } from '@playwright/test';
import { assertDisposableDatabase } from './e2e-real/isolation.cjs';

// Real-stack suite: Next.js -> FastAPI -> disposable PostgreSQL. No mock API. Run `node e2e-real/prepare.mjs` first
// (npm run test:e2e:real does both). The existing mock-backed suite (playwright.config.ts, ./e2e) is unchanged.
// Servers start through e2e-real/launch.mjs, which hands them an allowlisted environment (no inherited provider credentials).
assertDisposableDatabase(process.env.E2E_DATABASE_URL);   // loopback host + designated test database, or this config refuses to load
const apiPort = process.env.E2E_REAL_API_PORT || '4300';
const webPort = process.env.E2E_REAL_WEB_PORT || '3300';
const web = `http://127.0.0.1:${webPort}`;

export default defineConfig({
  testDir: './e2e-real',
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['html', { open: 'never', outputFolder: 'playwright-report-real' }], ['github']] : 'list',
  use: { baseURL: web, trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  webServer: [
    { command: 'node e2e-real/launch.mjs backend', url: `http://127.0.0.1:${apiPort}/ready/`, reuseExistingServer: false, timeout: 90_000 },
    { command: 'node e2e-real/launch.mjs frontend', url: web, reuseExistingServer: false, timeout: 120_000 },
  ],
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
