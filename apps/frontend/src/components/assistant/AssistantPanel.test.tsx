import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { initialState, reduce, type AssistantEvent } from '@/lib/assistant-stream';
import { CartProvider } from '@/components/cart/CartProvider';
import { AssistantTurn } from './AssistantPanel';

const P = '11111111-1111-4111-8111-111111111111';
const KEY = 'idem_0123456789abcdef';
const run = (events: AssistantEvent[]) => events.reduce(reduce, initialState());
const start: AssistantEvent = { seq: 0, type: 'start', meta: { session_id: 's', idempotency_key: KEY, context: {} } };
const params = { product_id: P, variant_id: P, quantity: 1, expected_revision: 7, expected_unit_price: 3500, currency: 'PKR' };
const validated = (seq: number, action_type: string, withParams = true): AssistantEvent =>
  ({ seq, type: 'proposal', action_type, idempotency_key: KEY, decision: { outcome: 'validated', reason: 'ok', replayed: false }, ...(withParams && { params }) });
const render = (state: ReturnType<typeof run>, retry?: () => void) => renderToStaticMarkup(<CartProvider><AssistantTurn state={state} onRetry={retry} /></CartProvider>);
const card = { seq: 1, type: 'product', product: { product_id: P, name: 'Wool Shawl', price: 3500, currency: 'PKR', slug: 'wool-shawl', image: 'https://img.example.com/a.jpg', color: 'Brown' } } as AssistantEvent;

describe('AssistantTurn', () => {
  it('escapes server text and product names and shows no markup from them', () => {
    const html = render(run([start, { seq: 1, type: 'text', delta: '<img src=x onerror=alert(1)>' },
      { seq: 2, type: 'product', product: { product_id: P, name: '<b>Shawl</b>', price: 3500, currency: 'PKR' } }]));
    expect(html).not.toContain('<img');
    expect(html).not.toContain('<b>');
    expect(html).toContain('&lt;b&gt;Shawl&lt;/b&gt;');
  });

  it('a product card shows colour, price, picture and link, and a button only when a validated suggestion exists for it', () => {
    const withProposal = render(run([start, card, { ...validated(2, 'add_to_cart') }]));
    expect(withProposal).toContain('Brown · PKR 3500');
    expect(withProposal).toContain('href="/product/wool-shawl"');
    expect(withProposal).toContain('Add to cart');
    expect(withProposal).not.toContain('Yes, add');                       // asking comes first: the confirmation is not even rendered yet
    const without = render(run([start, card]));
    expect(without).not.toContain('Add to cart');
    expect(without).toContain('Not available to add right now');
  });

  it('a rejected or param-less suggestion never becomes a control', () => {
    const html = render(run([start, card,
      { seq: 2, type: 'proposal', action_type: 'add_to_cart', idempotency_key: KEY, decision: { outcome: 'rejected', reason: 'stale_price', replayed: false } },
      validated(3, 'start_whatsapp_enquiry', false)]));
    expect(html).toContain('not accepted, so nothing was done');
    expect(html).not.toContain('stale_price');
    expect(html).not.toContain('Add to cart');
    expect(html).not.toContain('Confirm:');
  });

  it('offers one explicit confirm control for a validated enquiry that carries params', () => {
    const html = render(run([start, card, validated(2, 'start_whatsapp_enquiry', false), { ...validated(3, 'start_whatsapp_enquiry'), params: { items: [params] } } as AssistantEvent]));
    expect(html.match(/Confirm: start WhatsApp enquiry/g)).toHaveLength(1);
    expect(html).toContain('Nothing is sent until you open WhatsApp');
  });

  it('shows a safe error with an optional retry, and never the raw code', () => {
    const state = run([start, { seq: 1, type: 'error', code: 'provider_malformed' }]);
    expect(render(state)).toContain('unreadable reply');
    expect(render(state)).not.toContain('provider_malformed');
    expect(render(state)).not.toContain('Try again');
    expect(render(state, () => undefined)).toContain('Try again');
  });

  it('renders a memory suggestion as a question with Save and No thanks', () => {
    const html = render(run([start, { seq: 1, type: 'memory_suggestion', key: 'favourite_colour', value: 'pink' }]));
    expect(html).toContain('Remember your favourite colour');
    expect(html).toContain('>Save<');
    expect(html).toContain('No thanks');
  });
});
