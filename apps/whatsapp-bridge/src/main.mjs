// WhatsApp bridge: speaks WhatsApp (Baileys) and publishes events to Redis. No business logic, no SQL.
// Phase 1-2 scope: receive-only. /send and automated replies arrive in Phase 3.
import http from 'node:http';
import crypto from 'node:crypto';
import pino from 'pino';
import { loadConfig } from './config.mjs';
import { toEvent, isValidEvent } from './events.mjs';
import { backoffMs } from './backoff.mjs';

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

const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion } = await import('@whiskeysockets/baileys');
const { default: Redis } = await import('ioredis');
const redis = new Redis(config.redisUrl, { maxRetriesPerRequest: null });
const state = { state: 'connecting', lastEventAt: null, attempt: 0, number: null };
const pairOnly = process.argv[2] === 'pair';

const tokenOk = (header = '') => {
  const given = Buffer.from(header.replace(/^Bearer /, ''));
  const wanted = Buffer.from(config.token);
  return given.length === wanted.length && crypto.timingSafeEqual(given, wanted);
};

// Internal only: never published, never behind the proxy. Token on every call.
http.createServer((req, res) => {
  if (!tokenOk(req.headers.authorization)) { res.writeHead(401).end(); return; }
  if (req.method === 'GET' && req.url === '/health') {
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ state: state.state, last_event_at: state.lastEventAt, number: state.number, baileys: '7.0.0-rc13' }));
    return;
  }
  res.writeHead(404).end();
}).listen(config.port, '0.0.0.0');

async function publish(event) {
  if (!isValidEvent(event)) { log.warn({ id: event?.wa_id }, 'dropping invalid event'); return; }
  for (;;) { // noeviction Redis rejects writes when full: retry rather than lose the message
    try {
      await redis.xadd('wa:inbound', 'MAXLEN', '~', 10000, '*', 'event', JSON.stringify(event));
      state.lastEventAt = event.ts;
      return;
    } catch (err) {
      log.error({ err: err.message }, 'XADD failed; retrying');
      await new Promise((r) => setTimeout(r, 2000));
    }
  }
}

async function connect() {
  const { state: auth, saveCreds } = await useMultiFileAuthState(config.sessionDir);
  const { version } = await fetchLatestBaileysVersion();
  const sock = makeWASocket({
    version, auth, logger: log.child({ c: 'baileys' }, { level: 'warn' }),
    printQRInTerminal: false, markOnlineOnConnect: false, syncFullHistory: false,
  });
  sock.ev.on('creds.update', saveCreds);
  sock.ev.on('connection.update', ({ connection, lastDisconnect, qr }) => {
    if (qr) {
      // Pairing is a terminal fallback in this phase; the QR is a login credential and is never written to the log.
      process.stdout.write(`\nScan with WhatsApp > Linked devices:\n${qr}\n`);
    }
    if (connection === 'open') {
      state.state = 'connected'; state.attempt = 0; state.number = sock.user?.id?.split(':')[0] ?? null;
      log.info('connected');
      if (pairOnly) { log.info('paired; exiting'); process.exit(0); }
    }
    if (connection === 'close') {
      const code = lastDisconnect?.error?.output?.statusCode;
      if (code === DisconnectReason.loggedOut) { state.state = 'needs_pairing'; log.error('logged out; run the pair command'); return; }
      state.state = 'connecting';
      const wait = backoffMs(state.attempt++);
      log.warn({ code, wait }, 'disconnected; reconnecting');
      setTimeout(() => connect().catch((e) => log.error(e)), wait);
    }
  });
  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    if (type !== 'notify') return; // history and appends are not new chat activity
    for (const msg of messages) await publish(toEvent(msg));
  });
}

connect().catch((err) => { log.error(err); process.exit(1); });
process.on('SIGTERM', () => process.exit(0));
