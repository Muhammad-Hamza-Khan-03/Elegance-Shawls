import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const item = (id: string, status = 'active') => ({ _id: id, name: id, slug: id, status, price: 10, variants: [] });

const load = async (fetchMock: ReturnType<typeof vi.fn>) => {
  vi.resetModules();
  vi.stubEnv('NEXT_PUBLIC_API_URL', 'http://api.test');
  vi.stubGlobal('fetch', fetchMock);
  return (await import('./api')).api;
};

beforeEach(() => vi.spyOn(console, 'error').mockImplementation(() => {}));
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe('catalogue cursor pagination', () => {
  it('getProductPage fetches one page only and exposes the cursor', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(Response.json({ items: [item('a'), item('d', 'draft')], next_cursor: 'c1' }));
    const page = await (await load(fetchMock)).getProductPage();
    expect(page.items.map((p) => p.id)).toEqual(['a']);
    expect(page.nextCursor).toBe('c1');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('getAllProducts follows next_cursor, dedupes across page boundaries and drops inactive rows', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(Response.json({ items: [item('a'), item('b')], next_cursor: 'c1' }))
      .mockResolvedValueOnce(Response.json({ items: [item('b'), item('c'), item('d', 'draft')], next_cursor: 'c 2' }))
      .mockResolvedValueOnce(Response.json({ items: [item('e')], next_cursor: null }));
    const api = await load(fetchMock);
    const products = await api.getAllProducts();
    expect(products.map((p) => p.id)).toEqual(['a', 'b', 'c', 'e']);
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      'http://api.test/products/?limit=100',
      'http://api.test/products/?limit=100&cursor=c1',
      'http://api.test/products/?limit=100&cursor=c%202',
    ]);
  });

  it('keeps paging through a short page while next_cursor is set', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(Response.json({ items: [], next_cursor: 'c1' }))
      .mockResolvedValueOnce(Response.json({ items: [item('a')], next_cursor: null }));
    expect((await (await load(fetchMock)).getAllProducts()).map((p) => p.id)).toEqual(['a']);
  });

  it('fails instead of looping when the cursor does not advance', async () => {
    const fetchMock = vi.fn().mockImplementation(async () => Response.json({ items: [item('a')], next_cursor: 'same' }));
    await expect((await load(fetchMock)).getAllProducts()).rejects.toThrow(/did not advance/);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe('getProductBySlug error semantics', () => {
  it('returns undefined for a real 404 with exactly one request and no catalogue fallback', async () => {
    const fetchMock = vi.fn().mockResolvedValue(Response.json({ detail: 'Product not found' }, { status: 404 }));
    expect(await (await load(fetchMock)).getProductBySlug('nope')).toBeUndefined();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).toBe('http://api.test/products/slug/nope');
  });

  it.each([429, 503])('throws on HTTP %i without a fallback request', async (status) => {
    const fetchMock = vi.fn().mockResolvedValue(Response.json({ detail: 'busy' }, { status }));
    await expect((await load(fetchMock)).getProductBySlug('x')).rejects.toThrow('busy');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('propagates a network failure and a timeout', async () => {
    const network = vi.fn().mockRejectedValue(new TypeError('fetch failed'));
    await expect((await load(network)).getProductBySlug('x')).rejects.toThrow('fetch failed');
    const timeout = vi.fn().mockRejectedValue(new DOMException('timed out', 'TimeoutError'));
    await expect((await load(timeout)).getProductBySlug('x')).rejects.toMatchObject({ name: 'TimeoutError' });
    expect(timeout).toHaveBeenCalledTimes(1);
    expect(timeout.mock.calls[0][1].signal).toBeInstanceOf(AbortSignal);
  });
});
