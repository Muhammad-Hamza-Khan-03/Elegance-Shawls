import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { Footer } from './layout/Footer';
import { Navbar } from './layout/Navbar';
import { InfoPage } from './layout/InfoPage';
import { ProductExperience } from './product/ProductExperience';
import { Product } from '@/types/types';

const product: Product = {
  id: 'p1', name: 'Test Shawl', slug: 'test-shawl', description: 'A test product', price: 2500,
  currency: 'PKR', category: 'shawls', images: ['https://example.com/shawl.jpg'], stock: 2,
  status: 'active', createdAt: '2026-01-01', updatedAt: '2026-01-01',
  variants: [{ id: 'v1', color: 'Brown', size: 'Free Size', stock: 2, price: 2500 }],
};

describe('storefront accessibility landmarks and controls', () => {
  it('exposes labelled navigation and a correctly described menu control', () => {
    const html = renderToStaticMarkup(<Navbar />);
    expect(html).toContain('aria-label="Main navigation"');
    expect(html).toContain('aria-label="Open navigation menu"');
    expect(html).toContain('aria-expanded="false"');
    expect(html).not.toContain('aria-label="Mobile navigation"');
  });

  it('provides discoverable customer-information links in the footer', () => {
    const html = renderToStaticMarkup(<Footer />);
    for (const path of ['/delivery', '/returns', '/contact', '/privacy', '/terms']) expect(html).toContain(`href="${path}"`);
  });

  it('gives information pages a skip-link destination and heading hierarchy', () => {
    const html = renderToStaticMarkup(<InfoPage eyebrow="Help" title="Delivery" intro="Details"><section><h2>Timing</h2><p>Confirmed directly.</p></section></InfoPage>);
    expect(html).toContain('<main id="main-content"');
    expect(html).toContain('<h1');
    expect(html).toContain('<h2>Timing</h2>');
  });

  it('labels product option and quantity controls for assistive technology', () => {
    const html = renderToStaticMarkup(<ProductExperience product={product} siteUrl="https://example.com" whatsappNumber="923001234567" />);
    expect(html).toContain('role="radiogroup"');
    expect(html).toContain('aria-label="Available product options"');
    expect(html).toContain('<label for="quantity"');
    expect(html).toContain('type="number"');
  });
});
