import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

describe('sitemap backend availability', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubEnv('NEXT_PUBLIC_API_URL', 'https://backend.example.invalid');
    vi.stubEnv('NEXT_PUBLIC_SITE_URL', 'https://store.example.invalid');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it('returns static pages when a stalled backend request is aborted', async () => {
    const timeout = AbortSignal.timeout.bind(AbortSignal);
    vi.spyOn(AbortSignal, 'timeout').mockImplementation(() => timeout(10));
    vi.stubGlobal('fetch', vi.fn((_url, init?: RequestInit) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => reject(init.signal?.reason), { once: true });
    })));

    const { default: sitemap } = await import('./sitemap');
    const entries = await sitemap();

    expect(entries).toHaveLength(7);
    expect(entries.map((entry) => entry.url)).toContain('https://store.example.invalid/products');
  });

  it('includes active product pages when the backend responds', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json([
      { _id: 'fixture', slug: 'fixture-shawl', name: 'Fixture shawl', status: 'active', price: 100 },
    ])));

    const { default: sitemap } = await import('./sitemap');
    const entries = await sitemap();

    expect(entries.map((entry) => entry.url)).toContain('https://store.example.invalid/product/fixture-shawl');
  });
});
