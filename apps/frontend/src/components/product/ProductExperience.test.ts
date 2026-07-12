import { describe, expect, it } from 'vitest';
import { clampQuantity, getInitialVariant } from './ProductExperience';
import type { Product } from '@/types/types';

const product: Product = {
  id: 'p1', name: 'Signature Shawl', slug: 'signature-shawl', description: 'Soft shawl',
  price: 3000, currency: 'PKR', category: 'shawls', images: ['https://images.test/main.jpg'],
  variants: [
    { id: 'red', color: 'Red', size: 'Small', stock: 0, price: 3000 },
    { id: 'blue', color: 'Blue', size: 'Large', stock: 2, price: 5000 },
  ],
  stock: 2, status: 'active', itemNumber: 'ES-9', createdAt: '', updatedAt: '',
};

describe('ProductExperience ordering state', () => {
  it('starts with the first in-stock variant rather than an unavailable option', () => {
    expect(getInitialVariant(product)?.id).toBe('blue');
  });

  it('clamps typed quantities to the selected variant stock', () => {
    expect(clampQuantity(0, 2)).toBe(1);
    expect(clampQuantity(2, 2)).toBe(2);
    expect(clampQuantity(99, 2)).toBe(2);
    expect(clampQuantity(Number.NaN, 2)).toBe(1);
  });
});
