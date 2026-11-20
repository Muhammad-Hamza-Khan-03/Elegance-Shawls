import { renderToStaticMarkup } from 'react-dom/server';
import { expect, test } from 'vitest';
import { SimilarProducts } from './SimilarProducts';
import type { Product } from '@/types/types';

const p = (slug: string) => ({ id: slug, slug, name: `Name ${slug}`, price: 4500, currency: 'PKR', images: [], variants: [], stock: 1, category: 'shawls' }) as unknown as Product;

test('renders nothing when there is nothing similar', () => {
  expect(renderToStaticMarkup(<SimilarProducts products={[]} />)).toBe('');
});

test('links each similar product', () => {
  const html = renderToStaticMarkup(<SimilarProducts products={[p('a'), p('b')]} />);
  expect(html).toContain('More like this');
  expect(html).toContain('href="/product/a"');
  expect(html).toContain('href="/product/b"');
});
