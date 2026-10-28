import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DELETE, GET, POST } from './route';
import { LOGIN_FAILURE_LIMIT, LOGIN_FAILURE_WINDOW_MS, resetLoginThrottle } from '@/lib/admin-login-throttle';
import { ADMIN_SESSION_COOKIE } from '@/lib/admin-session';

const ADMIN_KEY = 'fixture-only-private-admin-key';

const signIn = (key: unknown, { ip = '203.0.113.10', contentType = 'application/json' } = {}) =>
  POST(new Request('https://store.example.invalid/api/admin/session', {
    method: 'POST',
    headers: { 'content-type': contentType, 'x-forwarded-for': ip },
    body: JSON.stringify({ key }),
  }));

const sessionCookie = (response: Response) =>
  response.headers.get('set-cookie')?.match(new RegExp(`${ADMIN_SESSION_COOKIE}=([^;]*)`))?.[1];

describe('admin session route', () => {
  const oldKey = process.env.ADMIN_API_KEY;

  beforeEach(() => {
    process.env.ADMIN_API_KEY = ADMIN_KEY;
    resetLoginThrottle();
    vi.spyOn(console, 'log');
    vi.spyOn(console, 'error');
    vi.spyOn(console, 'warn');
  });

  afterEach(() => {
    if (oldKey === undefined) delete process.env.ADMIN_API_KEY;
    else process.env.ADMIN_API_KEY = oldKey;
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('issues an httpOnly SameSite session cookie for the correct key', async () => {
    const response = await signIn(ADMIN_KEY);
    expect(response.status).toBe(200);
    const setCookie = response.headers.get('set-cookie')!;
    expect(setCookie).toMatch(/HttpOnly/i);
    expect(setCookie).toMatch(/SameSite=lax/i);
    expect(setCookie).toMatch(/Max-Age=28800/i);
    expect(setCookie).toMatch(/Path=\//i);
    expect(setCookie).not.toContain(ADMIN_KEY);
    expect(await response.text()).not.toContain(ADMIN_KEY);

    const token = sessionCookie(response)!;
    const check = await GET(new Request('https://store.example.invalid/api/admin/session', {
      headers: { cookie: `${ADMIN_SESSION_COOKIE}=${token}` },
    }));
    expect(await check.json()).toEqual({ authenticated: true });
  });

  it.each([
    ['wrong key', 'not-the-admin-key'],
    ['key prefix', ADMIN_KEY.slice(0, -1)],
    ['empty key', ''],
    ['non-string key', { key: ADMIN_KEY }],
  ])('rejects a %s with 401 and no cookie', async (_label, key) => {
    const response = await signIn(key);
    expect(response.status).toBe(401);
    expect(response.headers.get('set-cookie')).toBeNull();
    expect(await response.text()).not.toContain(ADMIN_KEY);
  });

  it('rejects non-JSON sign-in requests without counting a failure', async () => {
    const response = await signIn(ADMIN_KEY, { contentType: 'text/plain' });
    expect(response.status).toBe(415);
    expect(response.headers.get('set-cookie')).toBeNull();
  });

  it('throttles repeated failures with 429, even for the correct key, until the window expires', async () => {
    vi.useFakeTimers();
    for (let attempt = 0; attempt < LOGIN_FAILURE_LIMIT; attempt += 1) {
      expect((await signIn('wrong')).status).toBe(401);
    }

    const throttled = await signIn(ADMIN_KEY);
    expect(throttled.status).toBe(429);
    expect(Number(throttled.headers.get('retry-after'))).toBeGreaterThan(0);
    expect(throttled.headers.get('set-cookie')).toBeNull();

    expect((await signIn(ADMIN_KEY, { ip: '198.51.100.7' })).status).toBe(200);

    vi.advanceTimersByTime(LOGIN_FAILURE_WINDOW_MS + 1);
    expect((await signIn(ADMIN_KEY)).status).toBe(200);
  });

  it('keys the throttle on the proxy-appended address, not a client-supplied one', async () => {
    for (let attempt = 0; attempt < LOGIN_FAILURE_LIMIT; attempt += 1) {
      await signIn('wrong', { ip: `10.0.0.${attempt}, 203.0.113.10` });
    }
    expect((await signIn(ADMIN_KEY, { ip: '10.9.9.9, 203.0.113.10' })).status).toBe(429);
  });

  it('clears the failure count after a successful sign-in', async () => {
    for (let attempt = 0; attempt < LOGIN_FAILURE_LIMIT - 1; attempt += 1) await signIn('wrong');
    expect((await signIn(ADMIN_KEY)).status).toBe(200);
    for (let attempt = 0; attempt < LOGIN_FAILURE_LIMIT - 1; attempt += 1) {
      expect((await signIn('wrong')).status).toBe(401);
    }
  });

  it('returns 503 when no admin key is configured', async () => {
    delete process.env.ADMIN_API_KEY;
    expect((await signIn('anything')).status).toBe(503);
  });

  it('expires the session cookie on sign-out', async () => {
    const response = await DELETE();
    expect(await response.json()).toEqual({ authenticated: false });
    expect(response.headers.get('set-cookie')).toMatch(new RegExp(`${ADMIN_SESSION_COOKIE}=;.*Max-Age=0`, 'i'));
  });

  it('never logs the admin key', async () => {
    await signIn(ADMIN_KEY);
    await signIn('wrong');
    for (const spy of [console.log, console.error, console.warn]) {
      expect(JSON.stringify(vi.mocked(spy).mock.calls)).not.toContain(ADMIN_KEY);
    }
  });
});
