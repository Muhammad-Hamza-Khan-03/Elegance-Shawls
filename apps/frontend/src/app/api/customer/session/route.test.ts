import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DELETE, POST } from './route';
import { CUSTOMER_SESSION_COOKIE } from '@/lib/customer-session';

const ORIGIN = 'https://store.example.invalid';
const BACKEND = 'https://backend.example.invalid';
const ID_TOKEN = `provider-token-${'x'.repeat(20)}`;
const SESSION_TOKEN = `cs1.${'s'.repeat(43)}`;
const expiresAt = new Date(Date.now() + 3600 * 1000).toISOString();
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

const exchangeRequest = (body: unknown, options: { origin?: string | null; contentType?: string } = {}) =>
  new Request(`${ORIGIN}/api/customer/session`, {
    method: 'POST',
    headers: {
      'content-type': options.contentType ?? 'application/json',
      ...(options.origin === null ? {} : { origin: options.origin ?? ORIGIN }),
    },
    body: JSON.stringify(body),
  });

const signOutRequest = (cookie?: string, origin = ORIGIN) =>
  new Request(`${ORIGIN}/api/customer/session`, {
    method: 'DELETE',
    headers: { origin, ...(cookie ? { cookie } : {}) },
  });

const sessionCookie = (response: Response) =>
  response.headers.get('set-cookie')?.match(new RegExp(`${CUSTOMER_SESSION_COOKIE}=([^;]*)`))?.[1];

describe('customer session route', () => {
  const oldUrl = process.env.NEXT_PUBLIC_API_URL;
  const fetchMock = vi.fn();

  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = BACKEND;
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    if (oldUrl === undefined) delete process.env.NEXT_PUBLIC_API_URL;
    else process.env.NEXT_PUBLIC_API_URL = oldUrl;
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('exchanges only the external token, keeps the local session in an HttpOnly cookie, and never returns either token', async () => {
    fetchMock.mockResolvedValue(json({ session_token: SESSION_TOKEN, expires_at: expiresAt }));

    const response = await POST(exchangeRequest({ id_token: ID_TOKEN }));

    expect(response.status).toBe(200);
    expect(sessionCookie(response)).toBe(SESSION_TOKEN);
    expect(response.headers.get('set-cookie')).toMatch(/HttpOnly/i);
    expect(response.headers.get('set-cookie')).toMatch(/SameSite=lax/i);
    expect(response.headers.get('set-cookie')).toMatch(/Path=\//i);
    const body = await response.text();
    expect(JSON.parse(body)).toEqual({ authenticated: true, expiresAt: Math.floor(new Date(expiresAt).getTime() / 1000) });
    expect(body).not.toContain(ID_TOKEN);
    expect(body).not.toContain(SESSION_TOKEN);
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0][0].toString()).toBe(`${BACKEND}/v1/customer/auth/exchange`);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ id_token: ID_TOKEN });
    expect(new Headers(fetchMock.mock.calls[0][1].headers).get('X-Customer-Session')).toBeNull();
  });

  it('rejects customer identifiers and malformed exchange input before contacting the backend', async () => {
    for (const body of [{ id_token: ID_TOKEN, customer_id: 'victim' }, {}, { id_token: 'x'.repeat(4097) }]) {
      const response = await POST(exchangeRequest(body));
      expect(response.status).toBe(400);
      expect(response.headers.get('set-cookie')).toBeNull();
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('preserves safe backend refusal semantics and never issues a cookie', async () => {
    fetchMock.mockResolvedValueOnce(json({ detail: 'Invalid identity token' }, 401));
    const invalid = await POST(exchangeRequest({ id_token: ID_TOKEN }));
    expect(invalid.status).toBe(401);
    expect(await invalid.json()).toEqual({ detail: 'Invalid identity token' });
    expect(invalid.headers.get('set-cookie')).toBeNull();

    fetchMock.mockResolvedValueOnce(json({ detail: 'Sign-in is temporarily unavailable' }, 503));
    const unavailable = await POST(exchangeRequest({ id_token: ID_TOKEN }));
    expect(unavailable.status).toBe(503);
    expect(await unavailable.json()).toEqual({ detail: 'Sign-in is temporarily unavailable' });
    expect(unavailable.headers.get('set-cookie')).toBeNull();
  });

  it('requires same-origin JSON exchange and refuses a missing backend configuration', async () => {
    expect((await POST(exchangeRequest({ id_token: ID_TOKEN }, { origin: 'https://evil.example.invalid' }))).status).toBe(403);
    expect((await POST(exchangeRequest({ id_token: ID_TOKEN }, { origin: null }))).status).toBe(403);
    expect((await POST(exchangeRequest({ id_token: ID_TOKEN }, { contentType: 'text/plain' }))).status).toBe(415);
    expect(fetchMock).not.toHaveBeenCalled();

    delete process.env.NEXT_PUBLIC_API_URL;
    expect((await POST(exchangeRequest({ id_token: ID_TOKEN }))).status).toBe(503);
  });

  it('revokes the opaque session server-side before expiring the local cookie', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    const response = await DELETE(signOutRequest(`${CUSTOMER_SESSION_COOKIE}=${SESSION_TOKEN}`));

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ authenticated: false });
    expect(response.headers.get('set-cookie')).toMatch(new RegExp(`${CUSTOMER_SESSION_COOKIE}=;.*Max-Age=0`, 'i'));
    expect(fetchMock.mock.calls[0][0].toString()).toBe(`${BACKEND}/v1/customer/auth/logout`);
    expect(fetchMock.mock.calls[0][1].method).toBe('POST');
    expect(new Headers(fetchMock.mock.calls[0][1].headers).get('X-Customer-Session')).toBe(SESSION_TOKEN);
  });

  it('clears the cookie on backend failure, but refuses cross-origin sign-out', async () => {
    fetchMock.mockRejectedValueOnce(new Error('backend down'));
    const response = await DELETE(signOutRequest(`${CUSTOMER_SESSION_COOKIE}=${SESSION_TOKEN}`));
    expect(response.status).toBe(200);
    expect(response.headers.get('set-cookie')).toMatch(/Max-Age=0/i);

    fetchMock.mockClear();
    const crossOrigin = await DELETE(signOutRequest(`${CUSTOMER_SESSION_COOKIE}=${SESSION_TOKEN}`, 'https://evil.example.invalid'));
    expect(crossOrigin.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
