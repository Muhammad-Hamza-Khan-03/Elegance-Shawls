import { Product } from '@/types/types';

export type CatalogCategory = 'all' | Product['category'];
export type CatalogSort = 'newest' | 'name' | 'price_asc' | 'price_desc';

export interface CatalogFilters {
  query: string;
  category: CatalogCategory;
  sort: CatalogSort;
}

export const filterAndSortProducts = (products: Product[], filters: CatalogFilters) => {
  const query = filters.query.trim().toLocaleLowerCase();
  const filtered = products.filter((product) => {
    const matchesCategory = filters.category === 'all' || product.category === filters.category;
    const searchText = [product.name, product.description, product.material, product.type]
      .filter(Boolean)
      .join(' ')
      .toLocaleLowerCase();
    return matchesCategory && (!query || searchText.includes(query));
  });

  return [...filtered].sort((a, b) => {
    if (filters.sort === 'name') return a.name.localeCompare(b.name);
    if (filters.sort === 'price_asc') return a.price - b.price;
    if (filters.sort === 'price_desc') return b.price - a.price;
    return Date.parse(b.createdAt || '1970-01-01') - Date.parse(a.createdAt || '1970-01-01');
  });
};
