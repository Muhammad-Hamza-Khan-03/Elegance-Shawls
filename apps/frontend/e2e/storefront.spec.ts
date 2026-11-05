import { expect, test } from '@playwright/test';

test('customer can browse, search and filter the collection', async ({ page }) => {
  await page.goto('/products');
  await expect(page.getByRole('heading', { name: 'Shop the collection' })).toBeVisible();
  await expect(page.getByRole('main').getByText('12 products found')).toBeVisible();
  await page.getByLabel('Search').fill('silk');
  await expect(page.getByRole('link', { name: /Light Silk Stole/ })).toBeVisible();
  await expect(page.getByRole('link', { name: /Classic Wool Shawl/ })).toBeHidden();
  await page.getByLabel('Search').fill('');
  await page.getByLabel('Sort by').selectOption('price_desc');
  await expect(page.getByRole('link').filter({ hasText: 'Classic Wool Shawl' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Product pages' })).toBeVisible();
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(page.getByText('Page 2 of 2')).toBeVisible();
  await page.getByLabel('Category').selectOption('shawls');
  await expect(page.getByRole('main').getByText('1 product found')).toBeVisible();
});

test('header category links filter the collection', async ({ page, isMobile }) => {
  await page.goto('/products');
  await expect(page.getByRole('main').getByText('12 products found')).toBeVisible();
  const nav = async (name: string) => {
    if (isMobile) await page.getByRole('button', { name: 'Open navigation menu' }).click();
    const navigation = page.getByRole('navigation', { name: isMobile ? 'Mobile navigation' : 'Main navigation' });
    if (!isMobile && name !== 'All products') await navigation.getByRole('link', { name: 'All products' }).hover();
    await navigation.getByRole('link', { name, exact: true }).click();
  };
  await nav('Shawls');
  await expect(page.getByRole('main').getByText('1 product found')).toBeVisible();
  await nav('Stoles');
  await expect(page.getByRole('main').getByText('11 products found')).toBeVisible();
  await nav('All products');
  await expect(page.getByRole('main').getByText('12 products found')).toBeVisible();
});

test('collection is server-rendered and does not need the browser to reach the API', async ({ page }) => {
  await page.route('http://127.0.0.1:4100/**', (route) => route.abort());
  await page.goto('/products');
  await expect(page.getByRole('main').getByText('12 products found')).toBeVisible();
});

test('product selection creates a complete WhatsApp order', async ({ page }) => {
  await page.goto('/product/classic-wool-shawl');
  await expect(page.getByRole('heading', { name: 'Classic Wool Shawl' })).toBeVisible();
  await expect(page.getByRole('radio', { name: /Black/ })).toBeDisabled();
  await page.getByLabel('Increase quantity').click();
  const order = page.getByRole('link', { name: 'Order on WhatsApp' }).first();
  await expect(order).toHaveAttribute('href', /wa\.me\/923001234567/);
  const href = await order.getAttribute('href');
  const message = decodeURIComponent(href || '');
  for (const value of ['Classic Wool Shawl', 'Brown', 'Free Size', 'Quantity: 2', 'ES-001', 'PKR', 'classic-wool-shawl']) expect(message).toContain(value);
});

test('navigation and customer information pages work', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('link', { name: 'Explore the collection' }).click();
  await expect(page).toHaveURL(/\/products$/);
  await page.goto('/delivery');
  await expect(page.getByRole('heading', { name: 'Delivery' })).toBeVisible();
  await page.goto('/missing-page');
  await expect(page.getByRole('heading', { name: 'This page could not be found.' })).toBeVisible();
});
