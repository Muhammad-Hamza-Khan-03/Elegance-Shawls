import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { POST } from './route';
import { GET as adminList } from '../admin/enquiries/route';
import { GET as adminOne } from '../admin/enquiries/[reference]/route';
import { ADMIN_SESSION_COOKIE } from '@/lib/admin-session';

const origin = 'https://store.example.invalid';
const TOKEN = `es1.${'a'.repeat(43)}`;

describe('enquiry proxies', () => {
  const oldUrl = process.env.NEXT_PUBLIC_API_URL;
  const fetchMock = vi.fn();
  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = 'https://api.example.invalid/';
    fetchMock.mockReset().mockResolvedValue(new Response('{"reference":"ES-AAAAAA"}', { status: 201 }));
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => {
    process.env.NEXT_PUBLIC_API_URL = oldUrl;
    vi.unstubAllGlobals();
  });

  const post = (headers: Record<string, string> = { origin }, body = '{"items":[]}') =>
    POST(new Request(`${origin}/api/enquiries`, { method: 'POST', headers: { 'content-type': 'application/json', ...headers }, body }));

  it('forwards a same-origin cart to the backend and passes the status through', async () => {
    const response = await post({ origin, 'x-forwarded-for': '203.0.113.9' });
    expect(response.status).toBe(201);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe('https://api.example.invalid/v1/enquiries');
    expect(init.headers['x-forwarded-for']).toBe('203.0.113.9');
    expect(init.headers).not.toHaveProperty('X-Admin-Session');
  });

  it('refuses cross-origin and oversized requests without calling the backend', async () => {
    expect((await post({ origin: 'https://evil.example.invalid' })).status).toBe(403);
    expect((await post({ origin }, 'x'.repeat(20_000))).status).toBe(413);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('answers 503 when the backend is unreachable', async () => {
    fetchMock.mockRejectedValue(new Error('down'));
    expect((await post()).status).toBe(503);
  });

  it('admin lookups need the session cookie and forward it only as X-Admin-Session', async () => {
    const anonymous = await adminList(new Request(`${origin}/api/admin/enquiries`));
    expect(anonymous.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();

    fetchMock.mockImplementation(async () => new Response('[]'));
    const request = (path: string) => new Request(`${origin}${path}`, { headers: { cookie: `${ADMIN_SESSION_COOKIE}=${TOKEN}` } });
    expect((await adminList(request('/api/admin/enquiries?reference=ES-AAAAAA'))).status).toBe(200);
    expect((await adminOne(request('/api/admin/enquiries/ES-AAAAAA'))).status).toBe(200);
    const [[listUrl, listInit], [oneUrl]] = fetchMock.mock.calls;
    expect(String(listUrl)).toBe('https://api.example.invalid/v1/admin/enquiries?reference=ES-AAAAAA');
    expect(listInit.headers.get('X-Admin-Session')).toBe(TOKEN);
    expect(listInit.headers.has('X-Admin-Key')).toBe(false);
    expect(String(oneUrl)).toBe('https://api.example.invalid/v1/admin/enquiries/ES-AAAAAA');
  });
});
