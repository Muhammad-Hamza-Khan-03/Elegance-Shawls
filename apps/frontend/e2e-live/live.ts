import { APIRequestContext, BrowserContext, Page, TestInfo, expect } from '@playwright/test';

const env = (name: string) => {
  const value = process.env[name];
  if (!value) throw new Error(`${name} must be set for live acceptance tests.`);
  return value.replace(/\/$/, '');
};

export const live = {
  site: env('LIVE_SITE_URL'),
  api: env('LIVE_API_URL'),
  adminKey: env('LIVE_ADMIN_KEY'),
  whatsapp: env('LIVE_WHATSAPP_NUMBER'),
};

export const fixtureSuffix = (testInfo: TestInfo) =>
  `${testInfo.project.name}-${Date.now().toString(36)}`;

export const image = (label: string) => `https://placehold.co/600x800/png?text=${encodeURIComponent(label)}`;

type VariantInput = { name: string; color: string; price: number; stock: number; id?: string };

export const productPayload = (slug: string, name: string, variants: VariantInput[], status = 'active') => ({
  name,
  slug,
  cover_image_url: image(name),
  category: 'shawls',
  item_number: `QA-${slug}`.slice(0, 100),
  material: 'QA fixture wool',
  status,
  variants: variants.map((variant) => ({ ...variant, image_url: image(`${name} ${variant.color}`) })),
});

// Direct backend admin calls (X-Admin-Key) used only for fixture setup and assertions.
export const adminApi = async (request: APIRequestContext, method: string, path: string, data?: unknown) => {
  const response = await request.fetch(`${live.api}/products/admin${path}`, {
    method,
    headers: { 'X-Admin-Key': live.adminKey },
    data,
  });
  expect(response.status(), `${method} ${path}: ${await response.text()}`).toBeLessThan(300);
  return response.json();
};

export const createProduct = (request: APIRequestContext, payload: ReturnType<typeof productPayload>) =>
  adminApi(request, 'POST', '/', payload);

// Answer wa.me locally so the handoff URL can be inspected without contacting WhatsApp.
export const interceptWhatsApp = async (context: BrowserContext) => {
  await context.route('https://wa.me/**', (route) => route.fulfill({ status: 200, contentType: 'text/html', body: '<title>WhatsApp intercepted</title>' }));
};

export const whatsappMessage = (href: string | null) => {
  expect(href).toBeTruthy();
  const url = new URL(href!);
  expect(url.origin).toBe('https://wa.me');
  expect(url.pathname).toBe(`/${live.whatsapp}`);
  return url.searchParams.get('text') || '';
};

export const signIn = async (page: Page, key = live.adminKey) => {
  await page.goto('/admin/login');
  await page.getByLabel('Admin key').fill(key);
  await page.getByRole('button', { name: 'Sign in' }).click();
};
