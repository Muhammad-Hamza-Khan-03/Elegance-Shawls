import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DELETE, GET, POST } from './route';
import { LOGIN_FAILURE_LIMIT, LOGIN_FAILURE_WINDOW_MS, resetLoginThrottle } from '@/lib/admin-login-throttle';
import { ADMIN_SESSION_COOKIE } from '@/lib/admin-session';

const ORIGIN = 'https://store.example.invalid';
const BACKEND = 'https://backend.example.invalid';
const TOKEN = `es1.${'b'.repeat(43)}`;
const PASSWORD = 'fixture-only-account-password';
const account = { id: 'a1', email: 'owner@example.com', role: 'owner', display_name: null };
const loginBody = () => ({ token: TOKEN, expires_at: new Date(Date.now() + 8 * 3600 * 1000).toISOString(), account });
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

const signIn = (body: unknown, { ip = '203.0.113.10', contentType = 'application/json', origin = ORIGIN as string | null } = {}) =>
  POST(new Request(`${ORIGIN}/api/admin/session`, {
    method: 'POST',
    headers: { 'content-type': contentType, 'x-forwarded-for': ip, ...(origin ? { origin } : {}) },
    body: JSON.stringify(body),
  }));
const creds = (password = PASSWORD) => ({ email: 'owner@example.com', password });

const sessionCookie = (response: Response) =>
  response.headers.get('set-cookie')?.match(new RegExp(`${ADMIN_SESSION_COOKIE}=([^;]*)`))?.[1];

