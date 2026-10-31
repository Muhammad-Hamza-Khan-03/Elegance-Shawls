import { afterEach, describe, expect, it, vi } from 'vitest';
import { StaleCartError, createEnquiry } from '@/lib/enquiry';
import { createCartItem } from '@/lib/cart';
import type { Product, ProductVariant } from '@/types/types';

const variant = { id: 'v1', color: 'Brown', size: 'Free Size', stock: 3, price: 4500, image_url: 'x' } as ProductVariant;
const product = { id: 'p1', name: 'Shawl', slug: 'shawl', description: '', price: 4500, currency: 'PKR', category: 'shawls', images: ['x'], variants: [variant] } as unknown as Product;
const items = [createCartItem(product, variant, 2)!];

const respond = (status: number, body: unknown) => vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })));

afterEach(() => vi.unstubAllGlobals());

describe('createEnquiry', () => {
  it('posts only ids, quantity and the cart price to the same-origin proxy and returns the reference', async () => {
    respond(201, { reference: 'ES-7F3K9Q' });
    await expect(createEnquiry(items)).resolves.toBe('ES-7F3K9Q');
    const [url, init] = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe('/api/enquiries');
    expect(JSON.parse(init.body)).toEqual({ items: [{ product_id: 'p1', variant_id: 'v1', quantity: 2, unit_price: 4500, currency: 'PKR' }] });
  });

  it('surfaces a stale cart so the page re-verifies instead of handing off', async () => {
    respond(409, { detail: { code: 'cart_stale', issues: [{ reason: 'price_changed', variant_id: 'v1', product_id: 'p1' }] } });
    await expect(createEnquiry(items)).rejects.toBeInstanceOf(StaleCartError);
  });

  it('fails without a reference on server errors or a malformed answer', async () => {
    respond(503, { detail: 'down' });
    await expect(createEnquiry(items)).rejects.toThrow(/could not create/);
    respond(201, {});
    await expect(createEnquiry(items)).rejects.toThrow(/could not create/);
  });
});
