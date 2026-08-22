import { describe, expect, it } from 'vitest';
import {
  addCartItem,
  buildCartCheckoutUrl,
  clampCartQuantity,
  createCartItem,
  getCartLineId,
  getCartSummary,
  incrementCartItem,
  decrementCartItem,
  removeCartItem,
  setCartItemQuantity,
} from './cart';
import type { Product, ProductVariant } from '@/types/types';

const variantA: ProductVariant = { id: 'brown-free', color: 'Brown', size: 'Free Size', stock: 3, price: 4500 };
const variantB: ProductVariant = { id: 'beige-free', color: 'Beige', size: 'Free Size', stock: 2, price: 4200 };

const product: Product = {
  id: 'p1',
  name: 'Classic Wool Shawl',
  slug: 'classic-wool-shawl',
  description: 'Warm and elegant.',
  price: 4500,
  currency: 'PKR',
  category: 'shawls',
  images: ['https://images.test/shawl.jpg'],
  variants: [variantA, variantB],
  stock: 5,
  status: 'active',
  itemNumber: 'ES-001',
  createdAt: '2026-01-01',
  updatedAt: '2026-01-01',
};

describe('cart state helpers', () => {
  it('builds stable line ids and clamps quantities against stock', () => {
    expect(getCartLineId('p1', 'v1')).toBe('p1:v1');
    expect(clampCartQuantity(0, 3)).toBe(1);
    expect(clampCartQuantity(9, 3)).toBe(3);
    expect(clampCartQuantity(2, 0)).toBe(0);
  });

  it('adds multiple products and merges the same variant while respecting stock', () => {
    const first = createCartItem(product, variantA, 2);
    expect(first?.quantity).toBe(2);

    const items = addCartItem([], product, variantA, 2);
    const withSecondProduct = addCartItem(items, product, variantB, 1);

    expect(withSecondProduct).toHaveLength(2);
    expect(withSecondProduct.map((item) => item.variantId)).toEqual(['brown-free', 'beige-free']);

    const merged = addCartItem(withSecondProduct, product, variantA, 2);
    expect(merged.find((item) => item.variantId === 'brown-free')?.quantity).toBe(3);
  });

  it('updates and removes cart lines with stock-aware editing', () => {
    const items = addCartItem([], product, variantA, 1);
    expect(incrementCartItem(items, 'p1:brown-free')[0].quantity).toBe(2);
    expect(setCartItemQuantity(items, 'p1:brown-free', 99)[0].quantity).toBe(3);
    expect(decrementCartItem(items, 'p1:brown-free')).toHaveLength(0);
    expect(removeCartItem(items, 'p1:brown-free')).toHaveLength(0);
  });

  it('summarises totals and produces a checkout url', () => {
    const items = addCartItem(addCartItem([], product, variantA, 1), product, variantB, 2);
    expect(getCartSummary(items)).toEqual({ itemCount: 3, subtotal: 12900, currency: 'PKR' });
    expect(buildCartCheckoutUrl(items, '923001234567')).toContain('wa.me/923001234567');
  });
});
