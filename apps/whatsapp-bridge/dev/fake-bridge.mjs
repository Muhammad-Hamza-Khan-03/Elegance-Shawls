// LOCAL ONLY: a stand-in for apps/whatsapp-bridge that needs no WhatsApp account. It exposes the bridge's internal HTTP API
// (health, pairing, send, media), publishes events to Redis exactly like the real bridge, and serves a browser page at /sim with
// a "customer phone" and a "shop phone". Sends go through the real outbound guards (24-hour rule, rate cap, idempotency).
//   REDIS_URL=redis://127.0.0.1:56379/1 WHATSAPP_BRIDGE_TOKEN=local-dev-token node dev/fake-bridge.mjs
import { createServer } from 'node:http';
import Redis from 'ioredis';
import { createSender, SendError } from '../src/sender.mjs';
import { createMediaStore } from '../src/media.mjs';
import { createPairing } from '../src/pairing.mjs';
import { isValidEvent } from '../src/events.mjs';
import { extractMultipartFile, newId, simEvent } from './sim-lib.mjs';

const TOKEN = process.env.WHATSAPP_BRIDGE_TOKEN ?? '';
const PORT = Number(process.env.PORT ?? 3600);
if (!TOKEN || !process.env.REDIS_URL) { console.error('Set WHATSAPP_BRIDGE_TOKEN and REDIS_URL'); process.exit(1); }
const redis = new Redis(process.env.REDIS_URL);
const media = createMediaStore();
const pairing = createPairing();
const log = []; // every simulated message, for the page
const status = { state: 'needs_pairing', since: new Date().toISOString(), number: null };
const setState = (s) => { status.state = s; status.since = new Date().toISOString(); };

const publish = async (event) => {
  if (!isValidEvent(event)) throw new SendError(400, 'invalid_event');
  await redis.xadd('wa:inbound', 'MAXLEN', '~', 10000, '*', 'event', JSON.stringify(event));
};

const botIds = new Set();
const sender = createSender({
  getSock: () => (status.state === 'connected' ? sock : null),
  sleep: (ms) => new Promise((r) => setTimeout(r, ms / 5)), // same typing pause, five times faster for a demo
});
const sock = {
  sendPresenceUpdate: async () => {}, readMessages: async () => {},
  async sendMessage(chat, content, { messageId }) {
    log.push({ id: messageId, chat, who: 'bot', text: content.text, at: new Date().toISOString() });
    await publish({ ...simEvent({ from: 'staff', chat, text: content.text }, messageId), via_bot: true }); // the echo, tagged like the real bridge does
  },
};

const readBody = (req) => new Promise((resolve) => { const chunks = []; req.on('data', (c) => chunks.push(c)); req.on('end', () => resolve(Buffer.concat(chunks))); });
const json = (res, code, body) => { res.writeHead(code, { 'content-type': 'application/json' }); res.end(JSON.stringify(body)); };

const PAGE = `<!doctype html><meta charset=utf-8><title>WhatsApp simulator</title>
<style>body{font:15px system-ui;max-width:760px;margin:2rem auto;padding:0 1rem;background:#fbf7f0;color:#2f241f}
fieldset{border:1px solid #e7dac8;border-radius:14px;margin:1rem 0;background:#fff}input,textarea,select{font:inherit;padding:.4rem .6rem;border:1px solid #d8c8b4;border-radius:10px}
button{font:inherit;padding:.45rem 1rem;border-radius:999px;border:0;background:#2f241f;color:#fff;cursor:pointer}#chat{height:340px;overflow:auto;background:#efe7da;border-radius:12px;padding:.6rem}
.m{max-width:80%;margin:.3rem 0;padding:.4rem .7rem;border-radius:12px;white-space:pre-wrap}.customer{background:#fff}.bot{background:#d9e7ff;margin-left:auto}.staff{background:#dcf8c6;margin-left:auto}
small{color:#6f625a}</style>
<h1>WhatsApp simulator</h1><p><small>Local only. This replaces the real bridge: nothing here reaches WhatsApp. Bot = automatic reply, Staff = typed on the shop phone.</small></p>
<fieldset><legend>Customer phone</legend>
<p><label>Number <input id=num value="923009990001" size=14></label> <label>Name <input id=name value="Ayesha" size=10></label></p>
<p><textarea id=text rows=3 style="width:100%" placeholder="e.g. Assalam o Alaikum, I want to order.&#10;Ref: ES-XXXXXX   (paste a reference from the cart)&#10;or ask: red shawl under 4000"></textarea></p>
<button onclick="send('customer')">Send as customer</button> <button onclick="send('voice')">Send as voice note (text = what was said)</button></fieldset>
<fieldset><legend>Shop phone (staff typing)</legend><input id=staff style="width:70%" placeholder="Typing here pauses the bot in this chat"> <button onclick="send('staff')">Send as staff</button></fieldset>
<div id=chat></div><script>
const chat=()=>document.getElementById('num').value.replace(/\\D/g,'')+'@s.whatsapp.net';
async function send(from){const text=from==='staff'?staff.value:document.getElementById('text').value;if(!text.trim())return;
await fetch('/sim/send',{method:'POST',body:JSON.stringify({from,chat:chat(),name:name.value,text,voice:from==='voice'})});
(from==='staff'?staff:document.getElementById('text')).value='';poll()}
async function poll(){const r=await (await fetch('/sim/messages?chat='+encodeURIComponent(chat()))).json();
const c=document.getElementById('chat');c.innerHTML=r.map(m=>'<div class="m '+m.who+'"><small>'+m.who+' '+new Date(m.at).toLocaleTimeString()+'</small><br>'+m.text.replace(/[<&]/g,x=>x=='<'?'&lt;':'&amp;')+'</div>').join('');c.scrollTop=c.scrollHeight}
setInterval(poll,1500);poll();</script>`;

createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://x');
    if (req.method === 'GET' && url.pathname === '/sim') { res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' }); return res.end(PAGE); }
    if (req.method === 'GET' && url.pathname === '/sim/messages') return json(res, 200, log.filter((m) => m.chat === url.searchParams.get('chat')));
    if (req.method === 'POST' && url.pathname === '/sim/send') {
      const body = JSON.parse((await readBody(req)).toString() || '{}');
      if (status.state !== 'connected') return json(res, 409, { error: 'not_connected: pair first (Admin > WhatsApp > Connect WhatsApp)' });
      const id = newId();
      const event = simEvent(body, id);
      log.push({ id, chat: body.chat, who: body.voice ? 'customer' : body.from, text: body.voice ? `🎤 ${body.text}` : body.text, at: event.ts });
      if (body.voice) media.put(id, Buffer.from(body.text, 'utf8'), 'audio/ogg');
      if (body.from !== 'staff') sender.noteInbound(body.chat, { id, remoteJid: body.chat }, Date.parse(event.ts));
      await publish(event);
      return json(res, 200, { id });
    }
    if (req.method === 'POST' && url.pathname === '/sim/asr') { // fake self-hosted transcription endpoint
      const boundary = /boundary=(.+)$/.exec(req.headers['content-type'] ?? '')?.[1];
      const text = boundary ? extractMultipartFile((await readBody(req)).toString('utf8'), boundary) : null;
      return json(res, text ? 200 : 400, { text });
    }
    // everything below is the bridge's internal API: token on every call
    if (req.headers.authorization !== `Bearer ${TOKEN}`) { res.writeHead(401).end(); return; }
    const route = `${req.method} ${url.pathname}`;
    if (route === 'GET /health') return json(res, 200, { state: status.state, state_since: status.since, number: status.number, last_event_at: log.at(-1)?.at ?? null, baileys: 'simulated' });
    if (route === 'GET /pairing/status') return json(res, 200, { state: status.state, number: status.number, pairing: pairing.view() });
    if (route === 'POST /pairing/start') {
      if (status.state === 'connected') throw new SendError(409, 'already_connected');
      pairing.start(); pairing.setQr(`simulated-qr-${newId()}`); setState('pairing');
      setTimeout(() => { pairing.end(); status.number = '923001234567'; setState('connected'); }, 6000); // "scanned" after 6 seconds
      return json(res, 200, { state: status.state, pairing: pairing.view() });
    }
    if (route === 'POST /pairing/code') { pairing.setCode('ABCD-1234'); return json(res, 200, { state: status.state, pairing: pairing.view() }); }
    if (route === 'POST /pairing/disconnect') { pairing.end(); status.number = null; setState('needs_pairing'); return json(res, 200, { state: status.state }); }
    if (route === 'POST /send') return json(res, 200, await sender.send(JSON.parse((await readBody(req)).toString() || '{}')));
    const m = /^\/media\/([A-Za-z0-9_-]{1,128})$/.exec(url.pathname);
    if (m && req.method === 'GET') { const item = media.get(m[1]); if (!item) return json(res, 404, { error: 'not_found' }); res.writeHead(200, { 'content-type': item.mimetype }); return res.end(item.buffer); }
    if (m && req.method === 'DELETE') { media.delete(m[1]); return json(res, 200, { deleted: true }); }
    res.writeHead(404).end();
  } catch (err) {
    if (err instanceof SendError) return json(res, err.status, { error: err.code });
    console.error(err);
    json(res, 500, { error: 'internal' });
  }
}).listen(PORT, '127.0.0.1', () => console.log(`fake WhatsApp bridge on http://127.0.0.1:${PORT}  (simulator: /sim)`));
