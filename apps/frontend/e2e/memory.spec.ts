import { test, expect } from '@playwright/test';

test('memory management is principal-scoped and requires delete confirmation', async ({ page }) => {
  let deleted = false;
  await page.route('**/v1/me/memory**', async (route) => {
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
