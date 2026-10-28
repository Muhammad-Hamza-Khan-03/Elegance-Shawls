import { Page, expect, test } from '@playwright/test';
import { adminApi, createProduct, fixtureSuffix, interceptWhatsApp, live, productPayload, whatsappMessage } from './live';

// #72 / #75 / #74: customer browsing and WhatsApp handoff on desktop and mobile
// against the real backend, including catalogue changes after add-to-cart.

type Fixture = { id: string; slug: string; name: string; variants: { _id: string }[] };

const addToCart = async (page: Page, slug: string, quantity = 1) => {
  await page.goto(`/product/${slug}`);
  for (let added = 1; added < quantity; added += 1) await page.getByLabel('Increase quantity').click();
  await page.getByRole('button', { name: 'Add to cart' }).click();
};

const checkoutLink = (page: Page) => page.getByRole('link', { name: 'Send cart on WhatsApp' });

test.describe('customer WhatsApp ordering', () => {
  let shawl: Fixture;
  let stole: Fixture;

  test.beforeEach(async ({ request, context }, testInfo) => {
    const suffix = fixtureSuffix(testInfo);
    const create = async (slug: string, name: string, variants: Parameters<typeof productPayload>[2]) => {
      const created = await createProduct(request, productPayload(slug, name, variants));
      return { id: created._id, slug, name, variants: created.variants } as Fixture;
    };
    shawl = await create(`qa-shawl-${suffix}`, `QA Shawl ${suffix}`, [
      { name: 'Brown', color: 'Brown', price: 4500, stock: 3 },
      { name: 'Black', color: 'Black', price: 4800, stock: 0 },
    ]);
    stole = await create(`qa-stole-${suffix}`, `QA Stole ${suffix}`, [{ name: 'Beige', color: 'Beige', price: 2800, stock: 5 }]);
    await interceptWhatsApp(context);
  });

  test.afterEach(async ({ request }) => {
    for (const fixture of [shawl, stole]) await adminApi(request, 'DELETE', `/${fixture.id}`);
  });

  test('browse, search and order a single product', async ({ page }, testInfo) => {
    await page.goto('/products');
    await page.getByLabel('Search').fill(shawl.name);
    await expect(page.getByRole('heading', { name: shawl.name })).toBeVisible();
    await expect(page.getByRole('heading', { name: stole.name })).toBeHidden();
    await page.getByRole('heading', { name: shawl.name }).click();
    await expect(page).toHaveURL(new RegExp(`/product/${shawl.slug}$`));

    await expect(page.getByRole('radio', { name: /Black/ })).toBeDisabled();
    await page.getByLabel('Increase quantity').click();
    await page.getByLabel('Increase quantity').click();
    await expect(page.getByLabel('Increase quantity')).toBeDisabled();

    const order = page.getByRole('link', { name: 'Order on WhatsApp' }).first();
    if (testInfo.project.name === 'mobile') await expect(page.getByRole('link', { name: 'Order on WhatsApp' }).last()).toBeVisible();
    const message = whatsappMessage(await order.getAttribute('href'));
    expect(message).toContain(`Product: ${shawl.name}`);
    expect(message).toContain(`SKU/Item: QA-${shawl.slug}`);
    expect(message).toContain('Color: Brown');
    expect(message).toContain('Size: Free Size');
    expect(message).toContain('Quantity: 3');
    expect(message).toContain('Unit price: PKR 4,500');
    expect(message).toContain('Total: PKR 13,500');
    expect(message).toContain(`Product link: ${live.site}/product/${shawl.slug}`);

    const popup = page.waitForEvent('popup');
    await order.click();
    expect((await popup).url()).toContain(`https://wa.me/${live.whatsapp}`);
  });

  test('multi-item cart hands off verified items and totals', async ({ page }) => {
    await addToCart(page, shawl.slug, 2);
    await addToCart(page, stole.slug);
    await page.goto('/cart');
    await expect(checkoutLink(page)).toBeVisible();
    const message = whatsappMessage(await checkoutLink(page).getAttribute('href'));
    expect(message).toContain(`1. ${shawl.name}`);
    expect(message).toContain('Color / Size: Brown / Free Size');
    expect(message).toContain('Quantity: 2 x PKR 4,500 = PKR 9,000');
    expect(message).toContain(`Link: ${live.site}/product/${shawl.slug}`);
    expect(message).toContain(`2. ${stole.name}`);
    expect(message).toContain('Quantity: 1 x PKR 2,800 = PKR 2,800');
    expect(message).toContain('Total: PKR 11,800');

    const popup = page.waitForEvent('popup');
    await checkoutLink(page).click();
    expect((await popup).url()).toContain(`https://wa.me/${live.whatsapp}`);
  });

  test('backend price, stock and publication changes after add-to-cart win before handoff', async ({ page, request }) => {
    await addToCart(page, shawl.slug, 3);
    await addToCart(page, stole.slug);

    const current = await adminApi(request, 'GET', `/${shawl.id}`);
    await adminApi(request, 'PUT', `/${shawl.id}`, {
      ...productPayload(shawl.slug, shawl.name, [
        { id: current.variants[0]._id, name: 'Brown', color: 'Brown', price: 5000, stock: 1 },
        { id: current.variants[1]._id, name: 'Black', color: 'Black', price: 4800, stock: 0 },
      ]),
    });
    await adminApi(request, 'PATCH', `/${stole.id}/status`, { status: 'draft' });

    await page.goto('/cart');
    const notice = page.getByRole('alert').filter({ hasText: 'Your cart was updated' });
    await expect(notice).toContainText(`${stole.name} (Beige / Free Size) is no longer available`);
    await expect(notice).toContainText('quantity reduced from 3 to 1');
    await expect(notice).toContainText('price changed from PKR 4,500 to PKR 5,000');
    await expect(page.getByRole('button', { name: 'Review cart changes' })).toBeDisabled();
    await expect(checkoutLink(page)).toHaveCount(0);

    await page.getByRole('button', { name: 'Continue with updated cart' }).click();
    const message = whatsappMessage(await checkoutLink(page).getAttribute('href'));
    expect(message).toContain('Quantity: 1 x PKR 5,000 = PKR 5,000');
    expect(message).toContain('Total: PKR 5,000');
    expect(message).not.toContain(stole.name);
  });

  test('removed option and sold-out stock block handoff', async ({ page, request }) => {
    await addToCart(page, shawl.slug);
    await adminApi(request, 'PATCH', `/${shawl.id}/stock`, { variant_id: shawl.variants[0]._id, stock: 0 });
    await page.goto('/cart');
    await expect(page.getByRole('alert')).toContainText('is sold out and was removed from your cart');
    await expect(page.getByRole('heading', { name: 'Your cart is empty' })).toBeVisible();

    await page.goto(`/product/${shawl.slug}`);
    await expect(page.getByRole('button', { name: 'Order unavailable' }).first()).toBeDisabled();
  });

  test('catalogue outage blocks handoff until availability is confirmed', async ({ page }) => {
    await addToCart(page, stole.slug);
    await page.route(`${live.api}/products/slug/**`, (route) => route.abort());
    await page.goto('/cart');
    await expect(page.getByRole('alert')).toContainText('could not confirm current availability');
    await expect(page.getByRole('button', { name: 'Availability not confirmed' })).toBeDisabled();

    await page.unroute(`${live.api}/products/slug/**`);
    await page.getByRole('button', { name: 'Check again' }).click();
    await expect(checkoutLink(page)).toBeVisible();
  });

  test('a stale verification is re-checked instead of opening WhatsApp', async ({ page, request }) => {
    await page.clock.install();
    await addToCart(page, stole.slug);
    await page.goto('/cart');
    await expect(checkoutLink(page)).toBeVisible();

    await adminApi(request, 'PATCH', `/${stole.id}/status`, { status: 'archived' });
    await page.clock.fastForward('02:00');
    let opened = false;
    page.on('popup', () => { opened = true; });
    await checkoutLink(page).click();
    await expect(page.getByRole('alert')).toContainText('is no longer available');
    expect(opened).toBe(false);
  });

  test('empty cart shows guidance', async ({ page }) => {
    await page.goto('/cart');
    await expect(page.getByRole('heading', { name: 'Your cart is empty' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Browse products' })).toBeVisible();
  });
});
