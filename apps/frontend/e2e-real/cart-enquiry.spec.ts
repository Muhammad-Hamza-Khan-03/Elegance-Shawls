import { expect, test } from '@playwright/test';
import { API, WEB, adminLogin, backendSession, product } from './helpers';

test('cart -> real enquiry reference -> encoded wa.me handoff (the link is intercepted, nothing is sent)', async ({ page }) => {
  const sent: string[] = [];
  await page.context().route('https://wa.me/**', (route) => { sent.push(route.request().url()); return route.fulfill({ body: 'wa' }); });
  await page.goto('/product/e2e-brown-pashmina-stole');
  await page.getByRole('button', { name: 'Add to cart' }).click();
  await expect(page.getByRole('link', { name: /Cart/ }).last()).toContainText('1');
  await page.goto('/cart');
  await expect(page.getByRole('heading', { name: 'Brown Pashmina Stole' })).toBeVisible();
  const [popup] = await Promise.all([page.waitForEvent('popup'), page.getByRole('button', { name: 'Send cart on WhatsApp' }).click()]);
  await popup.waitForURL(/wa\.me/);
  const message = decodeURIComponent(popup.url().split('?text=')[1]);
  const reference = /Enquiry reference: (ES-[A-Z0-9]+)/.exec(message)?.[1];
  expect(reference, message).toBeTruthy();

  // The reference is a real row: staff can look it up, and it stores server-validated price/quantity (not an order).
  await adminLogin(page);
  const lookup = await page.request.get(`${WEB}/api/admin/enquiries/${reference}`);
  expect(lookup.status()).toBe(200);
  const body = await lookup.json();
  expect(body.total).toBe(3500);
  expect(body.items[0]).toMatchObject({ quantity: 1, unit_price: 3500 });
  expect(sent).toHaveLength(1);
});

test('the server revalidates price, stock and availability (stale carts are refused with 409)', async ({ request }) => {
  const stole = await product(request, 'e2e-brown-pashmina-stole');
  const sold = await product(request, 'e2e-maroon-silk-stole');
  const last = await product(request, 'e2e-last-piece-scarf');
  const line = (p: typeof stole, over: Record<string, unknown> = {}) => ({ product_id: p._id, variant_id: p.variants[0]._id, quantity: 1, unit_price: p.variants[0].price, currency: 'PKR', ...over });
  const post = (items: unknown[]) => request.post(`${WEB}/api/enquiries`, { headers: { origin: WEB }, data: { items } });

  expect((await post([line(stole, { unit_price: 100 })])).status()).toBe(409);    // client lies about the price
  expect((await post([line(sold)])).status()).toBe(409);                           // out of stock
  expect((await post([line(last, { quantity: 2 })])).status()).toBe(409);          // more than the single unit in stock
  expect((await post([line(stole, { variant_id: '00000000-0000-4000-8000-000000000000' })])).status()).toBeGreaterThanOrEqual(400);
  expect((await post([line(stole)])).status()).toBe(201);                          // control: a valid cart works
});

test('an admin price change between adding and sending is caught', async ({ request }) => {
  const stole = await product(request, 'e2e-ivory-merino-shawl');
  const item = { product_id: stole._id, variant_id: stole.variants[0]._id, quantity: 1, unit_price: stole.variants[0].price, currency: 'PKR' };
  expect((await request.post(`${API}/v1/enquiries`, { data: { items: [item] } })).status()).toBe(201);
  const owner = await backendSession(request);
  const changed = await request.put(`${API}/products/admin/${stole._id}`, { headers: owner, data: await updatePayload(request, stole._id, owner, 4300) });
  expect(changed.status(), await changed.text()).toBeLessThan(300);
  try {
    expect((await request.post(`${API}/v1/enquiries`, { data: { items: [item] } })).status()).toBe(409);
  } finally {   // restore so the suite stays order-independent
    await request.put(`${API}/products/admin/${stole._id}`, { headers: owner, data: await updatePayload(request, stole._id, owner, 4200) });
  }
});

async function updatePayload(request: import('@playwright/test').APIRequestContext, id: string, owner: Record<string, string>, price: number) {
  const current = await (await request.get(`${API}/products/admin/${id}`, { headers: owner })).json();
  const { _id, id: _ignore, is_active, created_at, updated_at, ...rest } = current;   // eslint-disable-line @typescript-eslint/no-unused-vars
  const variants = current.variants.map((v: Record<string, unknown>) =>
    ({ id: v._id, name: v.name, color: v.color, size: v.size, image_url: v.image_url, price, currency: v.currency, stock: v.stock, stock_status: v.stock_status, description: v.description }));
  return { ...rest, price, variants };
}
