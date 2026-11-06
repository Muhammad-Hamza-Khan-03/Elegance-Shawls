// WhatsApp bridge: speaks WhatsApp (Baileys) and publishes events to Redis; delivers replies the backend asks for.
// No business logic, no SQL. Internal only: never published on a port, never behind the proxy, token on every call.
import http from 'node:http';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import pino from 'pino';
import { loadConfig } from './config.mjs';
import { toEvent, isValidEvent } from './events.mjs';
import { backoffMs } from './backoff.mjs';
import { createSender, SendError } from './sender.mjs';
import { createPairing } from './pairing.mjs';

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
const status = { state: 'needs_pairing', lastEventAt: null, attempt: 0, number: null };
const pairing = createPairing();
const pairOnly = process.argv[2] === 'pair';
let sock = null;
let generation = 0; // handlers of a replaced socket are ignored
const sender = createSender({ getSock: () => (status.state === 'connected' ? sock : null), ratePerMin: config.sendRatePerMin });

const isPaired = () => {
  try { return Boolean(JSON.parse(fs.readFileSync(path.join(config.sessionDir, 'creds.json'), 'utf8')).me); } catch { return false; }
};
const wipeSession = () => fs.rmSync(config.sessionDir, { recursive: true, force: true });
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
  const { state: auth, saveCreds } = await useMultiFileAuthState(config.sessionDir);
  fs.chmodSync(config.sessionDir, 0o700);
  const { version } = await fetchLatestBaileysVersion();
  sock = makeWASocket({ version, auth, logger: log.child({ c: 'baileys' }, { level: 'warn' }), markOnlineOnConnect: false, syncFullHistory: false });
  const current = sock;
  current.ev.on('creds.update', saveCreds);
  current.ev.on('connection.update', ({ connection, lastDisconnect, qr }) => {
    if (mine !== generation) return;
    if (qr) {
      pairing.setQr(qr);
      if (pairOnly) process.stdout.write(`\nScan with WhatsApp > Linked devices:\n${qr}\n`); // terminal fallback only
    }
    if (connection === 'open') {
      status.state = 'connected'; status.attempt = 0; status.number = current.user?.id?.split(':')[0] ?? null;
      pairing.end();
      log.info('connected');
      if (pairOnly) { log.info('paired; exiting'); process.exit(0); }
    }
    if (connection === 'close') {
      const code = lastDisconnect?.error?.output?.statusCode;
      status.number = null;
      if (code === DisconnectReason.loggedOut) { status.state = 'needs_pairing'; wipeSession(); stopSocket(); log.error('logged out; pair again'); return; }
      if (!isPaired() && !pairing.active()) { status.state = 'needs_pairing'; stopSocket(); return; }
      status.state = pairing.active() ? 'pairing' : 'connecting';
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
    status.state = 'pairing';
    status.attempt = 0;
    connect().catch((e) => log.error(e));
    setTimeout(() => {
      if (status.state === 'pairing' && !pairing.active()) { stopSocket(); status.state = isPaired() ? 'connecting' : 'needs_pairing'; }
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
    if (route === 'GET /health') return reply(200, { state: status.state, last_event_at: status.lastEventAt, number: status.number, baileys: '7.0.0-rc13' });
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
      wipeSession(); status.state = 'needs_pairing'; status.number = null;
      return reply(200, { state: status.state });
    }
    if (route === 'POST /send') return reply(200, await sender.send(await readJson(req)));
    res.writeHead(404).end();
  } catch (err) {
    if (err instanceof SendError) return reply(err.status, { error: err.code });
    log.error({ err: err.message }, 'request failed');
    reply(500, { error: 'internal' });
  }
}).listen(config.port, '0.0.0.0');

if (isPaired()) connect().catch((err) => { log.error(err); process.exit(1); });
else if (pairOnly) startPairing();
else log.warn('no linked device; pair from Admin > WhatsApp or run the pair command');
process.on('SIGTERM', () => process.exit(0));
