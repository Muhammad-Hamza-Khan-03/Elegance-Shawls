import { defineConfig, devices } from '@playwright/test';

const apiPort = process.env.E2E_API_PORT || '4100';
const webPort = process.env.E2E_WEB_PORT || '3100';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [['html', { open: 'never' }], ['github']] : 'list',
  use: { baseURL: `http://127.0.0.1:${webPort}`, trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  webServer: [
    { command: 'node e2e/mock-api.mjs', url: `http://127.0.0.1:${apiPort}/health/`, reuseExistingServer: !process.env.CI, env: { MOCK_API_PORT: apiPort } },
    { command: `npm run dev -- --hostname 127.0.0.1 --port ${webPort}`, url: `http://127.0.0.1:${webPort}`, reuseExistingServer: !process.env.CI, env: { NEXT_PUBLIC_ASSISTANT_ENABLED: '1', NEXT_PUBLIC_API_URL: `http://127.0.0.1:${apiPort}`, NEXT_PUBLIC_SITE_URL: `http://127.0.0.1:${webPort}`, NEXT_PUBLIC_WHATSAPP_NUMBER: '923001234567' } },
  ],
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile-chromium', use: { ...devices['Pixel 7'] } },
  ],
});
