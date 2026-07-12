import { describe, expect, it } from 'vitest';
import { filterAndSortProducts } from './catalog';
import { Product } from '@/types/types';

const product = (overrides: Partial<Product>): Product => ({
  id: '1', name: 'Classic Shawl', slug: 'classic-shawl', description: 'Warm wool', price: 3000,
  currency: 'PKR', category: 'shawls', images: ['/shawl.jpg'], variants: [], stock: 2,
  status: 'active', createdAt: '2026-01-01', updatedAt: '2026-01-01', ...overrides,
});

const products = [
  product({ id: '1' }),
  product({ id: '2', name: 'Silk Stole', slug: 'silk-stole', description: 'Light silk', category: 'stoles', price: 1800, createdAt: '2026-02-01' }),
];

describe('filterAndSortProducts', () => {
  it('searches customer-facing product fields without case sensitivity', () => {
    expect(filterAndSortProducts(products, { query: 'SILK', category: 'all', sort: 'newest' }).map((item) => item.id)).toEqual(['2']);
  });

  it('filters by category and sorts without mutating the source list', () => {
    const result = filterAndSortProducts(products, { query: '', category: 'shawls', sort: 'price_asc' });
    expect(result.map((item) => item.id)).toEqual(['1']);
    expect(products.map((item) => item.id)).toEqual(['1', '2']);
  });

  it('supports price and name sorting', () => {
    expect(filterAndSortProducts(products, { query: '', category: 'all', sort: 'price_asc' }).map((item) => item.id)).toEqual(['2', '1']);
    expect(filterAndSortProducts(products, { query: '', category: 'all', sort: 'name' }).map((item) => item.id)).toEqual(['1', '2']);
  });
});
