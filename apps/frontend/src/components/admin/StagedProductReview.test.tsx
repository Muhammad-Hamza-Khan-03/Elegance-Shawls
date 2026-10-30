import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { EnrichmentView, StagedProductCard } from './StagedProductReview';
import type { Enrichment, StagedProduct } from '@/lib/staging';

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
    expect(html.match(/<img /g)).toHaveLength(3); // large photo + one thumbnail per image
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
    for (const label of ['Approve', 'Reject', 'Publish', 'Unpublish', 'Archive']) expect(html).not.toContain(`> ${label}</button>`);
    expect(html).not.toContain('<footer');
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

describe('review card layout and description', () => {
  const markdown = '## Why you will love it\n\nA **soft** wrap.\n\n- Warm colour\n- Fringed edges';

  it('renders the description as headings, paragraphs and lists, not one block of text', () => {
    const html = render({ product: { ...item().product, main_description: markdown } });
    expect(html).toContain('<h4');
    expect(html).toContain('Why you will love it');
    expect(html).toContain('<strong>soft</strong>');
    const list = html.slice(html.indexOf('<ul class="list-disc'));
    expect(list.slice(0, list.indexOf('</ul>')).match(/<li>/g)).toHaveLength(2);
    expect(html).not.toContain('## ');
    expect(html).not.toContain('**');
  });

  it('collapses a long description behind a toggle but keeps it in the page', () => {
    const long = Array.from({ length: 30 }, (_, i) => `Paragraph ${i} with some descriptive text about the shawl.`).join('\n\n');
    const html = render({ product: { ...item().product, main_description: long } });
    expect(html).toContain('Read full description');
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain('Paragraph 29');
    expect(render()).not.toContain('Read full description');
  });

  it('uses the shared category label, shows the source as host and path, and marks missing details honestly', () => {
    const html = render({ product: { ...item().product, category: 'scarves' } });
    expect(html).toContain('Scarves');
    expect(html).toContain('shop.example/products/pearl');
    expect(html).toContain('Not provided');
    expect(html).toContain('aria-label="Product photos"');
  });

  it('never turns description markup into elements or links', () => {
    const html = render({ product: { ...item().product, main_description: '<img src=x onerror=alert(1)> [click](https://evil.example) <script>alert(1)</script>' } });
    expect(html).not.toContain('<script>alert(1)</script>');
    expect(html).not.toContain('<img src="x"');
    expect(html).toContain('&lt;img src=x');
    expect(html).not.toContain('href="https://evil.example"');
  });
});

const run = (over: Partial<Enrichment> = {}): Enrichment => ({
  id: '11111111-1111-4111-8111-111111111111',
  staged_product_id: '22222222-2222-4222-8222-222222222222',
  status: 'succeeded',
  authoritative: false,
  suggestions: {
    pattern: { value: 'floral', reason: 'Embroidered flowers <b>visible</b>', source: 'visual_suggestion' },
    season: { value: null, reason: 'Cannot tell from the photo', source: 'visual_suggestion' },
  },
  validation_errors: [],
  provider: 'fixture-provider',
  model: 'fixture-model',
  prompt_version: 'p1',
  vocabulary_version: 'v1',
  input_content_hash: 'abc123hash',
  attempts: 1,
  trace_id: 'trace-9',
  created_at: '2026-01-01T00:00:00Z',
  started_at: '2026-01-01T00:00:05Z',
  finished_at: '2026-01-01T00:00:09Z',
  ...over,
});

const view = (data: Enrichment | null | undefined, over: Partial<Parameters<typeof EnrichmentView>[0]> = {}) =>
  renderToStaticMarkup(
    <EnrichmentView stagedStatus="pending_review" data={data} busy={false} error={null} notice={null} onRequest={() => {}} onCancel={() => {}} onRefresh={() => {}} {...over} />
  );

describe('enrichment panel', () => {
  it('shows the advisory label, provenance, metadata and escaped text', () => {
    const html = view(run());
    for (const text of ['Advisory suggestion — not catalogue truth', 'succeeded', 'floral', 'Reason: Embroidered flowers &lt;b&gt;visible&lt;/b&gt;', 'Source: visual_suggestion',
      'No suggestion', 'fixture-provider', 'fixture-model', 'abc123hash', 'trace-9', 'Attempts:', '2026-01-01 00:00:09 UTC']) expect(html).toContain(text);
    expect(html).not.toContain('<b>visible</b>');
  });

  it('never offers apply, edit or approval controls', () => {
    expect(view(run())).not.toMatch(/Apply|Auto-fill|Approve|Publish|<input|<textarea/);
  });

  it('shows an intentional empty state and offers a request', () => {
    const html = view(null);
    expect(html).toContain('No suggestions have been requested');
    expect(html).toContain('Request suggestions');
    expect(html).not.toContain('Cancel run');
  });

  it('offers cancel but no request while queued or running', () => {
    for (const status of ['queued', 'running'] as const) {
      const html = view(run({ status, suggestions: null }));
      expect(html).toContain('Cancel run');
      expect(html).not.toContain('Request new suggestions');
    }
  });

  it('allows re-request after a terminal state', () => {
    for (const status of ['succeeded', 'failed', 'cancelled'] as const) expect(view(run({ status }))).toContain('Request new suggestions');
  });

  it.each(['rejected', 'archived'] as const)('does not offer a request for %s products', (stagedStatus) => {
    const html = view(run(), { stagedStatus });
    expect(html).not.toContain('Request new suggestions');
    expect(html).toContain('cannot be requested');
  });

  it('shows validation warnings and failures as alerts', () => {
    const html = view(run({ status: 'failed', suggestions: null, validation_errors: ['pattern: value is not in the canonical vocabulary'], last_error: 'provider_timeout' }));
    expect(html).toContain('role="alert"');
    expect(html).toContain('pattern: value is not in the canonical vocabulary');
    expect(html).toContain('The run failed: provider_timeout');
  });

  it('announces errors, notices and loading', () => {
    expect(view(undefined)).toContain('role="status"');
    expect(view(null, { error: 'Job queue is unavailable. Try again shortly.' })).toContain('role="alert"');
    expect(view(run(), { notice: 'Suggestion run requested.' })).toContain('role="status"');
  });

  it('disables the request button while busy', () => {
    expect(view(null, { busy: true })).toMatch(/<button[^>]*disabled=""[^>]*>[^]*Request suggestions/);
  });

  it('is only mounted for UUID staged ids', () => {
    expect(renderToStaticMarkup(<StagedProductCard item={item()} />)).not.toContain('Enrichment suggestions');
    expect(renderToStaticMarkup(<StagedProductCard item={item({ _id: '22222222-2222-4222-8222-222222222222' })} />)).toContain('Enrichment suggestions');
  });
});
