import { test, expect } from '@playwright/test';

test('memory management is principal-scoped and requires delete confirmation', async ({ page }) => {
  let deleted = false;
  await page.route('**/api/customer/memory**', async (route) => {
    const request = route.request();
    if (request.method() === 'GET' && request.url().endsWith('/consent')) return route.fulfill({ json: { granted: true, policy_version: 'test-policy', changed_at: null } });
    if (request.method() === 'GET') return route.fulfill({ json: { items: [{ id: 'm-1', category: 'preference', key: 'fabric', value: 'wool', source: 'user_explicit', source_ref: null, reason: 'chosen by customer', version: 1, retention_days: 30, expires_at: '2030-01-01T00:00:00Z', created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' }] } });
    if (request.method() === 'DELETE') { deleted = true; return route.fulfill({ status: 204 }); }
    return route.fulfill({ json: {} });
  });
  await page.goto('/memory');
  await expect(page.getByRole('heading', { name: 'Manage saved memory' })).toBeVisible();
  await expect(page.getByText('wool')).toBeVisible();
  await expect(page.locator('body')).not.toContainText('customer-foreign-id');
  page.once('dialog', (dialog) => dialog.dismiss());
  await page.getByRole('button', { name: 'Delete', exact: true }).click();
  expect(deleted).toBe(false);
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: 'Delete', exact: true }).click();
  await expect.poll(() => deleted).toBe(true);
});

test('a customer can add a memory from the page and sees a clear message for a duplicate name', async ({ page }) => {
  const sent: Record<string, unknown>[] = [];
  const stored = { id: 'm-9', category: 'preference', key: 'favourite_colour', value: 'brown', source: 'memory_page', source_ref: null, reason: null, version: 1, retention_days: 180, expires_at: '2030-01-01T00:00:00Z', created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' };
  await page.route('**/api/customer/memory**', async (route) => {
    const request = route.request();
    if (request.method() === 'GET' && request.url().endsWith('/consent')) return route.fulfill({ json: { granted: true, policy_version: 'test-policy', changed_at: null } });
    if (request.method() === 'GET') return route.fulfill({ json: { items: [] } });
    if (request.method() === 'POST') {
      sent.push(request.postDataJSON());
      return sent.length === 1 ? route.fulfill({ status: 201, json: stored }) : route.fulfill({ status: 409, json: { detail: 'Request was not accepted.', reason: 'duplicate_key' } });
    }
    return route.fulfill({ json: {} });
  });
  await page.goto('/memory');
  const form = page.getByRole('form', { name: 'Add a memory' });
  await form.getByLabel('Name').fill('favourite_colour');
  await form.getByLabel('Value').fill('brown');
  await form.getByRole('button', { name: 'Save memory' }).click();
  await expect(page.getByRole('heading', { name: 'favourite_colour' })).toBeVisible();
  expect(sent[0]).toMatchObject({ category: 'preference', key: 'favourite_colour', value: 'brown', source: 'memory_page' });
  expect(String(sent[0].idempotency_key)).toMatch(/^idem_/);
  expect(Object.keys(sent[0]).join()).not.toMatch(/customer|user/i);

  await form.getByLabel('Name').fill('favourite_colour');
  await form.getByLabel('Value').fill('red');
  await form.getByRole('button', { name: 'Save memory' }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'already saved something with that name' })).toBeVisible();
});
