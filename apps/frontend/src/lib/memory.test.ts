import { describe, expect, it, vi, beforeEach } from 'vitest';
import { memoryApi } from './memory';

describe('memoryApi', () => {
  beforeEach(() => vi.restoreAllMocks());
  it('uses the authenticated principal seam and never sends a customer id', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ items: [] }), { status: 200 }));
    await memoryApi.list();
    expect(fetchMock).toHaveBeenCalledWith('/api/customer/memory', expect.objectContaining({ cache: 'no-store' }));  // same-origin proxy; the cookie becomes the session header there
    expect(String(fetchMock.mock.calls[0][0])).not.toMatch(/customer_id|user_id|principal|\?/i);
  });
  it('turns an unauthenticated response into a typed 401 error', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 401 }));
    await expect(memoryApi.getConsent()).rejects.toMatchObject({ status: 401, message: 'Sign in is required to manage memory.' });
  });
  it('sends explicit consent and delete requests', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => new Response(init?.method === 'DELETE' && String(_input) !== '/api/customer/memory' ? null : JSON.stringify({ granted: true }), { status: init?.method === 'DELETE' ? 204 : 200 }));
    await memoryApi.setConsent(true);
    await memoryApi.remove('memory-1');
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'PUT', body: JSON.stringify({ granted: true }) });
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: 'DELETE' });
  });
  it('creates a memory from the memory page with an idempotency key and no customer id', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ id: 'm1' }), { status: 201 }));
    await memoryApi.create({ category: 'preference', key: 'favourite_colour', value: 'brown' });
    const [url, init] = fetchMock.mock.calls[0];
    const sent = JSON.parse(String(init?.body));
    expect(url).toBe('/api/customer/memory');
    expect(init).toMatchObject({ method: 'POST' });
    expect(sent).toMatchObject({ category: 'preference', key: 'favourite_colour', value: 'brown', source: 'memory_page' });
    expect(sent.idempotency_key).toMatch(/^idem_[A-Za-z0-9_-]{16,64}$/);
    expect(Object.keys(sent).join()).not.toMatch(/customer|user|principal/i);
  });
  it('carries the backend refusal reason on the error', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ reason: 'duplicate_key' }), { status: 409 }));
    await expect(memoryApi.create({ category: 'preference', key: 'k', value: 'v' })).rejects.toMatchObject({ status: 409, reason: 'duplicate_key' });
  });
});
