import { expect, test } from '@playwright/test';

test('shared cart supports multiple products, quantity editing and refresh persistence', async ({ page }) => {
  const hydrationErrors: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error' && /hydration failed|hydrated.*didn't match/i.test(message.text())) hydrationErrors.push(message.text());
  });
  await page.goto('/product/classic-wool-shawl');
  await page.getByLabel('Increase quantity').click();
  await page.getByRole('button', { name: 'Add to cart' }).click();
  await expect(page.getByRole('link', { name: /Cart/ }).last()).toContainText('2');

  await page.goto('/product/light-silk-stole');
  await page.getByRole('button', { name: 'Add to cart' }).click();
  await expect(page.getByRole('link', { name: /Cart/ }).last()).toContainText('3');

  await page.goto('/cart');
  await expect(page.getByRole('heading', { name: 'Your cart' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Classic Wool Shawl' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Light Silk Stole' })).toBeVisible();
  await expect(page.getByLabel('Quantity for Classic Wool Shawl')).toHaveValue('2');
  await page.getByLabel('Increase Classic Wool Shawl quantity').click();
  await expect(page.getByLabel('Quantity for Classic Wool Shawl')).toHaveValue('3');
  await expect(page.getByLabel('Increase Classic Wool Shawl quantity')).toBeDisabled();

  await page.reload();
  await expect(page.getByLabel('Quantity for Classic Wool Shawl')).toHaveValue('3');
  await expect(page.getByLabel('Quantity for Light Silk Stole')).toHaveValue('1');
  await expect(page.getByRole('link', { name: /Cart/ }).last()).toContainText('4');
  expect(hydrationErrors).toEqual([]);
});

test('WhatsApp handoff creates an enquiry reference first and puts it in the encoded message', async ({ page }) => {
  await page.context().route('https://wa.me/**', (route) => route.fulfill({ body: 'wa' }));
  await page.goto('/product/classic-wool-shawl');
  await page.getByRole('button', { name: 'Add to cart' }).click();
  await page.goto('/cart');
  const send = page.getByRole('button', { name: 'Send cart on WhatsApp' });
  await expect(send).toBeEnabled();
  const [popup] = await Promise.all([page.waitForEvent('popup'), send.click()]);
  await popup.waitForURL(/wa\.me/);
  const message = decodeURIComponent(popup.url().split('?text=')[1]);
  expect(popup.url()).toContain('Enquiry%20reference%3A%20ES-MOCK42');
  expect(message).toContain('Enquiry reference: ES-MOCK42');
  const recorded = await (await page.request.get('http://127.0.0.1:4100/__last-enquiry')).json();
  expect(recorded.items).toEqual([{ product_id: 'p1', variant_id: 'v1', quantity: 1, unit_price: 4500, currency: 'PKR' }]);
});
