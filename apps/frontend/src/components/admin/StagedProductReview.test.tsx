import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { StagedProductCard } from './StagedProductReview';
import type { StagedProduct } from '@/lib/staging';

const item = (over: Partial<StagedProduct> = {}): StagedProduct => ({
  _id: '507f1f77bcf86cd799439011',
  source_name: 'Fixture Shop',
  source_url: 'https://shop.example/products/pearl',
  source_price: 189,
  source_currency: 'AUD',
  status: 'pending_review',
  missing_fields: ['price', 'stock', 'weight'],
  stock_known: false,
  product: {
    name: 'Pearl Cashmere Shawl',
    cover_image_url: 'https://shop.example/a.jpg',
    images: ['https://shop.example/a.jpg', 'https://shop.example/b.jpg'],
    main_description: 'Hand-finished cashmere.',
    category: 'shawls',
    material: '100% Pure Cashmere',
    variants: [{ name: 'Pearl', stock: 0 }],
  },
  created_at: '2026-01-01T00:00:00Z',
  ...over,
});

const render = (over?: Partial<StagedProduct>) => renderToStaticMarkup(<StagedProductCard item={item(over)} />);

describe('staged product review card', () => {
  it('shows what a reviewer needs', () => {
    const html = render();
    expect(html).toContain('Pearl Cashmere Shawl');
    expect(html).toContain('Fixture Shop');
    expect(html).toContain('https://shop.example/products/pearl');
    expect(html).toContain('189.00 AUD');
    expect(html).toContain('Unknown — reviewer must set');
    expect(html).toContain('pending review');
    expect(html).toContain('Hand-finished cashmere.');
    expect(html.match(/<img /g)).toHaveLength(2);
    expect(html).toContain('Retail price (PKR) — set on approval');
    expect(html).toContain('Weight');
  });

  it('offers approve and reject, but not publish, before approval', () => {
    const html = render();
    expect(html).toContain('Approve');
    expect(html).toContain('Reject');
    expect(html).not.toContain('Publish');
    expect(html).not.toContain('Unpublish');
  });

  it('offers publish and archive once approved', () => {
    const html = render({ status: 'approved', missing_fields: [], stock_known: true });
    expect(html).toContain('Publish');
    expect(html).toContain('Archive');
    expect(html).not.toContain('Approve');
    expect(html).not.toContain('data-testid="missing-fields"');
  });

  it('offers unpublish when live', () => {
    const html = render({ status: 'published' });
    expect(html).toContain('Unpublish');
    expect(html).not.toMatch(/>\s*Publish\s*</);
  });

  it('shows the rejection reason and only archive for rejected products', () => {
    const html = render({ status: 'rejected', rejection_reason: 'Blurry photos' });
    expect(html).toContain('Rejected: Blurry photos');
    expect(html).toContain('Archive');
    expect(html).not.toContain('Publish');
  });

  it('offers nothing for archived products', () => {
    const html = render({ status: 'archived' });
    expect(html).not.toContain('<button');
  });

  it('flags a source change that was not applied', () => {
    expect(render({ status: 'approved', latest_source_hash: 'abc' })).toContain('source changed after review');
  });

  it('renders untrusted text as text, not markup', () => {
    const html = render({ product: { ...item().product, name: '<script>alert(1)</script>' } });
    expect(html).not.toContain('<script>alert(1)</script>');
    expect(html).toContain('&lt;script&gt;');
  });

  it('shows unknown currency honestly', () => {
    expect(render({ source_currency: null })).toContain('currency unknown');
  });
});

describe('PKR suggestion control', () => {
  it('offers a suggestion only when the source price and currency are known, and never pre-fills the price', () => {
    const known = renderToStaticMarkup(<StagedProductCard item={item()} />);
    expect(known).toContain('Suggest from source price');
    expect(known).not.toContain('data-testid="pkr-suggestion"'); // nothing is fetched until the reviewer asks
    expect(known).toMatch(/Retail price \(PKR\)[\s\S]*?value=""/);
    expect(renderToStaticMarkup(<StagedProductCard item={item({ source_price: null })} />)).not.toContain('Suggest from source price');
    expect(renderToStaticMarkup(<StagedProductCard item={item({ source_currency: null })} />)).not.toContain('Suggest from source price');
  });

  it('is not offered once a product is past approval', () => {
    expect(renderToStaticMarkup(<StagedProductCard item={item({ status: 'approved' })} />)).not.toContain('Suggest from source price');
  });
});
