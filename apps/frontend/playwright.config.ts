import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [['html', { open: 'never' }], ['github']] : 'list',
  use: { baseURL: 'http://127.0.0.1:3100', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  webServer: [
    { command: 'node e2e/mock-api.mjs', url: 'http://127.0.0.1:4100/health/', reuseExistingServer: !process.env.CI },
    { command: 'npm run dev -- --hostname 127.0.0.1 --port 3100', url: 'http://127.0.0.1:3100', reuseExistingServer: !process.env.CI, env: { NEXT_PUBLIC_API_URL: 'http://127.0.0.1:4100', NEXT_PUBLIC_SITE_URL: 'http://127.0.0.1:3100', NEXT_PUBLIC_WHATSAPP_NUMBER: '923001234567' } },
  ],
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile-chromium', use: { ...devices['Pixel 7'] } },
  ],
});
