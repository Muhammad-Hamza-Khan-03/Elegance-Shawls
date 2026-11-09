import { expect, type APIRequestContext, type Page } from '@playwright/test';

export const API = `http://127.0.0.1:${process.env.E2E_REAL_API_PORT || '4300'}`;
export const WEB = `http://127.0.0.1:${process.env.E2E_REAL_WEB_PORT || '3300'}`;
export const OWNER = { email: 'owner@e2e.test', password: 'e2e-owner-Passw0rd-fixture' };
export const cartKey = 'elegance-shawls.cart.v1';

export type Variant = { _id: string; color?: string; price: number; stock: number };
export type PublicProduct = { _id: string; slug: string; name: string; status: string; variants: Variant[] };

/** Reads a product straight from the real backend (public route). */
export async function product(request: APIRequestContext, slug: string): Promise<PublicProduct> {
  const response = await request.get(`${API}/products/slug/${slug}`);
  expect(response.status(), `GET ${slug}`).toBe(200);
  return response.json();
}

/** Signs in through the storefront's own route handler, so the HttpOnly cookie lands in this page's context. */
export async function adminLogin(page: Page, credentials = OWNER) {
  const response = await page.request.post(`${WEB}/api/admin/session`, { headers: { origin: WEB }, data: credentials });
  expect(response.status(), 'admin sign-in').toBeLessThan(300);
}

/** Calls a backend route as an individual account (used to create other-role accounts and read audit data). */
export async function backendSession(request: APIRequestContext, credentials = OWNER): Promise<{ 'X-Admin-Session': string }> {
  const response = await request.post(`${API}/v1/admin/auth/login`, { data: credentials });
  expect(response.status(), 'backend login').toBe(200);
  return { 'X-Admin-Session': (await response.json()).token };
}
