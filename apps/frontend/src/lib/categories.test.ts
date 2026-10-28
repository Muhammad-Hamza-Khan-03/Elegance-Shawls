import { describe, expect, it } from 'vitest';
import { CATEGORY_LABELS, PRODUCT_CATEGORIES, isProductCategory, normalizeCategory } from './categories';
import { mapBackendProduct } from './api';

describe('category contract', () => {
  it('has scarves alongside shawls and stoles, labelled for display', () => {
    expect([...PRODUCT_CATEGORIES]).toEqual(['shawls', 'stoles', 'scarves']);
    expect(CATEGORY_LABELS.scarves).toBe('Scarves');
    expect(CATEGORY_LABELS.shawls).toBe('Shawls');
    expect(CATEGORY_LABELS.stoles).toBe('Stoles');
  });

  it('accepts only canonical keys as URL/query categories', () => {
    expect(isProductCategory('scarves')).toBe(true);
    expect(isProductCategory('scarf')).toBe(false);
    expect(isProductCategory('Scarves')).toBe(false);
    expect(isProductCategory(undefined)).toBe(false);
  });

  it.each([
    ['scarves', 'scarves'], ['scarf', 'scarves'], ['Scarves', 'scarves'], [{ name: 'Scarf' }, 'scarves'],
    ['stoles', 'stoles'], ['stole', 'stoles'], [{ name: 'Stoles' }, 'stoles'],
    ['shawls', 'shawls'], ['shawl', 'shawls'], ['', 'shawls'], [undefined, 'shawls'], ['unknown', 'shawls'],
  ])('maps %j to %s', (input, expected) => {
    expect(normalizeCategory(input)).toBe(expected);
  });

  it('maps backend products to the scarves category and keeps shawl/stole compatibility', () => {
    const map = (category: unknown) => mapBackendProduct({ _id: 'p', slug: 's', category } as Parameters<typeof mapBackendProduct>[0]).category;
    expect(map('scarves')).toBe('scarves');
    expect(map('stoles')).toBe('stoles');
    expect(map('shawls')).toBe('shawls');
    expect(map(undefined)).toBe('shawls');
  });
});
