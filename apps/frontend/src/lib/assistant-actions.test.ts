import { describe, expect, it, vi } from 'vitest';
import { confirmAction, resolveLines, type ExecItem } from './assistant-actions';
import type { Product } from '@/types/types';

const P = '11111111-1111-4111-8111-111111111111';
const V = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const KEY = 'idem_0123456789abcdef';
const params = { product_id: P, variant_id: V, quantity: 1, expected_revision: 7, expected_unit_price: 3500, currency: 'PKR' };
const req = { session_id: 'sess_1', idempotency_key: KEY, action_type: 'add_to_cart', params };
const items: ExecItem[] = [{ product_id: P, variant_id: V, quantity: 1, slug: 'pashmina' }];
const reply = (status: number, body: unknown) => vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })) as unknown as typeof fetch;

describe('confirmAction', () => {
  it('posts an explicit confirmation and returns the verified items', async () => {
    const f = reply(200, { status: 'executed', replayed: false, result: { items } });
    expect(await confirmAction(req, f)).toEqual({ ok: true, replayed: false, items, reference: null });
    const [url, init] = (f as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe('/api/assistant/actions/execute');
    expect(JSON.parse(init.body)).toEqual({ ...req, confirmed: true });
  });
  it('returns the enquiry reference', async () => {
    const r = await confirmAction({ ...req, action_type: 'start_whatsapp_enquiry' }, reply(200, { status: 'executed', replayed: true, result: { items, reference: 'ES-ABC234' } }));
    expect(r).toMatchObject({ ok: true, replayed: true, reference: 'ES-ABC234' });
  });
  it('turns a server rejection into a fixed friendly message, never the server text', async () => {
    const r = await confirmAction(req, reply(409, { detail: { status: 'rejected', reason: 'stale_price', secret: 'x' } }));
    expect(r).toEqual({ ok: false, reason: 'stale_price', message: expect.stringContaining('price changed') });
    expect(JSON.stringify(r)).not.toContain('secret');
  });
  it.each([
    ['network failure', vi.fn(async () => { throw new Error('boom'); }) as unknown as typeof fetch],
    ['server error', reply(503, { detail: 'down' })],
    ['malformed success', reply(200, { status: 'executed', result: { items: [{ product_id: 5 }] } })],
    ['enquiry without reference', reply(200, { status: 'executed', replayed: false, result: { items } })],
  ])('fails closed on %s', async (_n, f) => {
    const r = await confirmAction({ ...req, action_type: 'start_whatsapp_enquiry' }, f);
    expect(r.ok).toBe(false);
  });
});

const variant = (o = {}) => ({ id: V, color: 'Ivory', size: 'Free Size', stock: 5, price: 3500, ...o });
const product = (o: Partial<Product> = {}) => ({ id: P, slug: 'pashmina', name: 'Pashmina', currency: 'PKR', status: 'active', variants: [variant()], ...o }) as unknown as Product;
const load = (p: Product | null) => async () => new Map([['pashmina', p]]);

describe('resolveLines', () => {
  it('pairs each verified item with the current published product and variant', async () => {
    const lines = await resolveLines(items, [3500], load(product()));
    expect(lines?.[0]).toMatchObject({ quantity: 1, product: { id: P }, variant: { id: V } });
  });
  it.each([
    ['unpublished', null], ['other product id', product({ id: 'x' })],
    ['missing variant', product({ variants: [] } as Partial<Product>)],
    ['price drift', product({ variants: [variant({ price: 3600 })] } as Partial<Product>)],
    ['low stock', product({ variants: [variant({ stock: 0 })] } as Partial<Product>)],
  ])('returns null when %s', async (_n, p) => {
    expect(await resolveLines(items, [3500], load(p))).toBeNull();
  });
});
