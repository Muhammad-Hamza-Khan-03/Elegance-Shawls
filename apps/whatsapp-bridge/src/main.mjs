// WhatsApp bridge: speaks WhatsApp (Baileys) and publishes events to Redis; delivers replies the backend asks for.
// No business logic, no SQL. Internal only: never published on a port, never behind the proxy, token on every call.
import http from 'node:http';
import crypto from 'node:crypto';
import pino from 'pino';
import { loadConfig } from './config.mjs';
import { toEvent, isValidEvent } from './events.mjs';
import { backoffMs } from './backoff.mjs';
import { createSender, SendError } from './sender.mjs';
import { createPairing } from './pairing.mjs';
import { createCipher, fileStore, postgresStore } from './auth-store.mjs';
import { createMediaStore } from './media.mjs';

const log = pino({ level: process.env.LOG_LEVEL ?? 'info' });
const config = loadConfig();

if (!config.enabled) {
  log.info('WHATSAPP_BRIDGE_ENABLED is false; bridge not started');
  process.exit(0);
}
if (config.problems.length) {
  log.error({ problems: config.problems }, 'WhatsApp bridge cannot start');
  process.exit(1);
}

const baileys = await import('@whiskeysockets/baileys');
const { default: makeWASocket, DisconnectReason, fetchLatestBaileysVersion, downloadMediaMessage } = baileys;
const { default: Redis } = await import('ioredis');
const redis = new Redis(config.redisUrl, { maxRetriesPerRequest: null });
const status = { state: 'needs_pairing', lastEventAt: null, attempt: 0, number: null, since: new Date().toISOString() };
const media = createMediaStore();
const images = createMediaStore({ maxBytes: 5 * 1024 * 1024, maxItems: 10 }); // customer photos: memory only, minutes, never disk or Redis
let store = null; // the auth store: file volume or encrypted PostgreSQL
const pairing = createPairing();
const pairOnly = process.argv[2] === 'pair';
let sock = null;
let generation = 0; // handlers of a replaced socket are ignored
const sender = createSender({ getSock: () => (status.state === 'connected' ? sock : null), ratePerMin: config.sendRatePerMin });

const isPaired = () => (store ? store.isPaired() : false);
const wipeSession = async () => { await store?.wipe(); store = null; }; // reopened on the next connect, so stale keys are never reused
const setState = (next) => { if (status.state !== next) { status.state = next; status.since = new Date().toISOString(); } };
async function openStore() {
  if (config.authStore === 'postgres') {
    const { default: pg } = await import('pg');
    const pool = new pg.Pool({ connectionString: config.authDatabaseUrl, max: 3 });
    return postgresStore({ db: pool, cipher: createCipher(config.authKey), baileys });
  }
  return fileStore({ dir: config.sessionDir, baileys });
}
const stopSocket = () => { generation++; try { sock?.end(undefined); } catch { /* already closed */ } sock = null; };

async function publish(event) {
  if (!isValidEvent(event)) { log.warn({ id: event?.wa_id }, 'dropping invalid event'); return; }
  for (;;) { // noeviction Redis rejects writes when full: retry rather than lose the message
    try {
      await redis.xadd('wa:inbound', 'MAXLEN', '~', 10000, '*', 'event', JSON.stringify(event));
      status.lastEventAt = event.ts;
      return;
    } catch (err) {
      log.error({ err: err.message }, 'XADD failed; retrying');
      await new Promise((r) => setTimeout(r, 2000));
    }
  }
}

async function connect() {
  const mine = ++generation;
  store ??= await openStore();
  const { state: auth, saveCreds } = store;
  const { version } = await fetchLatestBaileysVersion();
  sock = makeWASocket({ version, auth, logger: log.child({ c: 'baileys' }, { level: 'warn' }), markOnlineOnConnect: false, syncFullHistory: false });
  const current = sock;
  current.ev.on('creds.update', saveCreds);
  current.ev.on('connection.update', async ({ connection, lastDisconnect, qr }) => {
    if (mine !== generation) return;
    if (qr) {
      pairing.setQr(qr);
      if (pairOnly) process.stdout.write(`\nScan with WhatsApp > Linked devices:\n${qr}\n`); // terminal fallback only
    }
    if (connection === 'open') {
      setState('connected'); status.attempt = 0; status.number = current.user?.id?.split(':')[0] ?? null;
      pairing.end();
      log.info('connected');
      if (pairOnly) { log.info('paired; exiting'); process.exit(0); }
    }
    if (connection === 'close') {
      const code = lastDisconnect?.error?.output?.statusCode;
      status.number = null;
      if (code === DisconnectReason.loggedOut) { setState('needs_pairing'); await wipeSession(); stopSocket(); log.error('logged out; pair again'); return; }
      if (!isPaired() && !pairing.active()) { setState('needs_pairing'); stopSocket(); return; }
      setState(pairing.active() ? 'pairing' : 'connecting');
      const wait = backoffMs(status.attempt++);
      log.warn({ code, wait }, 'disconnected; reconnecting');
      setTimeout(() => { if (mine === generation) connect().catch((e) => log.error(e)); }, wait);
    }
  });
  current.ev.on('messages.upsert', async ({ messages, type }) => {
    if (mine !== generation || type !== 'notify') return; // history and appends are not new chat activity
    for (const msg of messages) {
      const event = toEvent(msg);
      if (!event) continue;
      if (!event.from_me) sender.noteInbound(event.chat, msg.key, Date.parse(event.ts));
      if (config.imageEnabled && event.type === 'image' && !event.from_me) {
        try {
          const photo = await downloadMediaMessage(msg, 'buffer', {});
          if (images.put(event.wa_id, photo, msg.message.imageMessage?.mimetype ?? 'image/jpeg')) event.media = `image:${event.wa_id}`;
        } catch (err) { log.warn({ err: err.message }, 'image download failed'); }
      }
      if (config.voiceEnabled && event.type === 'audio' && !event.from_me) {
        try {
          const audio = await downloadMediaMessage(msg, 'buffer', {});
          if (media.put(event.wa_id, audio, msg.message.audioMessage?.mimetype ?? 'audio/ogg')) event.media = `voice:${event.wa_id}`;
        } catch (err) { log.warn({ err: err.message }, 'voice download failed'); }
      }
      else if (sender.isBotId(event.wa_id)) event.via_bot = true;
      await publish(event);
    }
  });
}

