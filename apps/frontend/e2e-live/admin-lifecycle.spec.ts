import { Page, expect, test } from '@playwright/test';
import { adminApi, fixtureSuffix, image, live, signIn } from './live';

// #71 / #66 / #81: product lifecycle through the built-in admin UI against real
// FastAPI + MongoDB, with storefront and backend state checked at every step.

const productCard = (page: Page, slug: string) =>
  page.getByText(slug, { exact: false }).locator('xpath=ancestor::*[.//button[normalize-space()="Edit"]][1]');

const variantSection = (page: Page, index: number) =>
  page.locator('section').filter({ has: page.getByText(`Variant ${index}`, { exact: true }) });

test('admin creates, publishes, edits, unpublishes, republishes and archives a product', async ({ page, request }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'Admin lifecycle runs once on desktop.');
  const suffix = fixtureSuffix(testInfo);
  const slug = `qa-lifecycle-${suffix}`;
  const name = `QA Lifecycle ${suffix}`;
  const publicStatus = async () => (await request.get(`${live.api}/products/slug/${slug}`)).status();
  const publicListHas = async () =>
    ((await (await request.get(`${live.api}/products/?limit=100`)).json()).items as { slug: string }[]).some((item) => item.slug === slug);
  const adminProduct = async () => {
    const items = (await adminApi(request, 'GET', '/?limit=100')).items as { slug: string; _id: string }[];
    const match = items.find((item) => item.slug === slug);
    return match ? adminApi(request, 'GET', `/${match._id}`) : null;
  };

  await test.step('anonymous access is rejected everywhere', async () => {
    await page.goto('/admin/products');
    await expect(page).toHaveURL(/\/admin\/login/);
    expect((await page.request.get('/api/admin/products')).status()).toBe(401);
    expect((await page.request.post('/api/admin/products', { data: {} })).status()).toBe(401);
    expect((await request.post(`${live.api}/products/admin/`, { data: {} })).status()).toBe(401);
    expect((await request.post(`${live.api}/products/admin/`, { headers: { 'X-Admin-Key': 'wrong' }, data: {} })).status()).toBe(401);
  });

  await test.step('wrong key is refused, real key signs in', async () => {
    await signIn(page, 'not-the-admin-key');
    await expect(page.getByText('Invalid administrative credentials.')).toBeVisible();
    await signIn(page);
    await expect(page).toHaveURL(/\/admin\/dashboard$/);
  });

  await test.step('create a draft with two variants', async () => {
    await page.goto('/admin/products');
    await page.getByRole('button', { name: 'New product' }).first().click();
    await page.getByLabel('Product name').fill(name);
    await page.getByLabel('Slug').fill(slug);
    await page.getByLabel('Cover image URL').fill(image(name));
    await page.getByLabel('Item number').fill(`QA-${suffix}`);
    await page.getByLabel('Status').last().selectOption('draft');
    const first = variantSection(page, 1);
    await first.getByLabel('Name', { exact: true }).fill('Brown');
    await first.getByLabel('Color', { exact: true }).fill('Brown');
    await first.getByLabel('Image URL', { exact: true }).fill(image(`${name} Brown`));
    await first.getByLabel('Price', { exact: true }).fill('4500');
    await first.getByLabel('Stock', { exact: true }).fill('3');
    await page.getByRole('button', { name: 'Add variant' }).click();
    const second = variantSection(page, 2);
    await second.getByLabel('Name', { exact: true }).fill('Ivory');
    await second.getByLabel('Color', { exact: true }).fill('Ivory');
    await second.getByLabel('Image URL', { exact: true }).fill(image(`${name} Ivory`));
    await second.getByLabel('Price', { exact: true }).fill('4800');
    await second.getByLabel('Stock', { exact: true }).fill('0');
    await page.getByRole('button', { name: 'Create product' }).click();
    await expect(page.getByText(`${name} created successfully.`)).toBeVisible();

    const saved = await adminProduct();
    expect(saved.status).toBe('draft');
    expect(saved.variants.map((variant: { stock_status: string }) => variant.stock_status)).toEqual(['In stock', 'Out of stock']);
    expect(await publicStatus()).toBe(404);
    expect(await publicListHas()).toBe(false);
    expect((await page.goto(`/product/${slug}`))?.status()).toBe(404);
  });

  await test.step('cross-origin admin mutation is refused before reaching the backend', async () => {
    const saved = await adminProduct();
    const response = await page.request.fetch(`/api/admin/products/${saved._id}/status`, {
      method: 'PATCH',
      headers: { Origin: 'https://attacker.example' },
      data: { status: 'active' },
    });
    expect(response.status()).toBe(403);
    expect((await adminProduct()).status).toBe('draft');
  });

  await test.step('publish makes it visible on the storefront', async () => {
    await page.goto('/admin/products');
    await productCard(page, slug).getByRole('button', { name: 'Publish' }).click();
    await expect(page.getByText(`${name} moved to live.`)).toBeVisible();
    expect(await publicStatus()).toBe(200);
    expect(await publicListHas()).toBe(true);

    await page.goto(`/product/${slug}`);
    await expect(page.getByRole('heading', { name })).toBeVisible();
    await expect(page.getByText('PKR 4,500').first()).toBeVisible();
    await expect(page.getByRole('radio', { name: /Brown/ })).toBeEnabled();
    await expect(page.getByRole('radio', { name: /Ivory/ })).toBeDisabled();
    await expect(page.getByRole('img', { name: new RegExp(name) }).first()).toHaveAttribute('src', /placehold\.co/);
  });

  await test.step('editing text and stock keeps variant identifiers stable', async () => {
    const before = await adminProduct();
    await page.goto('/admin/products');
    await productCard(page, slug).getByRole('button', { name: 'Edit' }).click();
    await page.getByLabel('Main description').fill('Edited during live QA.');
    await variantSection(page, 1).getByLabel('Stock', { exact: true }).fill('1');
    await page.getByRole('button', { name: 'Save product' }).click();
    await expect(page.getByText(`${name} updated successfully.`)).toBeVisible();

    const after = await adminProduct();
    expect(after.variants.map((variant: { _id: string }) => variant._id)).toEqual(before.variants.map((variant: { _id: string }) => variant._id));
    expect(after.main_description).toBe('Edited during live QA.');
    expect(after.variants[0].stock).toBe(1);
    await page.goto(`/product/${slug}`);
    await expect(page.getByText('1 available').first()).toBeVisible();
  });

  await test.step('unpublish hides it; republish restores it', async () => {
    await page.goto('/admin/products');
    await productCard(page, slug).getByRole('button', { name: 'Unpublish' }).click();
    await expect(page.getByText(`${name} moved to draft.`)).toBeVisible();
    expect(await publicStatus()).toBe(404);
    expect(await publicListHas()).toBe(false);

    await productCard(page, slug).getByRole('button', { name: 'Publish' }).click();
    await expect(page.getByText(`${name} moved to live.`)).toBeVisible();
    expect(await publicStatus()).toBe(200);
  });

  await test.step('archive removes it from every public surface', async () => {
    await productCard(page, slug).getByRole('button', { name: 'Archive' }).click();
    await expect(page.getByText(`${name} archived.`)).toBeVisible();
    expect((await adminProduct()).status).toBe('archived');
    expect(await publicStatus()).toBe(404);
    expect(await publicListHas()).toBe(false);
    expect((await page.goto(`/product/${slug}`))?.status()).toBe(404);
  });

  await test.step('sign out ends the session', async () => {
    expect((await page.request.delete('/api/admin/session')).status()).toBe(200);
    expect((await page.request.get('/api/admin/products')).status()).toBe(401);
  });
});
