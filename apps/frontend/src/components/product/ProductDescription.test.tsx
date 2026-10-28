import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { CartProvider } from '@/components/cart/CartProvider';
import { ProductExperience } from './ProductExperience';
import type { Product } from '@/types/types';

const BASE = 'https://shop.example/cdn/shop/files/';
const DESCRIPTION = '## Classic Wrap\n\nComplete your wardrobe with this **soft** shawl.\n\n## Why you will love it\n\n- Warm colour\n- Fringed edges\n\n### Is it warm?\n\nYes, medium weight.';

const product: Product = {
  id: 'p1', name: 'Cream Shawl', slug: 'cream-shawl', description: DESCRIPTION, price: 24340, currency: 'PKR', category: 'shawls',
  images: [`${BASE}a.jpg`, `${BASE}a_1800x1800.jpg`, `${BASE}b.jpg`, `${BASE}b.jpg?width=1200`, `${BASE}c.jpg`],
  stock: 2, status: 'active', createdAt: '2026-01-01', updatedAt: '2026-01-01',
  variants: [{ id: 'v1', color: 'Cream', size: 'Free Size', price: 24340, stock: 2, image_url: `${BASE}a.jpg` }],
};

const render = (over: Partial<Product> = {}) =>
  renderToStaticMarkup(<CartProvider><ProductExperience product={{ ...product, ...over }} siteUrl="https://store.example" whatsappNumber="923001234567" /></CartProvider>);

describe('product page description and gallery', () => {
  it('renders the description as headings, paragraphs and lists in its own section, with no raw markers', () => {
    const html = render();
    const section = html.slice(html.indexOf('id="product-details"'));
    expect(section).toContain('About this product');
    expect(section).toContain('<h4');
    expect(section).toContain('Why you will love it');
    expect(section).toContain('<strong>soft</strong>');
    expect(section.match(/<li>/g)).toHaveLength(2);
    expect(html).not.toContain('## ');
    expect(html).not.toContain('**');
  });

  it('keeps the buy panel short: a one-paragraph teaser that links to the full description', () => {
    const html = render();
    const panel = html.slice(0, html.indexOf('id="product-details"'));
    expect(panel).toContain('Complete your wardrobe with this soft shawl.');
    expect(panel).toContain('href="#product-details"');
    expect(panel).not.toContain('Why you will love it');
  });

  it('shows each picture once in the gallery', () => {
    const html = render();
    expect(html.match(/aria-label="View product image \d+"/g)).toHaveLength(3);
  });

  it('omits the description section when there is no description', () => {
    expect(render({ description: '' })).not.toContain('id="product-details"');
  });

  it('shows legacy single-block descriptions as one paragraph', () => {
    const html = render({ description: 'Plain text from an older import.' });
    expect(html).toContain('Plain text from an older import.');
    expect(html).toContain('id="product-details"');
  });
});
