export const PRODUCT_CATEGORIES = ['shawls', 'stoles', 'scarves'] as const;
export type ProductCategory = (typeof PRODUCT_CATEGORIES)[number];

export const CATEGORY_LABELS: Record<ProductCategory, string> = {
  shawls: 'Shawls',
  stoles: 'Stoles',
  scarves: 'Scarves',
};

export const isProductCategory = (value: unknown): value is ProductCategory =>
  typeof value === 'string' && (PRODUCT_CATEGORIES as readonly string[]).includes(value);

// Maps backend/legacy category values onto the canonical keys. Anything unrecognised stays a shawl.
export const normalizeCategory = (category: unknown): ProductCategory => {
  const raw =
    typeof category === 'object' && category !== null && 'name' in category
      ? String((category as { name?: string }).name || '')
      : String(category || '');
  const value = raw.toLowerCase();
  if (value.includes('scarf') || value.includes('scarves')) return 'scarves';
  return value.includes('stole') ? 'stoles' : 'shawls';
};
