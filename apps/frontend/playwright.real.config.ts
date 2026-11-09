import { defineConfig, devices } from '@playwright/test';

// Real-stack suite: Next.js -> FastAPI -> disposable PostgreSQL. No mock API. Run `node e2e-real/prepare.mjs` first
// (npm run test:e2e:real does both). The existing mock-backed suite (playwright.config.ts, ./e2e) is unchanged.
const apiPort = process.env.E2E_REAL_API_PORT || '4300';
const webPort = process.env.E2E_REAL_WEB_PORT || '3300';
const python = process.env.E2E_PYTHON || 'python';
const database = process.env.E2E_DATABASE_URL || '';
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
    {
      command: `${python} -m uvicorn main:app --host 127.0.0.1 --port ${apiPort}`,
      cwd: '../backend',
      url: `http://127.0.0.1:${apiPort}/ready/`,
      reuseExistingServer: false,
      timeout: 90_000,
      env: {
        DATABASE_URL: database, ENVIRONMENT: 'development', ALLOWED_ORIGINS: web, ASSISTANT_CATALOGUE: 'true', ASSISTANT_LLM: 'false',
        PUBLIC_RATE_LIMIT_PER_MINUTE: '100000', ADMIN_RATE_LIMIT_PER_MINUTE: '100000', ADMIN_API_KEY: '', ADMIN_LEGACY_KEY_EXPIRES_AT: '',
        EMBEDDING_ENABLED: 'false', LOCAL_SEMANTIC_SEARCH_ENABLED: 'false', REDIS_URL: '',
      },
    },
    {
      command: `npm run dev -- --hostname 127.0.0.1 --port ${webPort}`,
      url: web,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        NEXT_PUBLIC_API_URL: `http://127.0.0.1:${apiPort}`, NEXT_PUBLIC_SITE_URL: web, NEXT_PUBLIC_WHATSAPP_NUMBER: '923001234567',
        NEXT_PUBLIC_ASSISTANT_ENABLED: '1', ADMIN_API_KEY: '',
      },
    },
  ],
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
