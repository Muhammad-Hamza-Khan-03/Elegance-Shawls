import { expect, test, type Page, type Route } from '@playwright/test';

const ids = {
  pending: '22222222-2222-4222-8222-222222222222',
  rejected: '33333333-3333-4333-8333-333333333333',
  archived: '44444444-4444-4444-8444-444444444444',
};
const runId = '11111111-1111-4111-8111-111111111111';

const staged = (key: keyof typeof ids, name: string) => ({
  _id: ids[key], source_name: 'Fixture Shop', source_url: 'https://shop.example/p', status: key === 'pending' ? 'pending_review' : key,
  missing_fields: [], stock_known: true,
  product: { name, cover_image_url: '', images: [], category: 'shawls', variants: [] },
  created_at: '2026-01-01T00:00:00Z',
});

const run = (stagedId: string, status: string, over = {}) => ({
  id: runId, staged_product_id: stagedId, status, authoritative: false, suggestions: null, validation_errors: [],
  provider: 'fixture-provider', model: 'fixture-model', prompt_version: 'p1', vocabulary_version: 'v1',
  input_content_hash: 'hash123', attempts: 0, created_at: '2026-01-01T00:00:00Z', ...over,
});

const json = (route: Route, status: number, body: unknown) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

// Mocks the same-origin /api/admin/ingestion/* calls the page makes; the Next proxy itself is covered by vitest.
const mockBackend = async (page: Page) => {
  const state = { posts: 0, cancels: 0, current: null as ReturnType<typeof run> | null };

  await page.route(/\/api\/admin\/ingestion\/.*/, async (route) => {
    const { pathname, searchParams } = new URL(route.request().url());
    const method = route.request().method();
    if (pathname.endsWith('/staged')) {
      const all = [staged('pending', 'Pending Shawl'), staged('rejected', 'Rejected Shawl'), staged('archived', 'Archived Shawl')];
      const want = searchParams.get('status');
      return json(route, 200, { items: all.filter((item) => !want || item.status === want), next_cursor: null });
    }
    if (pathname.endsWith(`${ids.pending}/enrichment`)) {
      if (method === 'GET') return state.current ? json(route, 200, state.current) : json(route, 404, { detail: 'No enrichment suggestion for this staged product' });
      state.posts += 1;
      await new Promise((resolve) => setTimeout(resolve, 400)); // keep the request in flight so a second click can race it
      state.current = run(ids.pending, 'queued');
      return json(route, 202, state.current);
    }
    if (pathname.endsWith(`${runId}/cancel`)) {
      state.cancels += 1;
      state.current = run(ids.pending, 'cancelled');
      return json(route, 200, state.current);
    }
    for (const key of ['rejected', 'archived'] as const) {
      if (pathname.endsWith(`${ids[key]}/enrichment`)) {
        if (method !== 'GET') return json(route, 409, { detail: `Cannot enrich a staged product that is ${key}` });
        return json(route, 200, run(ids[key], 'succeeded', { suggestions: { pattern: { value: 'floral', reason: 'Seen in photo', source: 'visual_suggestion' } } }));
      }
    }
    return json(route, 404, { detail: 'unmocked' });
  });
  return state;
};

// Same login flow as admin.spec.ts: the real session cookie, no bypass.
const signIn = async (page: Page) => {
  await page.goto('/admin/login');
  await page.getByLabel('Email').fill('owner@example.test');
  await page.getByLabel('Password').fill('test-owner-password');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/admin\/dashboard$/);
  await page.goto('/admin/staging');
};

test('request -> queued -> cancel -> cancelled, with duplicate-click protection', async ({ page }) => {
  const state = await mockBackend(page);
  await signIn(page);

  const panel = page.getByTestId('staged-product').filter({ hasText: 'Pending Shawl' }).getByRole('region', { name: 'Enrichment suggestions' });
  await expect(panel.getByText('Advisory suggestion — not catalogue truth')).toBeVisible();
  await expect(panel.getByTestId('enrichment-empty')).toBeVisible();

  await panel.getByRole('button', { name: 'Request suggestions' }).dblclick();
  await expect(panel.getByTestId('enrichment-status')).toHaveText('queued');
  expect(state.posts).toBe(1);
  await expect(panel.getByRole('button', { name: 'Request new suggestions' })).toHaveCount(0);

  await panel.getByRole('button', { name: 'Cancel run' }).click();
  await expect(panel.getByTestId('enrichment-status')).toHaveText('cancelled');
  expect(state.cancels).toBe(1);
  await expect(panel.getByRole('button', { name: 'Cancel run' })).toHaveCount(0);
  await expect(panel.getByRole('button', { name: 'Request new suggestions' })).toBeVisible();

  await page.reload(); // backend state is reloaded, not kept client-side
  await expect(panel.getByTestId('enrichment-status')).toHaveText('cancelled');
});

for (const status of ['rejected', 'archived'] as const) {
  test(`${status} product shows existing suggestions but cannot request new ones`, async ({ page }) => {
    const state = await mockBackend(page);
    await signIn(page);
    await page.getByLabel('Status').selectOption(status);

    const panel = page.getByTestId('staged-product').getByRole('region', { name: 'Enrichment suggestions' });
    await expect(panel.getByTestId('enrichment-status')).toHaveText('succeeded');
    await expect(panel.getByText('floral')).toBeVisible();
    await expect(panel.getByText(`cannot be requested for ${status}`)).toBeVisible();
    await expect(panel.getByRole('button', { name: /Request/ })).toHaveCount(0);
    await expect(panel.getByRole('button', { name: 'Reload suggestions' })).toBeVisible();
    expect(state.posts).toBe(0);
  });
}
