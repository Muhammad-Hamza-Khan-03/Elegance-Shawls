import test from 'node:test';
import assert from 'node:assert/strict';
import { createSender, SendError } from './sender.mjs';
import { createPairing, PAIRING_TTL_MS } from './pairing.mjs';

const CHAT = '92300@s.whatsapp.net';
function harness(over = {}) {
  let t = 1_000_000;
  const calls = [];
  const sock = {
    sendPresenceUpdate: async (...a) => calls.push(['presence', ...a]),
    sendMessage: async (chat, content, opts) => calls.push(['send', chat, content.text, opts.messageId]),
    readMessages: async (keys) => calls.push(['read', keys[0].id]),
  };
  const sender = createSender({ getSock: () => sock, now: () => t, sleep: async () => {}, rand: () => 0.5, ...over });
  return { sender, calls, advance: (ms) => { t += ms; } };
}
const req = (key = 'k1', chat = CHAT) => ({ chat, text: 'hello', idempotency_key: key });
const rejects = (p, status) => assert.rejects(Promise.resolve().then(() => p()), (e) => e instanceof SendError && e.status === status);

test('refuses a chat that never wrote, or wrote more than 24h ago: the bot cannot start conversations', async () => {
  const { sender, calls, advance } = harness();
  await rejects(() => sender.send(req()), 403);
  sender.noteInbound(CHAT, { id: 'in1' });
  advance(24 * 60 * 60 * 1000 + 1);
  await rejects(() => sender.send(req('k2')), 403);
  assert.equal(calls.length, 0);
});

test('sends with typing, marks only that chat read, and a repeated key never sends twice', async () => {
  const { sender, calls } = harness();
  sender.noteInbound(CHAT, { id: 'in1' });
  const a = await sender.send(req());
  const b = await sender.send(req());
  assert.deepEqual(a, b);
  assert.equal(calls.filter((c) => c[0] === 'send').length, 1);
  assert.deepEqual(calls.map((c) => c[0]), ['presence', 'send', 'presence', 'read']);
  assert.ok(sender.isBotId(a.wa_id) && calls.find((c) => c[0] === 'send')[3] === a.wa_id);
});

test('global per-minute cap, then recovers', async () => {
  const { sender, advance } = harness({ ratePerMin: 2 });
  sender.noteInbound(CHAT, { id: 'in1' });
  await sender.send(req('a')); await sender.send(req('b'));
  await rejects(() => sender.send(req('c')), 429);
  advance(61_000);
  await sender.send(req('c'));
});

test('validates input and a failed send can be retried with the same key', async () => {
  let fail = true;
  const { sender } = harness({ getSock: () => ({ sendPresenceUpdate: async () => {}, readMessages: async () => {},
    sendMessage: async () => { if (fail) throw new Error('boom'); } }) });
  sender.noteInbound(CHAT, { id: 'in1' });
  await rejects(() => sender.send({ chat: 'x', text: 'a', idempotency_key: 'k' }), 400);
  await rejects(() => sender.send({ chat: '1-2@g.us', text: 'a', idempotency_key: 'k' }), 400);
  await rejects(() => sender.send(req('r')), 502);
  fail = false;
  assert.ok((await sender.send(req('r'))).wa_id);
});

test('not connected is a 503', async () => {
  const { sender } = harness({ getSock: () => null });
  sender.noteInbound(CHAT, { id: 'in1' });
  await rejects(() => sender.send(req()), 503);
});

test('pairing: one session, expires after 2 minutes, QR only while active', () => {
  let t = 0;
  const p = createPairing(() => t);
  assert.equal(p.view(), null);
  const first = p.start(); p.setQr('qr1');
  assert.equal(p.start(), first);
  assert.equal(p.view().qr, 'qr1');
  t = PAIRING_TTL_MS;
  assert.equal(p.view(), null);
  p.setQr('late');
  assert.equal(p.view(), null);
});
