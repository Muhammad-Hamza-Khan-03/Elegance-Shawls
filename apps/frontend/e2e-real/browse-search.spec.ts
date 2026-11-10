import { expect, test } from '@playwright/test';
import { API } from './helpers';

// Real FastAPI + PostgreSQL. Fixtures: apps/backend/scripts/seed_e2e.py. Nothing here is mocked.
const search = async (request: import('@playwright/test').APIRequestContext, q: string) => {
  const names: string[] = [];
  let cursor: string | null = null;
  do {   // a page can be short while next_cursor is set (architecture doc): keep paging until null
    const response = await request.post(`${API}/v1/search`, { data: { q, limit: 50, ...(cursor ? { cursor } : {}) } });
    expect(response.status()).toBe(200);
    const body = await response.json();
    names.push(...body.items.map((item: { product: { name: string } }) => item.product.name));
    cursor = body.next_cursor;
  } while (cursor);
  return names;
};

test('storefront lists catalogue rows from PostgreSQL and hides drafts', async ({ page }) => {
  await page.goto('/products');
  await expect(page.getByRole('heading', { name: 'Shop the collection' })).toBeVisible();
  await expect(page.getByRole('link', { name: /Brown Pashmina Stole/ })).toBeVisible();
  await expect(page.getByRole('link', { name: /Ivory Merino Shawl/ })).toBeVisible();
  await expect(page.getByRole('link', { name: /Draft Green Shawl/ })).toHaveCount(0);
  await page.getByLabel('Search').fill('pashmina');
  await expect(page.getByRole('link', { name: /Brown Pashmina Stole/ })).toBeVisible();
  await expect(page.getByRole('link', { name: /Ivory Merino Shawl/ })).toBeHidden();
});

test('product page renders the real record and an unknown slug is a 404', async ({ page, request }) => {
  await page.goto('/product/e2e-brown-pashmina-stole');
  await expect(page.getByRole('heading', { name: 'Brown Pashmina Stole' })).toBeVisible();
  expect((await request.get(`${API}/products/slug/e2e-draft-green-shawl`)).status()).toBe(404);   // draft is not public
  await page.goto('/product/e2e-draft-green-shawl');
  await expect(page.getByRole('heading', { name: 'This page could not be found.' })).toBeVisible();
});

const BROWN_STOLES = ['Brown Jamawar Stole', 'Brown Pashmina Stole'];

// Brown stoles exist at 3500 (in stock) and 4500 (in stock); a brown shawl at 5200 and a sold-out maroon stole are decoys.
// The budget therefore decides the answer: if max_price/min_price were ignored these equality checks would fail.
for (const [language, query] of [['English', 'brown stole under 4000'], ['Roman Urdu', 'bhoora stole 4000 se kam'], ['Urdu', 'بھورا اسٹول 4000 سے کم']] as const) {
  test(`constraint search (${language}) under budget returns exactly the 3500 brown stole`, async ({ request }) => {
    expect(await search(request, query)).toEqual(['Brown Pashmina Stole']);
  });
}

for (const [language, query] of [['English', 'brown stole above 4000'], ['Roman Urdu', 'bhoora stole 4000 se zyada'], ['Urdu', 'بھورا اسٹول 4000 سے زیادہ']] as const) {
  test(`constraint search (${language}) over budget returns exactly the 4500 brown stole`, async ({ request }) => {
    expect(await search(request, query)).toEqual(['Brown Jamawar Stole']);
  });
}

test('without a budget both brown stoles match, never the brown shawl, another colour or the draft', async ({ request }) => {
  expect((await search(request, 'brown stole')).sort()).toEqual(BROWN_STOLES);
});

test('"in stock" is a hard constraint: a sold-out piece matches only when stock is not asked for', async ({ request }) => {
  expect(await search(request, 'maroon stole')).toEqual(['Maroon Silk Stole']);              // stock is not filtered unless the customer says so
  for (const query of ['maroon stole in stock', 'maroon stole available', 'maroon stole maujood', 'مرون اسٹول موجود']) {
    const names = await search(request, query);
    expect(names, query).not.toContain('Maroon Silk Stole');                                    // the only maroon stole has stock 0
  }
  expect((await search(request, 'brown stole in stock')).sort()).toEqual(BROWN_STOLES);  // in-stock pieces still match
});

test('an unknown colour never matches (constraints are not relaxed)', async ({ request }) => {
  expect(await search(request, 'purple shawl')).toEqual([]);
});

test('hybrid search with semantic search off answers lexically and says so', async ({ request }) => {
  const response = await request.post(`${API}/v1/search/hybrid`, { data: { q: 'brown stole under 4000', limit: 10 } });
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body.semantic).toBe(false);   // no vector branch ran: order is lexical-only
  expect(body.items.map((item: { product: { name: string } }) => item.product.name)).toEqual(['Brown Pashmina Stole']);   // hard constraints still apply
  expect(body.unsupported).toEqual([]);
});

// Public variant filters of `GET /v1/search` (colour / min_price / max_price / in_stock), tested directly with no free-text query: each assertion is discriminating against the seed
// (prices 1800..5200, one out-of-stock product at 2900, one draft at 3900 that must never appear).
const listNames = async (request: import('@playwright/test').APIRequestContext, query: string) => {
  const response = await request.get(`${API}/v1/search?limit=100&${query}`);
  expect(response.status(), query).toBe(200);
  return ((await response.json()).items as { name: string }[]).map((p) => p.name).sort();
};

test('search filters: max_price is an inclusive upper bound and never shows drafts', async ({ request }) => {
  expect(await listNames(request, 'max_price=3500')).toEqual(['Brown Pashmina Stole', 'Last Piece Scarf', 'Maroon Silk Stole']);   // 3500 included; 3900 draft, 4200+ excluded
  expect(await listNames(request, 'max_price=1799')).toEqual([]);
});

test('search filters: min_price is an inclusive lower bound', async ({ request }) => {
  expect(await listNames(request, 'min_price=4500')).toEqual(['Brown Jamawar Stole', 'Brown Wool Shawl']);                       // 4500 included, 4200 excluded
  expect(await listNames(request, 'min_price=4200&max_price=4500')).toEqual(['Brown Jamawar Stole', 'Ivory Merino Shawl']);
});

test('search filters: in_stock drops products whose variants have no stock, and combines with price on one variant', async ({ request }) => {
  const all = await listNames(request, '');
  expect(all).toContain('Maroon Silk Stole');
  const inStock = await listNames(request, 'in_stock=true');
  expect(inStock).not.toContain('Maroon Silk Stole');                                   // stock 0
  expect(inStock).toHaveLength(all.length - 1);
  expect(await listNames(request, 'in_stock=true&max_price=3000')).toEqual(['Last Piece Scarf']);   // Maroon (2900) is cheap enough but out of stock
});

test('search filters: colour filter is exact and combines with other filters; bad filters are 422', async ({ request }) => {
  expect(await listNames(request, 'colour=brown')).toEqual(['Brown Jamawar Stole', 'Brown Pashmina Stole', 'Brown Wool Shawl']);
  expect(await listNames(request, 'colour=brown&max_price=4000')).toEqual(['Brown Pashmina Stole']);
  expect(await listNames(request, 'colour=ivory&in_stock=true')).toEqual(['Ivory Merino Shawl']);
  expect((await request.get(`${API}/v1/search?colour=not-a-colour`)).status()).toBe(422);
  expect((await request.get(`${API}/v1/search?min_price=5000&max_price=1000`)).status()).toBe(422);
});
