import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DELETE, GET, PATCH, POST, PUT } from './route';
import { CUSTOMER_SESSION_COOKIE } from '@/lib/customer-session';

const ORIGIN = 'https://store.example.invalid';
const BACKEND = 'https://backend.example.invalid';
const TOKEN = `cs1.${'s'.repeat(43)}`;
const COOKIE = `${CUSTOMER_SESSION_COOKIE}=${TOKEN}`;
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const ctx = (...path: string[]) => ({ params: Promise.resolve({ path: path.length ? path : undefined }) });
const req = (method: string, path = '', init: { cookie?: string | null; origin?: string | null; body?: unknown } = {}) =>
  new Request(`${ORIGIN}/api/customer/memory${path}`, {
    method,
    headers: { ...(init.cookie === null ? {} : { cookie: init.cookie ?? COOKIE }), ...(init.origin === null ? {} : { origin: init.origin ?? ORIGIN }), 'content-type': 'application/json' },
    ...(init.body !== undefined ? { body: JSON.stringify(init.body) } : {}),
  });

describe('customer memory proxy', () => {
  const old = process.env.NEXT_PUBLIC_API_URL;
  const fetchMock = vi.fn();
  beforeEach(() => { process.env.NEXT_PUBLIC_API_URL = BACKEND; fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock); });
  afterEach(() => { process.env.NEXT_PUBLIC_API_URL = old; vi.unstubAllGlobals(); });

  it('turns the HttpOnly cookie into the session header and never sends the cookie or a customer id upstream', async () => {
    fetchMock.mockResolvedValue(json({ items: [] }));
    const res = await GET(req('GET'), ctx());
    expect(await res.json()).toEqual({ items: [] });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BACKEND}/v1/me/memory`);
    expect(init.headers).toEqual({ 'X-Customer-Session': TOKEN });
    expect(JSON.stringify(init)).not.toContain(CUSTOMER_SESSION_COOKIE);
  });

  it('refuses without a session cookie, before any upstream call', async () => {
    for (const bad of [null, `${CUSTOMER_SESSION_COOKIE}=nope`]) {
      expect((await GET(req('GET', '', { cookie: bad }), ctx())).status).toBe(401);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('requires same origin for every mutation but not for reads', async () => {
    fetchMock.mockResolvedValue(json({ granted: true }));
    for (const [handler, method] of [[PUT, 'PUT'], [POST, 'POST'], [PATCH, 'PATCH'], [DELETE, 'DELETE']] as const) {
      expect((await handler(req(method, '/consent', { origin: 'https://evil.invalid', body: { granted: true } }), ctx('consent'))).status).toBe(403);
    }
    expect((await PUT(req('PUT', '/consent', { origin: null, body: { granted: true } }), ctx('consent'))).status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
    expect((await GET(req('GET', '/consent', { origin: 'https://evil.invalid' }), ctx('consent'))).status).toBe(200);
  });

  it('only forwards memory paths: consent, an id, or the list', async () => {
    fetchMock.mockResolvedValue(json({}));
    expect((await GET(req('GET', '/../../admin'), ctx('..', '..', 'admin'))).status).toBe(404);
    expect((await GET(req('GET', '/a/b/c'), ctx('a', 'b', 'c'))).status).toBe(404);
    expect((await GET(req('GET', '/x%2Fy'), ctx('x/y'))).status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
    await GET(req('GET', '/0b8f2a54-3c1d-4e6a-9f10-2a7d5c8e1b34'), ctx('0b8f2a54-3c1d-4e6a-9f10-2a7d5c8e1b34'));
    expect(fetchMock.mock.calls[0][0]).toBe(`${BACKEND}/v1/me/memory/0b8f2a54-3c1d-4e6a-9f10-2a7d5c8e1b34`);
  });

  it('passes created status through, handles 204, and never relays upstream error detail', async () => {
    fetchMock.mockResolvedValueOnce(json({ id: 'x' }, 201));
    expect((await POST(req('POST', '', { body: { key: 'k' } }), ctx())).status).toBe(201);
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    expect((await DELETE(req('DELETE', '/abc'), ctx('abc'))).status).toBe(204);
    fetchMock.mockResolvedValueOnce(json({ detail: { reason: 'secret internal text jane@example.com' } }, 422));
    const rejected = await POST(req('POST', '', { body: { key: 'k' } }), ctx());
    expect(rejected.status).toBe(422);
    expect(JSON.stringify(await rejected.json())).not.toContain('secret');
    fetchMock.mockResolvedValueOnce(json({ detail: 'boom' }, 500));
    expect((await GET(req('GET'), ctx())).status).toBe(503);
    fetchMock.mockRejectedValueOnce(new Error('down'));
    expect((await GET(req('GET'), ctx())).status).toBe(503);
  });

  it('keeps 403 and 410 as themselves and relays only allowlisted reason codes', async () => {
    fetchMock.mockResolvedValueOnce(json({ detail: { status: 'rejected', reason: 'consent_required' } }, 403));
    const consent = await GET(req('GET'), ctx());
    expect(consent.status).toBe(403);
    expect(await consent.json()).toEqual({ detail: 'Request was not accepted.', reason: 'consent_required' });
    fetchMock.mockResolvedValueOnce(json({ detail: { reason: 'gone' } }, 410));
    expect((await GET(req('GET', '/abc'), ctx('abc'))).status).toBe(410);
    fetchMock.mockResolvedValueOnce(json({ detail: { reason: 'stack trace for jane@example.com' } }, 409));
    const odd = await POST(req('POST', '', { body: {} }), ctx());
    expect(odd.status).toBe(409);
    expect(await odd.json()).toEqual({ detail: 'Request was not accepted.' });
  });
});
