import { afterEach, describe, expect, it, vi } from 'vitest';
import { POST } from './route';

const request = (body: string, headers: Record<string, string> = { origin: 'http://localhost:3000' }) =>
  new Request('http://localhost:3000/api/events', { method: 'POST', body, headers: { host: 'localhost:3000', ...headers } });

describe('POST /api/events', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it('answers 202 and does not call the backend when the API URL is missing', async () => {
    vi.stubEnv('NEXT_PUBLIC_API_URL', '');
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    expect((await POST(request('{}'))).status).toBe(202);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('ignores cross-origin posts', async () => {
    vi.stubEnv('NEXT_PUBLIC_API_URL', 'http://api.test');
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    await POST(request('{}', { origin: 'https://evil.example' }));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('forwards the session and visitor address, then sets an HTTP-only cookie without leaking the token in the body', async () => {
    vi.stubEnv('NEXT_PUBLIC_API_URL', 'http://api.test');
    const fetchMock = vi.fn().mockResolvedValue(Response.json({ accepted: 1, session_token: 'v1.abc.def' }));
    vi.stubGlobal('fetch', fetchMock);
    const response = await POST(request('{"events":[]}', { origin: 'http://localhost:3000', cookie: 'es_sid=v1.old.sig', 'x-forwarded-for': '203.0.113.9' }));
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers['x-session-token']).toBe('v1.old.sig');
    expect(init.headers['x-forwarded-for']).toBe('203.0.113.9');
    expect(response.headers.get('set-cookie')).toMatch(/es_sid=v1\.abc\.def;.*HttpOnly.*SameSite=Lax/);
    expect(await response.json()).toEqual({ accepted: 1 });
  });

  it('answers 202 when the backend is down', async () => {
    vi.stubEnv('NEXT_PUBLIC_API_URL', 'http://api.test');
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('down')));
    expect((await POST(request('{}'))).status).toBe(202);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 503 })));
    expect((await POST(request('{}'))).status).toBe(202);
  });

  it('drops oversized bodies without calling the backend', async () => {
    vi.stubEnv('NEXT_PUBLIC_API_URL', 'http://api.test');
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    await POST(request('x'.repeat(40_000)));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('continues an incoming trace with a new span and passes DNT / GPC through', async () => {
    vi.stubEnv('NEXT_PUBLIC_API_URL', 'http://api.test');
    const fetchMock = vi.fn().mockResolvedValue(Response.json({ accepted: 0 }));
    vi.stubGlobal('fetch', fetchMock);
    await POST(request('{}', { origin: 'http://localhost:3000', traceparent: '00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01', dnt: '1', 'sec-gpc': '1' }));
    const headers = fetchMock.mock.calls[0][1].headers;
    expect(headers.traceparent).toMatch(/^00-4bf92f3577b34da6a3ce929d0e0e4736-(?!00f067aa0ba902b7)[0-9a-f]{16}-01$/);
    expect(headers.dnt).toBe('1');
    expect(headers['sec-gpc']).toBe('1');
  });

  it('starts a trace when none is supplied', async () => {
    vi.stubEnv('NEXT_PUBLIC_API_URL', 'http://api.test');
    const fetchMock = vi.fn().mockResolvedValue(Response.json({ accepted: 0 }));
    vi.stubGlobal('fetch', fetchMock);
    await POST(request('{}'));
    expect(fetchMock.mock.calls[0][1].headers.traceparent).toMatch(/^00-[0-9a-f]{32}-[0-9a-f]{16}-01$/);
  });
});
