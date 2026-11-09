import { expect, test } from '@playwright/test';
import { API } from './helpers';

// Real FastAPI + PostgreSQL. Fixtures: e2e/seed_e2e.py. Nothing here is mocked.
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
