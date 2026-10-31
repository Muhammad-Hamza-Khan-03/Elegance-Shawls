import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

async function scan(page: Page, name: string) {
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
  await test.info().attach(`axe-${name}.json`, { body: JSON.stringify(violations, null, 2), contentType: 'application/json' });
  const baselineExceptions = new Set(['color-contrast', 'label-content-name-mismatch']);
  const blocking = violations.filter((violation) =>
    (violation.impact === 'serious' || violation.impact === 'critical') && !baselineExceptions.has(violation.id),
  );
  expect(blocking.map((violation) => violation.id), name).toEqual([]);
}

for (const [name, path] of [['home', '/'], ['collection', '/products'], ['product', '/product/classic-wool-shawl'], ['cart', '/cart'], ['delivery', '/delivery'], ['admin-login', '/admin/login']]) {
  test(`a11y: ${name}`, async ({ page }) => {
    await page.goto(path);
    await expect(page.locator('main, #main-content').first()).toBeVisible();
    await scan(page, name);
  });
}

test('a11y: admin dashboard and products after sign-in', async ({ page }) => {
  await page.goto('/admin/login');
  await page.getByLabel('Email').fill('owner@example.test');
  await page.getByLabel('Password').fill('test-owner-password');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Admin shell overview' })).toBeVisible();
  await scan(page, 'admin-dashboard');
  await page.getByRole('link', { name: 'Products', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Product management workspace' })).toBeVisible();
  await scan(page, 'admin-products');
});
