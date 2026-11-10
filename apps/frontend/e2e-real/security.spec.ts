import { expect, test } from '@playwright/test';
import { API, WEB, adminLogin } from './helpers';

test('admin proxy: no cookie or a forged cookie never reaches the backend', async ({ request }) => {
  expect((await request.get(`${WEB}/api/admin/products`)).status()).toBe(401);
  const forged = await request.get(`${WEB}/api/admin/products`, { headers: { cookie: 'es_admin_session=es1.forged-token-value' } });
  expect(forged.status()).toBe(401);
  const forgedWrite = await request.post(`${WEB}/api/admin/products`, { headers: { origin: WEB, cookie: 'es_admin_session=es1.forged-token-value' }, data: {} });
  expect(forgedWrite.status()).toBe(401);
});

test('admin proxy: a VALID session is still refused on writes from a foreign or missing origin (CSRF)', async ({ page }) => {
  await adminLogin(page);   // real session cookie in this context
  const write = (headers: Record<string, string>) => page.request.post(`${WEB}/api/admin/products`, { headers, data: {} });
  expect((await write({ origin: 'https://evil.example' })).status()).toBe(403);
  expect((await write({})).status()).toBe(403);                                  // no Origin header at all
  expect((await page.request.get(`${WEB}/api/admin/products`)).status()).toBe(200);   // reads are unaffected: the session itself is valid
});

test('backend admin routes refuse anonymous callers, a bogus session and the retired shared key', async ({ request }) => {
  for (const path of ['/products/admin/', '/v1/admin/accounts', '/v1/admin/audit', '/v1/admin/enquiries?reference=ES-NOPE22', '/v1/admin/jobs/00000000-0000-4000-8000-000000000000']) {
    expect((await request.get(`${API}${path}`)).status(), path).toBe(401);
  }
  expect((await request.get(`${API}/products/admin/`, { headers: { 'X-Admin-Session': 'es1.not-a-real-session' } })).status()).toBe(401);
  expect((await request.get(`${API}/products/admin/`, { headers: { 'X-Admin-Key': 'anything' } })).status()).toBe(401);   // legacy key is closed in this stack
});

test('public catalogue never exposes non-public rows or admin-only fields', async ({ request }) => {
  const list = await (await request.get(`${API}/products/?limit=100`)).json();
  const names = list.items.map((p: { name: string }) => p.name);
  expect(names).toContain('Brown Pashmina Stole');
  expect(names).not.toContain('Draft Green Shawl');
  expect(JSON.stringify(list)).not.toMatch(/password|token|secret/i);
});

test('malformed input is rejected, not a 500: bad cursor, bad enquiry body, oversized assistant body', async ({ request }) => {
  expect((await request.get(`${API}/products/?cursor=tampered`)).status()).toBe(400);
  expect((await request.post(`${API}/v1/enquiries`, { data: { items: [] } })).status()).toBe(422);
  expect((await request.post(`${API}/v1/enquiries`, { data: { items: [{ product_id: 'x' }], extra: 1 } })).status()).toBe(422);
  expect((await request.post(`${WEB}/api/assistant/stream`, { headers: { origin: WEB, 'content-type': 'application/json' }, data: 'x'.repeat(5000) })).status()).toBe(413);
  expect((await request.post(`${WEB}/api/assistant/stream`, { headers: { origin: 'https://evil.example', 'content-type': 'application/json' }, data: '{}' })).status()).toBe(403);
});

test('liveness and readiness reflect the real database', async ({ request }) => {
  expect((await request.get(`${API}/health/`)).status()).toBe(200);
  const ready = await request.get(`${API}/ready/`);
  expect(ready.status()).toBe(200);
});
