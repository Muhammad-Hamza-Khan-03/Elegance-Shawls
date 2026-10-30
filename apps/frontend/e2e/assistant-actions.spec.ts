import { expect, test, type Page } from '@playwright/test';

// Golden journey (M3-S3): ask -> proposal (inert) -> explicit confirm -> cart / enquiry reference -> human wa.me handoff.
// Uses the mock API only (e2e/mock-api.mjs): no model, no database, and wa.me is intercepted so no message can be sent.
const MOCK = 'http://127.0.0.1:4100';
const cart = (page: Page) => page.evaluate(() => JSON.parse(localStorage.getItem('elegance-shawls.cart.v1') ?? '[]') as { quantity: number; productId: string }[]);
// Counts only this page's session (tests run in parallel against one mock).
const sessions = new WeakMap<Page, string>();
const actions = async (page: Page) => {
  const log = await (await page.request.get(`${MOCK}/__actions`)).json() as { requests: { session_id: string; confirmed: boolean; action_type: string; executed: boolean }[] };
  const mine = log.requests.filter((r) => r.session_id === sessions.get(page));
  return { executions: mine.filter((r) => r.executed).length, requests: mine };
};

async function ask(page: Page, text = 'Show me a shawl') {
  page.on('request', (r) => { if (r.url().endsWith('/api/assistant/stream')) sessions.set(page, r.postDataJSON().session_id); });
  await page.goto('/e2e-assistant');
  await page.getByLabel('Message').fill(text);
  await page.getByRole('button', { name: 'Send' }).click();
  await expect(page.getByTestId('proposal')).toHaveCount(2);
}

test('a proposal does nothing until the user confirms, then adds to the cart exactly once', async ({ page }) => {
  await ask(page);
  const before = (await actions(page)).executions;
  await expect(page.getByText('Add Pashmina Shawl × 1 (PKR 3500 each) to your cart?')).toBeVisible();
  expect((await actions(page)).executions).toBe(before); // proposing executed nothing
  expect(await cart(page)).toEqual([]);

  const confirm = page.getByRole('button', { name: 'Confirm: add to cart' });
  await confirm.dblclick(); // a double press must still be a single action
  await expect(page.getByTestId('action-done')).toHaveText('Added to your cart.');
  await expect(confirm).toHaveCount(0);
  const lines = await cart(page);
  expect(lines).toHaveLength(1);
  expect(lines[0]).toMatchObject({ productId: '11111111-1111-4111-8111-111111111111', quantity: 1 });
  const after = await actions(page);
  expect(after.executions).toBe(before + 1);
  expect(after.requests.at(-1)).toMatchObject({ confirmed: true, action_type: 'add_to_cart' });

  await page.goto('/cart');
  await expect(page.getByRole('heading', { name: 'Pashmina Shawl' })).toBeVisible();
});

test('a confirmed enquiry shows its reference and only a human click opens the intercepted wa.me link', async ({ page }) => {
  const waRequests: string[] = [];
  await page.context().route('https://wa.me/**', (route) => { waRequests.push(route.request().url()); return route.fulfill({ body: 'wa' }); });
  await ask(page);
  const before = (await actions(page)).executions;
  await page.getByRole('button', { name: 'Confirm: start WhatsApp enquiry' }).click();
  await expect(page.getByTestId('action-done')).toContainText('Your enquiry reference is ES-GOLD42.');
  const link = page.getByTestId('whatsapp-handoff');
  await expect(link).toHaveAttribute('href', /^https:\/\/wa\.me\/923001234567\?text=.*Enquiry%20reference%3A%20ES-GOLD42/);
  expect((await actions(page)).executions).toBe(before + 1);
  expect(await cart(page)).toEqual([]); // an enquiry does not touch the cart
  expect(waRequests).toEqual([]); // nothing opened on its own

  const [popup] = await Promise.all([page.waitForEvent('popup'), link.click()]);
  await popup.waitForURL(/wa\.me/);
  expect(decodeURIComponent(popup.url())).toContain('Enquiry reference: ES-GOLD42');
});

test('a changed price is refused visibly, executes nothing and leaves the cart alone', async ({ page }) => {
  await ask(page, 'stale price please');
  const before = (await actions(page)).executions;
  await page.getByRole('button', { name: 'Confirm: add to cart' }).click();
  await expect(page.getByTestId('action-failed')).toContainText('price changed');
  expect((await actions(page)).executions).toBe(before);
  expect(await cart(page)).toEqual([]);
  await expect(page.getByRole('button', { name: 'Confirm: add to cart' })).toBeVisible(); // the person can retry or ask again
});

test('a failing execute call shows a failure and adds nothing', async ({ page }) => {
  await page.route('**/api/assistant/actions/execute', (route) => route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"down"}' }));
  await ask(page);
  await page.getByRole('button', { name: 'Confirm: add to cart' }).click();
  await expect(page.getByTestId('action-failed')).toBeVisible();
  expect(await cart(page)).toEqual([]);
});
