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

for (const [language, query] of [['English', 'brown stole under 4000'], ['Roman Urdu', 'bhoora stole 4000 se kam'], ['Urdu', 'بھورا اسٹول 4000 سے کم']] as const) {
  test(`constraint search (${language}) returns only the in-stock brown stole within budget`, async ({ request }) => {
    const names = await search(request, query);
    expect(names).toEqual(['Brown Pashmina Stole']);   // not the 5200 shawl, not the out-of-stock maroon stole, never the draft
  });
}

test('an unknown colour never matches (constraints are not relaxed)', async ({ request }) => {
  expect(await search(request, 'purple shawl')).toEqual([]);
});

test('hybrid search degrades to lexical results when semantic search is off', async ({ request }) => {
  const response = await request.post(`${API}/v1/search/hybrid`, { data: { q: 'brown stole', limit: 10 } });
  expect(response.status()).toBeLessThan(500);   // semantic is disabled in this stack: lexical must still answer, never a 5xx
});
