import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { proxyAdminRequest } from './admin-backend';
import { ADMIN_SESSION_COOKIE, issueAdminSession } from './admin-session';

describe('admin backend proxy authentication', () => {
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
    vi.unstubAllGlobals();
  });

  it.each(['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])('blocks anonymous %s before calling the backend', async (method) => {
    const response = await proxyAdminRequest(new Request('https://store.example.invalid/api/admin/products', { method }), '/products/admin/');
    expect(response.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each(['invalid-session', '%E0%A4%A'])('rejects invalid or malformed session cookies', async (token) => {
    const request = new Request('https://store.example.invalid/api/admin/products', {
      headers: { cookie: `${ADMIN_SESSION_COOKIE}=${token}` },
    });
    expect((await proxyAdminRequest(request, '/products/admin/')).status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('forwards an authenticated request with a private server-side key', async () => {
    const session = issueAdminSession()!;
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ items: [] }), { status: 200, headers: { 'content-type': 'application/json' } }));
    const request = new Request('https://store.example.invalid/api/admin/products?limit=10', {
      headers: { cookie: `${ADMIN_SESSION_COOKIE}=${session.token}` },
    });
    const response = await proxyAdminRequest(request, '/products/admin/');
    expect(response.status).toBe(200);
    expect(fetchMock.mock.calls[0][0].toString()).toBe('https://backend.example.invalid/products/admin/?limit=10');
    expect(fetchMock.mock.calls[0][1].headers.get('X-Admin-Key')).toBe(process.env.ADMIN_API_KEY);
    expect(await response.text()).not.toContain(process.env.ADMIN_API_KEY!);
  });
});
