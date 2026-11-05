import { expect, test } from '@playwright/test';

// Panel-on tests need the dev server built with the flag: ASSISTANT_E2E=1 npx playwright test e2e/assistant.spec.ts
const on = Boolean(process.env.ASSISTANT_E2E);

test.describe('assistant flag off', () => {
  test.skip(on, 'flag is on');
  test('panel is absent, routes are 404, cart is unaffected', async ({ page, request }) => {
    await page.goto('/');
    await expect(page.getByRole('button', { name: 'اسسٹنٹ' })).toHaveCount(0);
    const res = await request.post('/api/assistant/stream', { data: { session_id: 's', message: 'x' }, headers: { origin: 'http://127.0.0.1:3100' } });
    expect(res.status()).toBe(404);
    await page.goto('/product/light-silk-stole');
    await page.getByRole('button', { name: 'Add to cart' }).click();
    await expect(page.getByRole('link', { name: /Cart/ }).last()).toContainText('1');
  });
});

test.describe('assistant flag on', () => {
  test.skip(!on, 'set ASSISTANT_E2E=1');

  test('RTL panel; add_to_cart needs confirmation and is applied once', async ({ page }) => {
    let executeCalls = 0;
    page.on('request', (r) => { if (r.url().endsWith('/api/assistant/actions/execute')) executeCalls++; });
    await page.goto('/');
    await page.getByRole('button', { name: 'اسسٹنٹ' }).click();
    const panel = page.getByTestId('assistant-panel');
    await expect(panel).toHaveAttribute('dir', 'rtl');
    await panel.getByLabel('پیغام').fill('add to cart');
    await panel.getByRole('button', { name: 'بھیجیں' }).click();
    const card = panel.getByTestId('proposal-card');
    await expect(card).toContainText('add_to_cart');
    expect(executeCalls).toBe(0); // proposal-only until confirmed
    await expect(page.getByRole('link', { name: /Cart/ }).last()).not.toContainText('1');
    await card.getByRole('button', { name: 'تصدیق کریں' }).click();
    await expect(card.getByRole('status')).toContainText('کارٹ میں شامل');
    await expect(page.getByRole('link', { name: /Cart/ }).last()).toContainText('1');
    await expect(card.getByRole('button', { name: 'تصدیق کریں' })).toHaveCount(0);
    expect(executeCalls).toBe(1);
  });

  test('start_whatsapp_order is an inert handoff to the cart', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'اسسٹنٹ' }).click();
    const panel = page.getByTestId('assistant-panel');
    await panel.getByLabel('پیغام').fill('start order');
    await panel.getByRole('button', { name: 'بھیجیں' }).click();
    await panel.getByRole('button', { name: 'تصدیق کریں' }).click();
    await expect(panel.getByRole('status')).toContainText('ابھی نہیں بھیجا');
    await expect(panel.getByRole('link', { name: 'کارٹ' })).toHaveAttribute('href', '/cart');
    await expect(page.getByRole('link', { name: /Cart/ }).last()).not.toContainText('1');
  });

  test('silent relaxation is shown as rejected with no confirm', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'اسسٹنٹ' }).click();
    const panel = page.getByTestId('assistant-panel');
    await panel.getByLabel('پیغام').fill('relax');
    await panel.getByRole('button', { name: 'بھیجیں' }).click();
    await expect(panel.getByRole('alert')).toContainText('silent_relaxation');
    await expect(panel.getByRole('button', { name: 'تصدیق کریں' })).toHaveCount(0);
  });
});
