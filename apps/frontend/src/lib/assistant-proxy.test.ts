import { afterEach, describe, expect, it, vi } from 'vitest';
import { POST as stream } from '@/app/api/assistant/stream/route';
import { POST as execute } from '@/app/api/assistant/actions/execute/route';

const req = (path: string, origin?: string) => new Request(`https://store.example.invalid${path}`, {
  method: 'POST', body: '{}', headers: { 'content-type': 'application/json', ...(origin ? { origin } : {}) },
});

afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });

describe('assistant proxies', () => {
  it('404 when the flag is off, without calling the backend', async () => {
    const f = vi.fn(); vi.stubGlobal('fetch', f);
    vi.stubEnv('NEXT_PUBLIC_API_URL', 'https://api.example.invalid');
    expect((await stream(req('/api/assistant/stream', 'https://store.example.invalid'))).status).toBe(404);
    expect(f).not.toHaveBeenCalled();
  });

  it('rejects cross-origin and missing-origin posts', async () => {
    vi.stubEnv('NEXT_PUBLIC_ASSISTANT_ENABLED', 'true'); vi.stubEnv('NEXT_PUBLIC_API_URL', 'https://api.example.invalid');
    const f = vi.fn(); vi.stubGlobal('fetch', f);
    expect((await execute(req('/api/assistant/actions/execute', 'https://evil.example.invalid'))).status).toBe(403);
    expect((await execute(req('/api/assistant/actions/execute'))).status).toBe(403);
    expect(f).not.toHaveBeenCalled();
  });

  it('forwards to the v1 route and never sends the admin key', async () => {
    vi.stubEnv('NEXT_PUBLIC_ASSISTANT_ENABLED', 'true'); vi.stubEnv('NEXT_PUBLIC_API_URL', 'https://api.example.invalid'); vi.stubEnv('ADMIN_API_KEY', 'secret');
    const f = vi.fn().mockResolvedValue(new Response('data: [DONE]\n\n', { headers: { 'content-type': 'text/event-stream', 'x-vercel-ai-ui-message-stream': 'v1' } }));
    vi.stubGlobal('fetch', f);
    const res = await stream(req('/api/assistant/stream', 'https://store.example.invalid'));
    expect(res.headers.get('x-vercel-ai-ui-message-stream')).toBe('v1');
    const [url, init] = f.mock.calls[0];
    expect(url).toBe('https://api.example.invalid/v1/assistant/stream');
    expect(JSON.stringify(init.headers).toLowerCase()).not.toContain('x-admin-key');
  });
});
