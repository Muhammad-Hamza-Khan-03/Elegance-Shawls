import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { initialState, reduce, type AssistantEvent } from '@/lib/assistant-stream';
import { CartProvider } from '@/components/cart/CartProvider';
import { AssistantView } from './AssistantChat';

const P = '11111111-1111-4111-8111-111111111111';
const run = (events: AssistantEvent[]) => events.reduce(reduce, initialState());
const start: AssistantEvent = { seq: 0, type: 'start', meta: { session_id: 's', idempotency_key: 'idem_0123456789abcdef', context: {} } };

describe('AssistantView', () => {
  it('shows text and product, escaping server-provided markup', () => {
    const html = renderToStaticMarkup(<AssistantView state={run([
      start, { seq: 1, type: 'text', delta: '<img src=x onerror=alert(1)>' },
      { seq: 2, type: 'product', product: { product_id: P, name: '<b>Shawl</b>', price: 3500, currency: 'PKR' } },
    ])} />);
    expect(html).not.toContain('<img');
    expect(html).not.toContain('<b>');
    expect(html).toContain('&lt;b&gt;Shawl&lt;/b&gt;');
    expect(html).toContain('PKR 3500');
  });
  it('shows validated proposals as not yet done and rejected ones without reason internals, and offers no action control', () => {
    const html = renderToStaticMarkup(<AssistantView state={run([
      start,
      { seq: 1, type: 'proposal', action_type: 'add_to_cart', idempotency_key: null, decision: { outcome: 'validated', reason: 'ok', replayed: false } },
      { seq: 2, type: 'proposal', action_type: 'unknown', idempotency_key: null, decision: { outcome: 'rejected', reason: 'stale_price', replayed: false } },
    ])} />);
    expect(html).toContain('nothing has been done yet');
    expect(html).toContain('not accepted, so nothing was done');
    expect(html).not.toContain('stale_price');
    expect(html).not.toMatch(/<button|<a /);
  });
  it('offers an explicit confirm control only for a validated executable proposal that carries params', () => {
    const params = { product_id: P, variant_id: P, quantity: 1, expected_revision: 7, expected_unit_price: 3500, currency: 'PKR' };
    const html = renderToStaticMarkup(<CartProvider><AssistantView state={run([
      start, { seq: 1, type: 'product', product: { product_id: P, name: 'Shawl', price: 3500, currency: 'PKR' } },
      { seq: 2, type: 'proposal', action_type: 'add_to_cart', idempotency_key: 'idem_0123456789abcdef', decision: { outcome: 'validated', reason: 'ok', replayed: false }, params },
      { seq: 3, type: 'proposal', action_type: 'start_whatsapp_enquiry', idempotency_key: 'idem_0123456789abcdee', decision: { outcome: 'rejected', reason: 'stale_price', replayed: false }, params },
    ])} /></CartProvider>);
    expect(html.match(/<button/g)).toHaveLength(1);
    expect(html).toContain('Confirm: add to cart');
    expect(html).toContain('nothing has been done yet');
  });
  it('shows a safe message for errors', () => {
    const html = renderToStaticMarkup(<AssistantView state={run([start, { seq: 1, type: 'error', code: 'provider_malformed' }])} />);
    expect(html).toContain('role="alert"');
    expect(html).toContain('unreadable reply');
  });
});