function startPairing() {
  if (status.state === 'connected') throw new SendError(409, 'already_connected');
  const fresh = !pairing.active();
  pairing.start();
  if (fresh) {
    stopSocket();
    setState('pairing');
    status.attempt = 0;
    connect().catch((e) => log.error(e));
    setTimeout(() => {
      if (status.state === 'pairing' && !pairing.active()) { stopSocket(); setState(isPaired() ? 'connecting' : 'needs_pairing'); }
    }, 2 * 60 * 1000 + 500);
  }
}

const tokenOk = (header = '') => {
  const given = Buffer.from(header.replace(/^Bearer /, ''));
  const wanted = Buffer.from(config.token);
  return given.length === wanted.length && crypto.timingSafeEqual(given, wanted);
};
const readJson = (req) => new Promise((resolve, reject) => {
  let body = '';
  req.on('data', (c) => { body += c; if (body.length > 20_000) reject(new SendError(413, 'too_large')); });
  req.on('end', () => { try { resolve(body ? JSON.parse(body) : {}); } catch { reject(new SendError(400, 'invalid_json')); } });
});

http.createServer(async (req, res) => {
  const reply = (code, body) => { res.writeHead(code, { 'content-type': 'application/json' }); res.end(JSON.stringify(body)); };
  if (!tokenOk(req.headers.authorization)) { res.writeHead(401).end(); return; }
  try {
    const route = `${req.method} ${req.url}`;
    if (route === 'GET /health') return reply(200, { state: status.state, state_since: status.since, last_event_at: status.lastEventAt, number: status.number, baileys: '7.0.0-rc13', auth_store: config.authStore });
    if (route === 'GET /pairing/status') return reply(200, { state: status.state, number: status.number, pairing: pairing.view() });
    if (route === 'POST /pairing/start') { startPairing(); return reply(200, { state: status.state, pairing: pairing.view() }); }
    if (route === 'POST /pairing/code') {
      const { phone } = await readJson(req);
      if (!pairing.active() || !pairing.view().qr || !sock) throw new SendError(409, 'pairing_not_ready');
      if (!/^[0-9]{8,15}$/.test(String(phone))) throw new SendError(400, 'invalid_phone');
      pairing.setCode(await sock.requestPairingCode(String(phone)));
      return reply(200, { state: status.state, pairing: pairing.view() });
    }
    if (route === 'POST /pairing/disconnect') {
      const old = sock;
      pairing.end(); stopSocket();
      try { await old?.logout(); } catch { /* already unlinked on the phone */ }
      wipeSession(); setState('needs_pairing'); status.number = null;
      return reply(200, { state: status.state });
    }
    const voice = req.url?.match(/^\/media\/([A-Za-z0-9_-]{1,128})$/);
    if (voice && req.method === 'GET') {
      const item = media.get(voice[1]) ?? images.get(voice[1]);
      if (!item) return reply(404, { error: 'not_found' });
      res.writeHead(200, { 'content-type': item.mimetype }); return res.end(item.buffer);
    }
    if (voice && req.method === 'DELETE') { media.delete(voice[1]); images.delete(voice[1]); return reply(200, { deleted: true }); }
    if (route === 'POST /send') return reply(200, await sender.send(await readJson(req)));
    res.writeHead(404).end();
  } catch (err) {
    if (err instanceof SendError) return reply(err.status, { error: err.code });
    log.error({ err: err.message }, 'request failed');
    reply(500, { error: 'internal' });
  }
}).listen(config.port, '0.0.0.0');

store = await openStore();
if (isPaired()) connect().catch((err) => { log.error(err); process.exit(1); });
else if (pairOnly) startPairing();
else log.warn('no linked device; pair from Admin > WhatsApp or run the pair command');
process.on('SIGTERM', () => process.exit(0));
