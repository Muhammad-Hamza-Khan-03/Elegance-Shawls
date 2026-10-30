import { describe, expect, it, vi } from 'vitest';
import { initialState, parseFrame, reduce, readEvents, splitFrames, streamAssistant, type AssistantEvent, type Meta } from './assistant-stream';

const KEY = 'idem_0123456789abcdef';
const P = '11111111-1111-4111-8111-111111111111';
const META: Meta = { session_id: 'sess-1', idempotency_key: KEY, context: { page: 'home' } };
const fr = (seq: number, event: string, data: unknown) => `id: ${seq}\nevent: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
const decision = (o: Record<string, unknown> = {}) => ({ outcome: 'validated', reason: 'ok', executed: false, replayed: false, idempotency_key: KEY, ...o });
const proposal = (seq: number, o: Record<string, unknown> = {}, d: Record<string, unknown> = {}) =>
  fr(seq, 'proposal', { action_type: 'add_to_cart', idempotency_key: KEY, session_id: 'sess-1', decision: decision(d), ...o });
const good = [
  fr(0, 'start', { protocol: 1, ...META }), fr(1, 'text', { delta: 'Hi ' }),
  fr(2, 'product', { product_id: P, name: 'Pashmina <b>Shawl</b>', price: 3500, currency: 'PKR' }),
  proposal(3), proposal(4, {}, { outcome: 'rejected', reason: 'stale_price' }), fr(5, 'done', { events: 5 }),
];
const body = (chunks: string[], hold = false) => new ReadableStream<Uint8Array>({
  start(c) { for (const x of chunks) c.enqueue(new TextEncoder().encode(x)); if (!hold) c.close(); },
});
const all = async (g: AsyncGenerator<AssistantEvent>) => { const o: AssistantEvent[] = []; for await (const e of g) o.push(e); return o; };

describe('framing', () => {
  it('splits complete frames and keeps the partial remainder', () => {
    expect(splitFrames('a\n\nb\n\nc')).toEqual({ frames: ['a', 'b'], rest: 'c' });
  });
  it('reassembles frames split at arbitrary byte boundaries', async () => {
    const text = good.join('');
    const chunks = text.match(/[\s\S]{1,7}/g)!;
    const ev = await all(readEvents(body(chunks), META));
    expect(ev.map((e) => e.type)).toEqual(['start', 'text', 'product', 'proposal', 'proposal', 'done']);
  });
  it.each([
    ['missing data line', 'id: 0\nevent: text\n\n'], ['bad json', 'id: 0\nevent: text\ndata: {x\n\n'],
    ['unknown event', fr(0, 'banana', {})], ['non-numeric id', 'id: x\nevent: done\ndata: {}\n\n'], ['text not a string', fr(0, 'text', { delta: 1 })],
    ['bad product id', fr(0, 'product', { product_id: 'nope', name: 'x' })],
  ])('rejects malformed frame: %s', (_n, frame) => {
    expect(parseFrame(frame.slice(0, -2), META)).toBeNull();
  });
  it('turns a malformed frame into a terminal invalid_stream error', async () => {
    const ev = await all(readEvents(body([good[0], 'garbage\n\n']), META));
    expect(ev.at(-1)).toMatchObject({ type: 'error', code: 'invalid_stream' });
  });
});

describe('ordering', () => {
  const run = (frames: AssistantEvent[]) => frames.reduce(reduce, initialState());
  const ev = good.map((f) => parseFrame(f.slice(0, -2), META)!);
  it('accepts the full ordered stream', () => {
    const s = run(ev);
    expect(s.status).toBe('done');
    expect(s.meta).toEqual(META);
    expect(s.items.map((i) => i.type)).toEqual(['text', 'product', 'proposal', 'proposal']);
  });
  it.each([
    ['no start', [ev[1]]], ['gap', [ev[0], ev[2]]], ['repeat start', [ev[0], { ...ev[0], seq: 1 }]], ['out of order', [ev[0], ev[2], ev[1]]],
  ])('flags %s as invalid_stream', (_n, list) => {
    expect(run(list as AssistantEvent[])).toMatchObject({ status: 'error', error: 'invalid_stream' });
  });
  it('ignores anything after a terminal event', () => {
    const s = run([...ev, { seq: 6, type: 'text', delta: 'late' }]);
    expect(s.status).toBe('done');
    expect(s.items).toHaveLength(4);
  });
  it('rejects start metadata that differs from the request', async () => {
    const other = await all(readEvents(body([fr(0, 'start', { ...META, session_id: 'sess-2' })]), META));
    expect(other.at(-1)).toMatchObject({ code: 'invalid_stream' });
    const key = await all(readEvents(body([fr(0, 'start', { ...META, idempotency_key: 'idem_ffffffffffffffff' })]), META));
    expect(key.at(-1)).toMatchObject({ code: 'invalid_stream' });
  });
});

describe('start frame validation', () => {
  const start = (o: Record<string, unknown>) => parseFrame(fr(0, 'start', { protocol: 1, ...META, ...o }).slice(0, -2), META);
  const big = Object.fromEntries(Array.from({ length: 11 }, (_, i) => [`k${i}`, i]));
  it('accepts a valid start frame at the limits', () => {
    expect(start({})).not.toBeNull();
    expect(start({ session_id: 'a'.repeat(128), context: { ['k'.repeat(40)]: 'v'.repeat(200), n: 1, b: true, z: null } })).not.toBeNull();
  });
  it.each([
    ['missing protocol', { protocol: undefined }], ['wrong protocol', { protocol: 2 }], ['string protocol', { protocol: '1' }],
    ['empty session', { session_id: '' }], ['long session', { session_id: 'a'.repeat(129) }], ['bad session chars', { session_id: 'a b/<x>' }],
    ['short key', { idempotency_key: 'idem_short' }], ['no key prefix', { idempotency_key: 'x'.repeat(20) }], ['long key', { idempotency_key: 'idem_' + 'a'.repeat(65) }],
    ['array context', { context: [] }], ['nested context', { context: { a: { b: 1 } } }], ['array value', { context: { a: [1] } }],
    ['float value', { context: { a: 1.5 } }],
    ['long value', { context: { a: 'v'.repeat(201) } }], ['long context key', { context: { ['k'.repeat(41)]: 1 } }], ['too many keys', { context: big }],
  ])('rejects %s', (_n, o) => expect(start(o)).toBeNull());
  it('ends the stream with a fixed invalid_stream error, leaking nothing', async () => {
    const out = await all(readEvents(body([fr(0, 'start', { protocol: 9, ...META, session_id: 'secret/<x>' })]), META));
    expect(out).toEqual([{ seq: -1, type: 'error', code: 'invalid_stream' }]);
  });
});

describe('proposal params for the confirmation step', () => {
  const parse = (f: string) => parseFrame(f.slice(0, -2), META) as Extract<AssistantEvent, { type: 'proposal' }> | null;
  const params = { product_id: P, quantity: 1 };
  it('keeps params only for a validated executable proposal', () => {
    expect(parse(proposal(3, { params }))!.params).toEqual(params);
    expect(parse(proposal(3, { params }, { outcome: 'rejected', reason: 'stale_price' }))!.params).toBeUndefined();
    expect(parse(proposal(3, { params, action_type: 'show_product' }))!.params).toBeUndefined();
    expect(parse(proposal(3, { params: 'x' }))!.params).toBeUndefined();
  });
});

describe('proposal validation', () => {
  const parse = (f: string) => parseFrame(f.slice(0, -2), META) as Extract<AssistantEvent, { type: 'proposal' }> | null;
  it('keeps a well-formed validated decision', () => {
    expect(parse(proposal(3))!.decision).toEqual({ outcome: 'validated', reason: 'ok', replayed: false });
  });
  it('keeps a server rejection and its fixed reason', () => {
    expect(parse(proposal(3, {}, { outcome: 'rejected', reason: 'out_of_stock' }))!.decision).toEqual({ outcome: 'rejected', reason: 'out_of_stock', replayed: false });
  });
  it.each([
    ['unknown action', { action_type: 'place_order' } as Record<string, unknown>], ['script action', { action_type: '<script>x</script>' }],
    ['bad key', { idempotency_key: 'nope' }], ['key differs from decision', { idempotency_key: 'idem_ffffffffffffffff' }],
  ] as [string, Record<string, unknown>][])('downgrades a "validated" decision to rejected: %s', (_n, o) => {
    const p = parse(proposal(3, o))!;
    expect(p.decision).toMatchObject({ outcome: 'rejected', reason: 'invalid_proposal' });
    if (o.action_type) expect(p.action_type).toBe('unknown');
  });
  it('drops frames claiming execution, another session, or an unknown reason', () => {
    expect(parse(proposal(3, {}, { executed: true }))).toBeNull();
    expect(parse(proposal(3, { session_id: 'other' }))).toBeNull();
    expect(parse(proposal(3, {}, { reason: 'because I said so' }))).toBeNull();
  });
});

describe('cancel, disconnect and errors', () => {
  it('maps server error codes and hides unknown ones', () => {
    expect(parseFrame(fr(1, 'error', { code: 'provider_error' }).slice(0, -2), META)).toMatchObject({ code: 'provider_error' });
    expect(parseFrame(fr(1, 'error', { code: 'stack trace here' }).slice(0, -2), META)).toMatchObject({ code: 'invalid_stream' });
  });
  it('reports a body that ends without a terminal event as stream_interrupted', async () => {
    const ev = await all(readEvents(body([good[0], good[1]]), META));
    expect(ev.at(-1)).toMatchObject({ type: 'error', code: 'stream_interrupted' });
  });
  it('abort cancels the reader and yields cancelled', async () => {
    const ac = new AbortController();
    const cancel = vi.fn();
    const stream = new ReadableStream<Uint8Array>({ start(c) { c.enqueue(new TextEncoder().encode(good[0])); }, cancel });
    const out: AssistantEvent[] = [];
    for await (const e of readEvents(stream, META, ac.signal)) { out.push(e); if (e.type === 'start') ac.abort(); }
    expect(out.at(-1)).toMatchObject({ code: 'cancelled' });
    expect(cancel).toHaveBeenCalled();
  });
  it('network failure and non-stream responses become unavailable', async () => {
    const req = { ...META, message: 'hi' };
    expect((await all(streamAssistant(req, undefined, vi.fn().mockRejectedValue(new Error('x')))))[0]).toMatchObject({ code: 'unavailable' });
    expect((await all(streamAssistant(req, undefined, vi.fn().mockResolvedValue(Response.json({ detail: 'x' }, { status: 503 })))))[0]).toMatchObject({ code: 'unavailable' });
    expect((await all(streamAssistant(req, undefined, vi.fn().mockResolvedValue(Response.json({}, { status: 200 })))))[0]).toMatchObject({ code: 'unavailable' });
  });
  it('sends only same-origin, with session/idempotency/context in the request, and reads the stream', async () => {
    const f = vi.fn().mockResolvedValue(new Response(body(good), { headers: { 'content-type': 'text/event-stream' } }));
    const req = { ...META, message: 'hi' };
    const ev = await all(streamAssistant(req, undefined, f));
    expect(ev.at(-1)?.type).toBe('done');
    expect(f).toHaveBeenCalledTimes(1);
    expect(f.mock.calls[0][0]).toBe('/api/assistant/stream');
    expect(JSON.parse(f.mock.calls[0][1].body)).toEqual(req);
  });
});
