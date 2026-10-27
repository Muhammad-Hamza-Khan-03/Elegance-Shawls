import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GET as listProducts, POST as createProduct } from '@/app/api/admin/products/route';
import { GET as getProduct, PUT as updateProduct, DELETE as archiveProduct } from '@/app/api/admin/products/[productId]/route';
import { PATCH as updateStatus } from '@/app/api/admin/products/[productId]/status/route';
import { PATCH as updateStock } from '@/app/api/admin/products/[productId]/stock/route';
import { ADMIN_SESSION_COOKIE, issueAdminSession } from './admin-session';

const origin = 'https://store.example.invalid';
const productId = '507f1f77bcf86cd799439011';
const routes = [
  { name: 'list', method: 'GET', path: '/api/admin/products?limit=10', backendPath: '/products/admin/?limit=10', handler: listProducts },
  { name: 'create', method: 'POST', path: '/api/admin/products', backendPath: '/products/admin/', handler: createProduct },
  { name: 'detail', method: 'GET', path: `/api/admin/products/${productId}`, backendPath: `/products/admin/${productId}`, handler: getProduct },
  { name: 'edit', method: 'PUT', path: `/api/admin/products/${productId}`, backendPath: `/products/admin/${productId}`, handler: updateProduct },
  { name: 'archive', method: 'DELETE', path: `/api/admin/products/${productId}`, backendPath: `/products/admin/${productId}`, handler: archiveProduct },
  { name: 'status', method: 'PATCH', path: `/api/admin/products/${productId}/status`, backendPath: `/products/admin/${productId}/status`, handler: updateStatus },
  { name: 'stock', method: 'PATCH', path: `/api/admin/products/${productId}/stock`, backendPath: `/products/admin/${productId}/stock`, handler: updateStock },
] as const;

const makeRequest = (route: (typeof routes)[number], cookie?: string, requestOrigin?: string) =>
  new Request(`${origin}${route.path}`, {
    method: route.method,
    headers: {
      ...(cookie ? { cookie: `${ADMIN_SESSION_COOKIE}=${cookie}` } : {}),
      ...(requestOrigin ? { origin: requestOrigin } : {}),
      ...(route.method === 'GET' ? {} : { 'content-type': 'application/json' }),
    },
    ...(route.method === 'GET' ? {} : { body: JSON.stringify({ fixture: true }) }),
  });

describe('admin API proxy authorization', () => {
  const oldKey = process.env.ADMIN_API_KEY;
  const oldUrl = process.env.NEXT_PUBLIC_API_URL;
  const fetchMock = vi.fn();

  beforeEach(() => {
    process.env.ADMIN_API_KEY = 'fixture-only-private-admin-key';
    process.env.NEXT_PUBLIC_API_URL = 'https://backend.example.invalid';
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    if (oldKey === undefined) delete process.env.ADMIN_API_KEY;
    else process.env.ADMIN_API_KEY = oldKey;
    if (oldUrl === undefined) delete process.env.NEXT_PUBLIC_API_URL;
    else process.env.NEXT_PUBLIC_API_URL = oldUrl;
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it.each(routes)('blocks anonymous $name without calling the backend', async (route) => {
    expect((await route.handler(makeRequest(route, undefined, origin))).status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each(routes)('blocks forged sessions on $name without calling the backend', async (route) => {
    expect((await route.handler(makeRequest(route, 'forged-session', origin))).status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each(routes)('blocks expired sessions on $name without calling the backend', async (route) => {
    const session = issueAdminSession()!;
    vi.spyOn(Date, 'now').mockReturnValue((session.expiresAt + 1) * 1000);
    expect((await route.handler(makeRequest(route, session.token, origin))).status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each(routes.filter((route) => route.method !== 'GET'))('blocks cross-origin $name without calling the backend', async (route) => {
    const session = issueAdminSession()!;
    expect((await route.handler(makeRequest(route, session.token, 'https://other.example.invalid'))).status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each(routes.filter((route) => route.method !== 'GET'))('blocks $name with no Origin without calling the backend', async (route) => {
    const session = issueAdminSession()!;
    expect((await route.handler(makeRequest(route, session.token))).status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('uses the public Host when Next.js canonicalizes the request URL', async () => {
    const session = issueAdminSession()!;
    fetchMock.mockResolvedValue(new Response('{}', { status: 200 }));
    const request = new Request('http://localhost:3200/api/admin/products', {
      method: 'POST',
      headers: {
        host: '127.0.0.1:3200',
        origin: 'http://127.0.0.1:3200',
        cookie: `${ADMIN_SESSION_COOKIE}=${session.token}`,
      },
    });

    expect((await createProduct(request)).status).toBe(200);
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('rejects an Origin that matches the internal URL but not the public Host', async () => {
    const session = issueAdminSession()!;
    const request = new Request('http://localhost:3200/api/admin/products', {
      method: 'POST',
      headers: {
        host: '127.0.0.1:3200',
        origin: 'http://localhost:3200',
        cookie: `${ADMIN_SESSION_COOKIE}=${session.token}`,
      },
    });

    expect((await createProduct(request)).status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each(routes)('forwards signed-in same-origin $name with the private key', async (route) => {
    const session = issueAdminSession()!;
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    }));
    const response = await route.handler(makeRequest(route, session.token, origin));

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0][0].toString()).toBe(`https://backend.example.invalid${route.backendPath}`);
    expect(fetchMock.mock.calls[0][1].method).toBe(route.method);
    expect(fetchMock.mock.calls[0][1].headers.get('X-Admin-Key')).toBe(process.env.ADMIN_API_KEY);
    expect(await response.text()).not.toContain(process.env.ADMIN_API_KEY!);
  });
});
