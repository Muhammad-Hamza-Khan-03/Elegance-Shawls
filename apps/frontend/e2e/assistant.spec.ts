import { expect, test, type Page } from '@playwright/test';

const PRODUCT_ID = '0b8f2a54-3c1d-4e6a-9f10-2a7d5c8e1b34';

const frame = (seq: number, event: string, data: unknown) => `id: ${seq}\nevent: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

// Stubs the same-origin stream; `build` receives the client's real session/key so `start` round-trips them.
async function stubStream(page: Page, build: (req: { session_id: string; idempotency_key: string }) => string, status = 200, contentType = 'text/event-stream') {
  const requests: unknown[] = [];
  await page.route('**/api/assistant/stream', async (route) => {
    const req = route.request().postDataJSON();
    requests.push(req);
    await route.fulfill({ status, contentType, body: build(req) });
  });
  return requests;
}

// The Next route announcer is also role=alert, so scope to the chat form.
const alert = (page: Page) => page.locator('form').getByRole('alert');

const start = (r: { session_id: string; idempotency_key: string }) =>
  frame(0, 'start', { protocol: 1, session_id: r.session_id, idempotency_key: r.idempotency_key, context: {} });

async function ask(page: Page) {
  await page.goto('/e2e-assistant');
  await page.getByLabel('Message').fill('Show me a shawl');
  await page.getByRole('button', { name: 'Send' }).click();
}

// Nothing the assistant proposes may become a control; only the chat's own Send/Stop buttons exist.
async function expectNoActionControls(page: Page) {
  const form = page.locator('form');
  await expect(form.getByRole('button').filter({ hasNotText: /Speak|Listening/ })).toHaveText(['Send', 'Stop']);
  await expect(form.getByRole('link')).toHaveCount(0);
}

test('streams text and a product, and shows a validated proposal as information only', async ({ page }) => {
  await stubStream(page, (r) => start(r)
    + frame(1, 'text', { delta: 'Here is ' }) + frame(2, 'text', { delta: '<b>a shawl</b>' })
    + frame(3, 'product', { product_id: PRODUCT_ID, name: 'Classic Wool Shawl', price: 4500, currency: 'PKR' })
    + frame(4, 'proposal', { session_id: r.session_id, action_type: 'add_to_cart', idempotency_key: r.idempotency_key, decision: { outcome: 'validated', reason: 'ok', executed: false, idempotency_key: r.idempotency_key, replayed: false } })
    + frame(5, 'done', {}));
  await ask(page);
  await expect(page.getByText('Here is <b>a shawl</b>')).toBeVisible(); // escaped, not parsed as HTML
  await expect(page.getByTestId('product')).toContainText('Classic Wool Shawl');
  await expect(page.getByTestId('product')).toContainText('PKR 4500');
  await expect(page.getByTestId('proposal')).toHaveAttribute('data-outcome', 'validated');
  await expect(page.getByTestId('proposal')).toContainText('nothing has been done yet');
  await expect(alert(page)).toHaveCount(0);
  await expectNoActionControls(page);
});

test('renders a rejected proposal safely', async ({ page }) => {
  await stubStream(page, (r) => start(r)
    + frame(1, 'proposal', { session_id: r.session_id, action_type: 'start_whatsapp_enquiry', idempotency_key: r.idempotency_key, decision: { outcome: 'rejected', reason: 'out_of_stock', executed: false, idempotency_key: r.idempotency_key, replayed: false } })
    + frame(2, 'proposal', { session_id: r.session_id, action_type: 'drop_database', idempotency_key: null, decision: { outcome: 'validated', reason: 'ok', executed: false, idempotency_key: null, replayed: false } })
    + frame(3, 'done', {}));
  await ask(page);
  const proposals = page.getByTestId('proposal');
  await expect(proposals).toHaveCount(2);
  for (const p of await proposals.all()) {
    await expect(p).toHaveAttribute('data-outcome', 'rejected'); // an unknown action is never believed, even if "validated"
    await expect(p).toContainText('not accepted, so nothing was done');
  }
  await expectNoActionControls(page);
});

test('an executed proposal or malformed frame ends the stream as an error', async ({ page }) => {
  await stubStream(page, (r) => start(r)
    + frame(1, 'proposal', { session_id: r.session_id, action_type: 'add_to_cart', idempotency_key: r.idempotency_key, decision: { outcome: 'validated', reason: 'ok', executed: true, idempotency_key: r.idempotency_key, replayed: false } }));
  await ask(page);
  await expect(alert(page)).toHaveText('Something went wrong. Please try again.');
  await expect(page.getByTestId('proposal')).toHaveCount(0);
  await expectNoActionControls(page);
});

test('a start frame that does not round-trip the request metadata is rejected', async ({ page }) => {
  await stubStream(page, () => frame(0, 'start', { protocol: 1, session_id: 'sess_other', idempotency_key: 'idem_aaaaaaaaaaaaaaaa', context: {} }) + frame(1, 'text', { delta: 'leaked' }));
  await ask(page);
  await expect(alert(page)).toBeVisible();
  await expect(page.getByText('leaked')).toHaveCount(0);
});

test('a stream cut off before done shows an interruption error', async ({ page }) => {
  await stubStream(page, (r) => start(r) + frame(1, 'text', { delta: 'Partial' }));
  await ask(page);
  await expect(page.getByText('Partial')).toBeVisible();
  await expect(alert(page)).toHaveText('Something went wrong. Please try again.');
});

test('a server-sent provider error is mapped to friendly text', async ({ page }) => {
  await stubStream(page, (r) => start(r) + frame(1, 'error', { code: 'provider_error' }));
  await ask(page);
  await expect(alert(page)).toHaveText('The assistant had a problem. Please try again.');
});

test('a non-stream or failing response shows the unavailable message', async ({ page }) => {
  await stubStream(page, () => '{"detail":"nope"}', 503, 'application/json');
  await ask(page);
  await expect(alert(page)).toHaveText('The assistant is unavailable right now.');
  await expectNoActionControls(page);
});

test('speech only fills the box; the request is marked voice until the customer types', async ({ page }) => {
  await page.addInitScript(() => {
    class Fake {
      lang = ''; interimResults = false; onresult: ((e: unknown) => void) | null = null; onend: (() => void) | null = null; onerror: (() => void) | null = null;
      start() { setTimeout(() => { this.onresult?.({ results: [[{ transcript: 'red shawl under 2000' }]] }); this.onend?.(); }); }
      stop() {}
    }
    for (const name of ['SpeechRecognition', 'webkitSpeechRecognition']) Object.defineProperty(window, name, { value: Fake, configurable: true });
  });
  const requests = (await stubStream(page, (r) => start(r) + frame(1, 'done', { events: 1 }))) as { context: Record<string, string>; message: string }[];
  await page.goto('/e2e-assistant');
  await page.getByRole('button', { name: 'Speak your request' }).click();
  await expect(page.getByLabel('Message')).toHaveValue('red shawl under 2000');
  expect(requests).toHaveLength(0);                       // nothing is sent until the customer presses Send
  await page.getByRole('button', { name: 'Send' }).click();
  await expect.poll(() => requests.length).toBe(1);
  expect(requests[0].context.input).toBe('voice');
  await page.getByLabel('Message').fill('red shawl under 3000');
  await page.getByRole('button', { name: 'Send' }).click();
  await expect.poll(() => requests.length).toBe(2);
  expect(requests[1].context.input).toBeUndefined();
});
