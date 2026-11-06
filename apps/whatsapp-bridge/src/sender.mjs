// Outbound safety, independent of the backend: the bot can only answer a chat whose customer wrote in the last 24 hours,
// a retried idempotency key never sends twice, and a global per-minute cap stops loops. No Baileys import: testable with a stub.
import crypto from 'node:crypto';

const DAY = 24 * 60 * 60 * 1000;
export class SendError extends Error {
  constructor(status, code) { super(code); this.status = status; this.code = code; }
}

export function createSender({ getSock, ratePerMin = 20, now = Date.now, sleep = (ms) => new Promise((r) => setTimeout(r, ms)), rand = Math.random }) {
  const lastInbound = new Map(); // chat -> { at, key }; in memory, so after a restart a chat must write again before we can answer it
  const results = new Map();     // idempotency key -> Promise<{ wa_id }>
  const botIds = new Set();      // ids we sent, so their echo is not mistaken for staff typing on the phone
  const stamps = [];

  const noteInbound = (chat, key, atMs = now()) => lastInbound.set(chat, { at: atMs, key });
  const isBotId = (id) => botIds.has(id);

  async function deliver({ chat, text }) {
    const sock = getSock();
    if (!sock) throw new SendError(503, 'not_connected');
    const waId = '3EB0' + crypto.randomBytes(10).toString('hex').toUpperCase();
    botIds.add(waId);
    try {
      await sock.sendPresenceUpdate('composing', chat);
      await sleep(1000 + Math.floor(rand() * 2000));
      await sock.sendMessage(chat, { text }, { messageId: waId });
      await sock.sendPresenceUpdate('paused', chat);
      const key = lastInbound.get(chat)?.key;
      if (key) await sock.readMessages([key]); // only chats the bot answered are marked read
    } catch (err) {
      botIds.delete(waId);
      throw new SendError(502, `send_failed: ${err.message}`);
    }
    return { wa_id: waId };
  }

  function send({ chat, text, idempotency_key: key }) {
    if (typeof key !== 'string' || !key || typeof text !== 'string' || !text.trim() || text.length > 4096) throw new SendError(400, 'invalid_request');
    if (typeof chat !== 'string' || !/@(s\.whatsapp\.net|lid)$/.test(chat)) throw new SendError(400, 'invalid_chat');
    if (results.has(key)) return results.get(key);
    const seen = lastInbound.get(chat);
    if (!seen || now() - seen.at > DAY) throw new SendError(403, 'no_customer_message_in_24h');
    while (stamps.length && now() - stamps[0] > 60_000) stamps.shift();
    if (stamps.length >= ratePerMin) throw new SendError(429, 'rate_limited');
    stamps.push(now());
    const pending = deliver({ chat, text });
    results.set(key, pending);
    pending.catch(() => results.delete(key)); // a failed send may be retried with the same key
    return pending;
  }

  return { send, noteInbound, isBotId };
}
