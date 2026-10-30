import { describe, expect, it, vi, beforeEach } from 'vitest';
import { memoryApi } from './memory';

describe('memoryApi', () => {
  beforeEach(() => vi.restoreAllMocks());
  it('uses the authenticated principal seam and never sends a customer id', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ items: [] }), { status: 200 }));
    await memoryApi.list();
    expect(fetchMock).toHaveBeenCalledWith('/v1/me/memory', expect.objectContaining({ cache: 'no-store' }));
    expect(String(fetchMock.mock.calls[0][0])).not.toMatch(/customer|user|principal/i);
  });
  it('turns an unauthenticated response into a typed 401 error', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 401 }));
    await expect(memoryApi.getConsent()).rejects.toMatchObject({ status: 401, message: 'Sign in is required to manage memory.' });
  });
  it('sends explicit consent and delete requests', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => new Response(init?.method === 'DELETE' && String(_input) !== '/v1/me/memory' ? null : JSON.stringify({ granted: true }), { status: init?.method === 'DELETE' ? 204 : 200 }));
    await memoryApi.setConsent(true);
    await memoryApi.remove('memory-1');
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'PUT', body: JSON.stringify({ granted: true }) });
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: 'DELETE' });
  });
});
