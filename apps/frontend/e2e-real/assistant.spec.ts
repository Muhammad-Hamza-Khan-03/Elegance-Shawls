import { expect, test, type Page } from '@playwright/test';
import { cartKey } from './helpers';

// The assistant here is the REAL backend (catalogue-grounded, no LLM: ASSISTANT_LLM=false), so wording is deterministic.
// What is real: parsing, search, stock/price checks, action validation, enquiry creation. What is not covered: model wording.
const cart = (page: Page) => page.evaluate((key) => JSON.parse(localStorage.getItem(key) ?? '[]') as { quantity: number; productId: string }[], cartKey);

async function ask(page: Page, text: string) {
  await page.goto('/');
  await page.getByRole('button', { name: 'Open shopping assistant' }).click();
  await page.getByLabel('Message the shopping assistant').fill(text);
  await page.getByLabel('Message the shopping assistant').press('Enter');
}

test('English request -> exactly one grounded in-stock card -> confirmed add-to-cart executes exactly once', async ({ page }) => {
  await ask(page, 'brown stole under 4000');
  const cards = page.getByTestId('assistant-product-card');
  await expect(cards).toHaveCount(1);                                              // every card is checked, not just the first
  await expect(cards.first()).toContainText('Brown Pashmina Stole');
  for (const excluded of ['Brown Jamawar Stole', 'Brown Wool Shawl', 'Maroon Silk Stole', 'Draft Green Shawl']) {
    await expect(page.getByTestId('assistant-product-card').filter({ hasText: excluded })).toHaveCount(0);   // over budget / wrong kind / sold out / never public
  }
  expect(await cart(page)).toEqual([]);                                            // asking changed nothing

  const card = cards.first();
  await card.getByRole('button', { name: 'Add to cart' }).click();
  await card.getByRole('button', { name: 'Yes, add' }).dblclick();                 // a double press is still one action
  await expect(page.getByTestId('action-done')).toContainText('Added to your cart.');
  const lines = await cart(page);
  expect(lines).toHaveLength(1);
  expect(lines[0].quantity).toBe(1);
});

test('a lower bound is honoured: "above 4000" shows only the 4500 brown stole', async ({ page }) => {
  await ask(page, 'brown stole above 4000');
  const cards = page.getByTestId('assistant-product-card');
  await expect(cards).toHaveCount(1);
  await expect(cards.first()).toContainText('Brown Jamawar Stole');
});

for (const [language, text] of [['Roman Urdu', 'bhoora stole 4000 se kam'], ['Urdu', 'بھورا اسٹول 4000 سے کم']] as const) {
  test(`${language} request is understood by the real parser (one card, within budget)`, async ({ page }) => {
    await ask(page, text);
    const cards = page.getByTestId('assistant-product-card');
    await expect(cards).toHaveCount(1);
    await expect(cards.first()).toContainText('Brown Pashmina Stole');
  });
}

test('an impossible request is answered honestly: no invented products', async ({ page }) => {
  await ask(page, 'purple shawl under 100');
  await expect(page.getByTestId('assistant-message').first()).toBeVisible();
  await expect(page.getByTestId('assistant-product-card')).toHaveCount(0);
});

test('graceful degradation: when the assistant stream is down the shop still works', async ({ page }) => {
  await page.route('**/api/assistant/stream', (route) => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'The assistant is temporarily unavailable.' }) }));
  await ask(page, 'show me a shawl');
  await expect(page.getByTestId('assistant-error')).toBeVisible();
  await page.goto('/products');
  await expect(page.getByRole('link', { name: /Ivory Merino Shawl/ })).toBeVisible();
});