describe('admin session route', () => {
  const oldUrl = process.env.NEXT_PUBLIC_API_URL;
  const fetchMock = vi.fn();

  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = BACKEND;
    resetLoginThrottle();
    fetchMock.mockReset();
    // The backend accepts exactly one password.
    fetchMock.mockImplementation(async (_url: string, init: RequestInit) => {
      const sent = JSON.parse(String(init.body));
      return sent.password === PASSWORD ? json(loginBody()) : json({ detail: 'Invalid email or password' }, 401);
    });
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(console, 'log');
    vi.spyOn(console, 'error');
    vi.spyOn(console, 'warn');
  });

  afterEach(() => {
    if (oldUrl === undefined) delete process.env.NEXT_PUBLIC_API_URL;
    else process.env.NEXT_PUBLIC_API_URL = oldUrl;
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('puts the backend session token only in an httpOnly SameSite cookie, never in the body', async () => {
    const response = await signIn(creds());
    expect(response.status).toBe(200);
    const setCookie = response.headers.get('set-cookie')!;
    expect(setCookie).toMatch(/HttpOnly/i);
    expect(setCookie).toMatch(/SameSite=lax/i);
    expect(setCookie).toMatch(/Max-Age=(2879\d|28800)/i);
    expect(setCookie).toMatch(/Path=\//i);
    expect(sessionCookie(response)).toBe(TOKEN);
    const text = await response.text();
    expect(text).not.toContain(TOKEN);
    expect(text).not.toContain(PASSWORD);
    expect(JSON.parse(text)).toMatchObject({ authenticated: true, email: 'owner@example.com', role: 'owner' });
    expect(fetchMock.mock.calls[0][0].toString()).toBe(`${BACKEND}/v1/admin/auth/login`);
    expect(new Headers(fetchMock.mock.calls[0][1].headers).get('X-Admin-Key')).toBeNull();
  });

  it('reports who is signed in by asking the backend, and nothing for a dead session', async () => {
    fetchMock.mockResolvedValueOnce(json({ account, role: 'owner', legacy: false }));
    const alive = await GET(new Request(`${ORIGIN}/api/admin/session`, { headers: { cookie: `${ADMIN_SESSION_COOKIE}=${TOKEN}` } }));
    expect(await alive.json()).toEqual({ authenticated: true, email: 'owner@example.com', role: 'owner' });
    expect(new Headers(fetchMock.mock.calls[0][1].headers).get('X-Admin-Session')).toBe(TOKEN);

    fetchMock.mockResolvedValueOnce(json({ detail: 'Invalid administrative credentials' }, 401));
    const dead = await GET(new Request(`${ORIGIN}/api/admin/session`, { headers: { cookie: `${ADMIN_SESSION_COOKIE}=${TOKEN}` } }));
    expect(await dead.json()).toEqual({ authenticated: false });

    fetchMock.mockClear();
    const none = await GET(new Request(`${ORIGIN}/api/admin/session`, { headers: { cookie: `${ADMIN_SESSION_COOKIE}=forged` } }));
    expect(await none.json()).toEqual({ authenticated: false });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([
    ['wrong password', creds('not-the-password')],
    ['empty password', creds('')],
    ['no body fields', {}],
  ])('rejects %s without a cookie', async (_label, body) => {
    const response = await signIn(body);
    expect([400, 401]).toContain(response.status);
    expect(response.headers.get('set-cookie')).toBeNull();
    expect(await response.text()).not.toContain(PASSWORD);
  });

  it('gives the same answer for any backend sign-in refusal (unknown account, disabled, locked)', async () => {
    fetchMock.mockResolvedValue(json({ detail: 'Invalid email or password' }, 401));
    const answers = await Promise.all([signIn(creds()), signIn({ email: 'ghost@example.com', password: 'whatever-it-is' }, { ip: '198.51.100.1' })]);
    expect(answers.map((r) => r.status)).toEqual([401, 401]);
    expect(new Set(await Promise.all(answers.map((r) => r.text()))).size).toBe(1);
  });

  it('refuses cross-origin and origin-less sign-in before calling the backend (login CSRF)', async () => {
    expect((await signIn(creds(), { origin: 'https://evil.example.invalid' })).status).toBe(403);
    expect((await signIn(creds(), { origin: null })).status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('rejects non-JSON sign-in requests without counting a failure', async () => {
    const response = await signIn(creds(), { contentType: 'text/plain' });
    expect(response.status).toBe(415);
    expect(response.headers.get('set-cookie')).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('throttles repeated failures with 429, even for the right password, until the window expires', async () => {
    vi.useFakeTimers();
    for (let attempt = 0; attempt < LOGIN_FAILURE_LIMIT; attempt += 1) {
      expect((await signIn(creds('wrong'))).status).toBe(401);
    }

    const throttled = await signIn(creds());
    expect(throttled.status).toBe(429);
    expect(Number(throttled.headers.get('retry-after'))).toBeGreaterThan(0);
    expect(throttled.headers.get('set-cookie')).toBeNull();

    expect((await signIn(creds(), { ip: '198.51.100.7' })).status).toBe(200);

    vi.advanceTimersByTime(LOGIN_FAILURE_WINDOW_MS + 1);
    expect((await signIn(creds())).status).toBe(200);
  });

  it('keys the throttle on the proxy-appended address, not a client-supplied one', async () => {
    for (let attempt = 0; attempt < LOGIN_FAILURE_LIMIT; attempt += 1) {
      await signIn(creds('wrong'), { ip: `10.0.0.${attempt}, 203.0.113.10` });
    }
    expect((await signIn(creds(), { ip: '10.9.9.9, 203.0.113.10' })).status).toBe(429);
  });

  it('does not issue a cookie for a malformed token from the backend, and survives it being down', async () => {
    fetchMock.mockResolvedValueOnce(json({ ...loginBody(), token: 'not-a-session' }));
    const bad = await signIn(creds());
    expect(bad.status).toBe(503);
    expect(bad.headers.get('set-cookie')).toBeNull();
    fetchMock.mockRejectedValueOnce(new Error('connect ECONNREFUSED'));
    expect((await signIn(creds())).status).toBe(503);
  });

  it('returns 503 when the backend is not configured', async () => {
    delete process.env.NEXT_PUBLIC_API_URL;
    expect((await signIn(creds())).status).toBe(503);
  });

  it('revokes the session on the backend and expires the cookie on sign-out', async () => {
    fetchMock.mockResolvedValue(json({ ok: true }));
    const response = await DELETE(new Request(`${ORIGIN}/api/admin/session`, {
      method: 'DELETE',
      headers: { origin: ORIGIN, cookie: `${ADMIN_SESSION_COOKIE}=${TOKEN}` },
    }));
    expect(await response.json()).toEqual({ authenticated: false });
    expect(response.headers.get('set-cookie')).toMatch(new RegExp(`${ADMIN_SESSION_COOKIE}=;.*Max-Age=0`, 'i'));
    expect(fetchMock.mock.calls[0][0].toString()).toBe(`${BACKEND}/v1/admin/auth/logout`);
    expect(fetchMock.mock.calls[0][1].method).toBe('POST');
    expect(new Headers(fetchMock.mock.calls[0][1].headers).get('X-Admin-Session')).toBe(TOKEN);
  });

  it('still clears the cookie when the backend cannot be reached, and refuses cross-origin sign-out', async () => {
    fetchMock.mockRejectedValue(new Error('down'));
    const request = (origin: string) => new Request(`${ORIGIN}/api/admin/session`, { method: 'DELETE', headers: { origin, cookie: `${ADMIN_SESSION_COOKIE}=${TOKEN}` } });
    expect((await DELETE(request(ORIGIN))).headers.get('set-cookie')).toMatch(/Max-Age=0/i);
    fetchMock.mockClear();
    const cross = await DELETE(request('https://evil.example.invalid'));
    expect(cross.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('never logs the password or the session token', async () => {
    await signIn(creds());
    await signIn(creds('wrong'));
    for (const spy of [console.log, console.error, console.warn]) {
      const logged = JSON.stringify(vi.mocked(spy).mock.calls);
      expect(logged).not.toContain(PASSWORD);
      expect(logged).not.toContain(TOKEN);
    }
  });
});
