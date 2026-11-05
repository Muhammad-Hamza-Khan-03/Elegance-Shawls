import { describe, expect, it, vi } from 'vitest';
import { ACTION_NAMES, applyAddToCart, buildExecuteBody, markApplied, toProposal, wasApplied } from './assistant';
import type { Product } from '@/types/types';

const out = (extra = {}) => ({ outcome: 'needs_confirmation', reason: 'needs_confirmation', action_id: 'act_1234567890123456', fingerprint: 'fp', requires_confirmation: true, executed: false, ...extra });
const line = { product_id: 'p1', variant_id: 'v1', quantity: 2 };
const product = (stock = 3, status = 'active') => ({
  id: 'p1', name: 'Shawl', slug: 's', description: '', price: 100, currency: 'PKR', category: 'shawls', images: [], stock, status,
  variants: [{ id: 'v1', color: 'Brown', size: 'Free', stock, price: 100 }],
}) as unknown as Product;

describe('assistant contract', () => {
  it('knows exactly the five backend actions', () => {
    expect([...ACTION_NAMES]).toEqual(['show_products', 'open_product', 'apply_filters', 'add_to_cart', 'start_whatsapp_order']);
  });

  it('only add_to_cart / start_whatsapp_order proposals can be confirmed', () => {
    expect(toProposal('add_to_cart', line, out())?.needsConfirmation).toBe(true);
    expect(toProposal('start_whatsapp_order', { items: [line] }, out())?.needsConfirmation).toBe(true);
    expect(toProposal('show_products', {}, out())?.needsConfirmation).toBe(false);
    expect(toProposal('add_to_cart', line, out({ outcome: 'rejected', requires_confirmation: false }))?.needsConfirmation).toBe(false);
    expect(toProposal('add_to_cart', line, out({ fingerprint: undefined }))?.needsConfirmation).toBe(false);
    expect(toProposal('delete_everything', {}, out())).toBeNull();
    expect(toProposal('add_to_cart', line, { outcome: 'x' })).toBeNull();
  });

  it('builds an explicit, action-bound, short-lived confirmation', () => {
    const p = toProposal('add_to_cart', line, out())!;
    const body = buildExecuteBody(p, 'sess_1', 1_000_000);
    expect(body).toMatchObject({ action_id: p.actionId, name: 'add_to_cart', session_id: 'sess_1', params: line });
    expect(body.confirmation).toMatchObject({ action_id: p.actionId, session_id: 'sess_1', fingerprint: 'fp', explicit: true });
    expect(body.confirmation.confirmed_at).toBeLessThan(1000);
    expect(body.confirmation.expires_at - body.confirmation.confirmed_at).toBeLessThanOrEqual(300);
  });
});

describe('applyAddToCart', () => {
  it('adds the exact line through the cart API', () => {
    const add = vi.fn();
    expect(applyAddToCart([line], [product()], add)).toBe('added');
    expect(add).toHaveBeenCalledWith(expect.objectContaining({ id: 'p1' }), expect.objectContaining({ id: 'v1' }), 2);
  });

  it.each([
    ['over stock (no silent clamp)', [product(1)]],
    ['out of stock', [product(0)]],
    ['unpublished', [product(3, 'draft')]],
    ['unknown product', []],
  ])('adds nothing when %s', (_n, catalogue) => {
    const add = vi.fn();
    expect(applyAddToCart([line], catalogue, add)).toBe('unavailable');
    expect(add).not.toHaveBeenCalled();
  });

  it('is all-or-nothing across lines', () => {
    const add = vi.fn();
    expect(applyAddToCart([line, { ...line, variant_id: 'nope' }], [product()], add)).toBe('unavailable');
    expect(add).not.toHaveBeenCalled();
  });
});

describe('applied-action-id set', () => {
  const store = () => {
    const m = new Map<string, string>();
    return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) };
  };
  it('is false until the action was applied here, then true', () => {
    const s = store();
    expect(wasApplied(s, 'act_1')).toBe(false); // server-claimed but client apply failed: replay must not show success
    markApplied(s, 'act_1');
    expect(wasApplied(s, 'act_1')).toBe(true);
    expect(wasApplied(s, 'act_2')).toBe(false);
  });
  it('survives corrupt or blocked storage without throwing', () => {
    expect(wasApplied({ getItem: () => '{bad' }, 'a')).toBe(false);
    expect(() => markApplied({ getItem: () => null, setItem: () => { throw new Error('blocked'); } }, 'a')).not.toThrow();
  });
});
