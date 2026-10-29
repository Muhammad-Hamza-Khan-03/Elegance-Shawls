import { afterEach, describe, expect, it, vi } from 'vitest';
import { internalApiHeaders, mapBackendProduct } from './api';
import { createCartItem } from './cart';
import { validateSingleProductOrder } from './whatsapp';

const productWith = (variant: Record<string, unknown>) =>
  mapBackendProduct({
    _id: 'p1',
    name: 'Classic Wool Shawl',
    slug: 'classic-wool-shawl',
    price: 4500,
    status: 'active',
    variants: [{ _id: 'v1', color: 'Brown', price: 4500, image_url: 'https://images.example.com/brown.jpg', ...variant }],
  } as Parameters<typeof mapBackendProduct>[0]);

describe('backend product stock mapping', () => {
  it.each([
    ['missing stock and status', {}],
    ['missing stock with "In stock" status', { stock_status: 'In stock' }],
    ['null stock', { stock: null }],
    ['zero stock', { stock: 0 }],
    ['negative stock', { stock: -3 }],
    ['fractional stock', { stock: 2.5 }],
    ['non-finite stock', { stock: Number.NaN }],
    ['string stock', { stock: '10' }],
    ['positive stock marked out of stock', { stock: 4, stock_status: 'Out of stock' }],
  ])('treats %s as unavailable', (_label, variant) => {
    const product = productWith(variant);
    expect(product.variants[0].stock).toBe(0);
    expect(product.stock).toBe(0);
    expect(createCartItem(product, product.variants[0])).toBeNull();
    expect(validateSingleProductOrder({ variant: product.variants[0], quantity: 1, productUrl: 'https://store.example.invalid/product/classic-wool-shawl' }))
      .toBe('This option is currently out of stock.');
  });

  it('keeps real backend stock orderable', () => {
    const product = productWith({ stock: 3, stock_status: 'In stock' });
    expect(product.variants[0].stock).toBe(3);
    expect(product.stock).toBe(3);
    expect(createCartItem(product, product.variants[0], 2)?.quantity).toBe(2);
    expect(validateSingleProductOrder({ variant: product.variants[0], quantity: 3, productUrl: 'https://store.example.invalid/product/classic-wool-shawl' })).toBeNull();
    expect(validateSingleProductOrder({ variant: product.variants[0], quantity: 4, productUrl: 'https://store.example.invalid/product/classic-wool-shawl' }))
      .toBe('Only 3 items available.');
  });

  it('sums only real stock across variants', () => {
    const product = mapBackendProduct({
      _id: 'p2',
      slug: 'light-silk-stole',
      variants: [{ _id: 'a', stock: 2 }, { _id: 'b' }, { _id: 'c', stock: 5 }],
    });
    expect(product.variants.map((variant) => variant.stock)).toEqual([2, 0, 5]);
    expect(product.stock).toBe(7);
  });
});

describe('internal API token', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it('is sent from the server when configured', () => {
    vi.stubEnv('INTERNAL_API_TOKEN', 'server-only-fixture');
    expect(internalApiHeaders()).toEqual({ 'X-Internal-API-Token': 'server-only-fixture' });
  });

  it('is never sent from the browser', () => {
    vi.stubEnv('INTERNAL_API_TOKEN', 'server-only-fixture');
    vi.stubGlobal('window', {});
    expect(internalApiHeaders()).toEqual({});
  });

  it('is omitted when not configured', () => {
    vi.stubEnv('INTERNAL_API_TOKEN', '');
    expect(internalApiHeaders()).toEqual({});
  });
});

describe('trace headers on storefront reads', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  const lastHeaders = (fetchMock: ReturnType<typeof vi.fn>) => fetchMock.mock.calls.at(-1)![1].headers as Record<string, string>;

  it('sends a valid traceparent from the browser and never the internal token', async () => {
    vi.resetModules();
    vi.stubEnv('NEXT_PUBLIC_API_URL', 'http://api.test');
    vi.stubEnv('INTERNAL_API_TOKEN', 'server-only-fixture');
    vi.stubGlobal('window', {});
    const fetchMock = vi.fn().mockResolvedValue(Response.json({ items: [], next_cursor: null }));
    vi.stubGlobal('fetch', fetchMock);
    const { api } = await import('./api');
    await api.getProducts();
    expect(lastHeaders(fetchMock).traceparent).toMatch(/^00-[0-9a-f]{32}-[0-9a-f]{16}-01$/);
    expect(lastHeaders(fetchMock)['X-Internal-API-Token']).toBeUndefined();
  });

  it('sends the internal token but no traceparent from the server', async () => {
    vi.resetModules();
    vi.stubEnv('NEXT_PUBLIC_API_URL', 'http://api.test');
    vi.stubEnv('INTERNAL_API_TOKEN', 'server-only-fixture');
    const fetchMock = vi.fn().mockResolvedValue(Response.json({ items: [], next_cursor: null }));
    vi.stubGlobal('fetch', fetchMock);
    const { api } = await import('./api');
    await api.getProducts();
    expect(lastHeaders(fetchMock)).toEqual({ 'X-Internal-API-Token': 'server-only-fixture' });
  });
});
