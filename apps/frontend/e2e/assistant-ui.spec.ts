import { expect, test, type Page } from '@playwright/test';

// The assistant's look and keyboard behaviour. Runs against the mock API's scripted stream (no model, no database).
const open = async (page: Page) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Open shopping assistant' }).click();
  return page.getByRole('dialog', { name: 'Elegance Shawls shopping assistant' });
};

test('launcher is hidden on cart and admin routes', async ({ page }) => {
  await page.goto('/cart');
  await expect(page.getByRole('button', { name: /shopping assistant/ })).toHaveCount(0);
  await page.goto('/admin/login');
  await expect(page.getByRole('button', { name: /shopping assistant/ })).toHaveCount(0);
});

test('a suggested prompt gets a real answer; add-to-cart asks first and is idempotent; the card links to the product', async ({ page }) => {
  const panel = await open(page);
  await expect(panel.getByTestId('assistant-welcome')).toBeVisible();
  await expect(panel.locator('header')).not.toContainText(/preview|demo/i);       // this is the live assistant, not a mock-up
  await panel.getByRole('button', { name: 'Show me shawls' }).click();
  await expect(panel.getByTestId('assistant-user-message')).toHaveText('Show me shawls');
  const card = panel.getByTestId('assistant-product-card').first();
  await expect(card).toContainText('Pashmina Shawl');

  await card.getByRole('button', { name: 'Add to cart' }).click();
  const before = JSON.parse((await page.evaluate(() => localStorage.getItem('elegance-shawls.cart.v1'))) || '[]'); expect(before).toHaveLength(0);
  const yes = card.getByRole('button', { name: 'Yes, add' });
  await yes.evaluate((button) => { (button as HTMLElement).click(); (button as HTMLElement).click(); });
  await expect(card.getByRole('status')).toContainText('Added');
  const cart = JSON.parse((await page.evaluate(() => localStorage.getItem('elegance-shawls.cart.v1'))) || '[]');
  expect(cart).toHaveLength(1);
  expect(cart[0].quantity).toBe(1);

  await card.getByRole('link', { name: 'View product' }).click();
  await expect(page).toHaveURL(/\/product\/assistant-pashmina/);
});

test('Cancel in the confirmation adds nothing', async ({ page }) => {
  const panel = await open(page);
  await panel.getByRole('button', { name: 'Show me shawls' }).click();
  const card = panel.getByTestId('assistant-product-card').first();
  await card.getByRole('button', { name: 'Add to cart' }).click();
  await card.getByRole('button', { name: 'Cancel' }).click();
  await expect(card.getByRole('button', { name: 'Add to cart' })).toBeVisible();
  expect(JSON.parse((await page.evaluate(() => localStorage.getItem('elegance-shawls.cart.v1'))) || '[]')).toHaveLength(0);
});

test('keyboard: focus lands in the box, Enter sends, an error can be retried, New chat resets, Escape closes and returns focus, no horizontal overflow', async ({ page }) => {
  let fail = true;
  await page.route('**/api/assistant/stream', async (route) => {
    if (!fail) return route.fallback();
    fail = false;
    await route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"down"}' });
  });
  const panel = await open(page);
  const input = panel.getByLabel('Message the shopping assistant');
  await expect(input).toBeFocused();
  await input.fill('show me a shawl');
  await input.press('Enter');
  await expect(panel.getByTestId('assistant-error')).toContainText('The assistant is unavailable right now.');
  await panel.getByRole('button', { name: 'Try again' }).click();
  await expect(panel.getByTestId('assistant-product-card').first()).toBeVisible();
  await expect(panel.getByTestId('assistant-user-message')).toHaveCount(1);       // the retry replaced the failed turn
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

  await panel.getByRole('button', { name: 'New chat' }).click();
  await expect(panel.getByTestId('assistant-welcome')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(panel).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Open shopping assistant' })).toBeFocused();
});

test('Stop ends a response without adding anything', async ({ page }) => {
  await page.route('**/api/assistant/stream', () => new Promise(() => undefined));  // never answers
  const panel = await open(page);
  await panel.getByLabel('Message the shopping assistant').fill('show me a shawl');
  await panel.getByLabel('Message the shopping assistant').press('Enter');
  await expect(panel.getByTestId('assistant-thinking')).toBeVisible();
  await panel.getByRole('button', { name: 'Stop response' }).click();
  await expect(panel.getByRole('button', { name: 'Send message' })).toBeVisible();
  await expect(panel.getByTestId('assistant-product-card')).toHaveCount(0);
});
