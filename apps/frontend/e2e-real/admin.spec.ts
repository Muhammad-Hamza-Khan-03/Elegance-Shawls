import { expect, test } from '@playwright/test';
import { API, OWNER, WEB, adminLogin, backendSession } from './helpers';

const write = { origin: WEB };

test('wrong password is refused and anonymous admin access is redirected', async ({ page }) => {
  await page.goto('/admin/dashboard');
  await expect(page).toHaveURL(/\/admin\/login/);
  await page.getByLabel('Email').fill(OWNER.email);
  await page.getByLabel('Password').fill('definitely-the-wrong-password');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'Invalid email or password.' })).toBeVisible();   // not Next's route announcer
  await expect(page).toHaveURL(/\/admin\/login/);
  expect((await page.context().cookies()).some((c) => c.name === 'es_admin_session')).toBe(false);   // no session was issued
});

test('owner signs in with a real account and reaches the dashboard', async ({ page }) => {
  await page.goto('/admin/login');
  await page.getByLabel('Email').fill(OWNER.email);
  await page.getByLabel('Password').fill(OWNER.password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/admin\/dashboard$/);
  const cookie = (await page.context().cookies()).find((c) => c.name === 'es_admin_session');
  expect(cookie?.httpOnly).toBe(true);
  expect(cookie?.value.startsWith('es1.')).toBe(true);
});

test('product lifecycle through the admin proxy: create -> public -> draft -> hidden -> archived', async ({ page, request }) => {
  await adminLogin(page);
  const slug = `e2e-lifecycle-${Date.now()}`;
  const created = await page.request.post(`${WEB}/api/admin/products`, {
    headers: write,
    data: { name: 'Lifecycle Test Shawl', slug, cover_image_url: 'https://picsum.photos/seed/lifecycle/600/800', category: 'shawls', status: 'active',
            variants: [{ name: 'Teal', color: 'Teal', image_url: 'https://picsum.photos/seed/lifecycle-v/600/800', price: 3000, stock: 2 }] },
  });
  expect(created.status(), await created.text()).toBe(201);
  const id = (await created.json())._id;
  expect((await request.get(`${API}/products/slug/${slug}`)).status()).toBe(200);

  const setStatus = (status: string) => page.request.patch(`${WEB}/api/admin/products/${id}/status`, { headers: write, data: { status } });
  expect((await setStatus('draft')).status()).toBe(200);
  expect((await request.get(`${API}/products/slug/${slug}`)).status()).toBe(404);   // a draft is not public
  expect((await setStatus('active')).status()).toBe(200);
  expect((await request.get(`${API}/products/slug/${slug}`)).status()).toBe(200);
  expect((await page.request.delete(`${WEB}/api/admin/products/${id}`, { headers: write })).status()).toBe(200);   // soft delete = archive
  expect((await request.get(`${API}/products/slug/${slug}`)).status()).toBe(404);

  const owner = await backendSession(request);   // mutations were attributed to the individual account, not a shared key
  const me = await (await request.get(`${API}/v1/admin/auth/me`, { headers: owner })).json();
  const audit = await request.get(`${API}/v1/admin/audit`, { headers: owner });
  expect(audit.status()).toBe(200);
  const rows: { actor_type: string; actor_id: string }[] = (await audit.json()).items;
  expect(rows.some((row) => row.actor_type === 'admin' && row.actor_id === me.account.id)).toBe(true);
});

test('RBAC: a viewer can read but is refused every write, and the refusal is audited against that viewer', async ({ page, request }) => {
  const owner = await backendSession(request);
  const viewer = { email: `viewer-${Date.now()}@e2e.test`, password: 'e2e-viewer-Passw0rd-fixture' };
  const made = await request.post(`${API}/v1/admin/accounts`, { headers: owner, data: { ...viewer, role: 'viewer' } });
  expect(made.status(), await made.text()).toBe(201);
  const viewerId = (await made.json()).id;
  await adminLogin(page, viewer);
  expect((await page.request.get(`${WEB}/api/admin/products`)).status()).toBe(200);
  expect((await page.request.post(`${WEB}/api/admin/products`, { headers: write, data: {} })).status()).toBe(403);
  expect((await request.get(`${API}/v1/admin/accounts`, { headers: await backendSession(request, viewer) })).status()).toBe(403);   // viewers cannot manage accounts

  const audit = await request.get(`${API}/v1/admin/audit?limit=200`, { headers: owner });
  expect(audit.status()).toBe(200);
  const denials = ((await audit.json()).items as { actor_id: string; outcome: string; action: string; detail: { status: number } | null }[])
    .filter((row) => row.actor_id === viewerId && row.outcome === 'denied');
  // exactly the two refused requests, each recorded once (neither endpoint has path parameters, so template naming is not exercised), as 403, against this viewer
  expect(denials.map((row) => row.action).sort()).toEqual(['GET /v1/admin/accounts', 'POST /products/admin/']);
  for (const row of denials) expect(row.detail?.status).toBe(403);
});
