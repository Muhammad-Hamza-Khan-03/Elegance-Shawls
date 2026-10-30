import { expect, test } from '@playwright/test';

test('admin shell blocks anonymous access and supports navigation', async ({ page }) => {
  await page.goto('/admin/dashboard');
  await expect(page).toHaveURL(/\/admin\/login/);
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();

  await page.getByLabel('Email').fill('owner@example.test');
  await page.getByLabel('Password').fill('test-owner-password');
  await page.getByRole('button', { name: 'Sign in' }).click();

  await expect(page).toHaveURL(/\/admin\/dashboard$/);
  await expect(page.getByRole('heading', { name: 'Admin shell overview' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Admin navigation' })).toBeVisible();

  await page.getByRole('link', { name: 'Products', exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/products$/);
  await expect(page.getByRole('heading', { name: 'Product management workspace' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'New product' })).toBeVisible();

  const mutationStatus = await page.evaluate(async () => {
    const response = await fetch('/api/admin/products', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: '{}',
    });
    return response.status;
  });
  expect(mutationStatus).toBe(200);

  await page.getByRole('link', { name: 'Orders' }).click();
  await expect(page).toHaveURL(/\/admin\/orders$/);
  await expect(page.getByRole('heading', { name: 'Order operations scaffold' })).toBeVisible();
});
