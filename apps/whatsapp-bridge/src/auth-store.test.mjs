import test from 'node:test';
import assert from 'node:assert/strict';
import { createCipher, postgresStore } from './auth-store.mjs';
import { createMediaStore } from './media.mjs';
import { loadConfig } from './config.mjs';

const KEY = 'a'.repeat(64);
const baileys = {
  initAuthCreds: () => ({ noiseKey: Buffer.from('noise'), registered: false }),
  BufferJSON: {
    replacer: (_k, v) => (Buffer.isBuffer(v) ? { type: 'Buffer', data: v.toString('base64') } : v && v.type === 'Buffer' && typeof v.data === 'string' ? v : v),
    reviver: (_k, v) => (v && v.type === 'Buffer' && typeof v.data === 'string' ? Buffer.from(v.data, 'base64') : v),
  },
  proto: { Message: { AppStateSyncKeyData: { fromObject: (o) => ({ wrapped: o }) } } },
};
function fakeDb() {
  const rows = new Map();
  return {
    rows,
    async query(sql, p) {
      const k = (s, kind, id) => `${s}|${kind}|${id}`;
      if (sql.startsWith('SELECT')) { const r = rows.get(k(...p)); return { rows: r ? [{ value: r }] : [] }; }
      if (sql.startsWith('INSERT')) { rows.set(k(p[0], p[1], p[2]), p[3]); return { rows: [] }; }
      if (sql.includes('AND kind')) { rows.delete(k(...p)); return { rows: [] }; }
      for (const key of [...rows.keys()]) if (key.startsWith(`${p[0]}|`)) rows.delete(key);
      return { rows: [] };
    },
  };
}

test('cipher round-trips, uses a fresh IV, and rejects tampering and wrong keys', () => {
  const c = createCipher(KEY);
  const a = c.seal('secret'); const b = c.seal('secret');
  assert.notDeepEqual(a, b);
  assert.equal(c.open(a), 'secret');
  const bad = Buffer.from(a); bad[bad.length - 1] ^= 1;
  assert.throws(() => c.open(bad));
  assert.throws(() => createCipher('b'.repeat(64)).open(a));
  assert.throws(() => createCipher('short'));
});

test('postgres store persists encrypted creds and keys, and never writes plaintext', async () => {
  const db = fakeDb();
  const cipher = createCipher(KEY);
  const store = await postgresStore({ db, cipher, baileys });
  assert.equal(store.isPaired(), false);
  store.state.creds.me = { id: '92300:1@s.whatsapp.net' };
  await store.saveCreds();
  await store.state.keys.set({ 'pre-key': { 1: { private: Buffer.from('k1') } }, 'app-state-sync-key': { A: { keyData: 'x' } } });
  for (const blob of db.rows.values()) assert.ok(!blob.toString('latin1').includes('92300'));
  const again = await postgresStore({ db, cipher, baileys });
  assert.equal(again.isPaired(), true);
  const got = await again.state.keys.get('pre-key', ['1', '2']);
  assert.deepEqual(Object.keys(got), ['1']);
  assert.equal(Buffer.from(got['1'].private).toString(), 'k1');
  assert.deepEqual((await again.state.keys.get('app-state-sync-key', ['A'])).A, { wrapped: { keyData: 'x' } });
  await again.state.keys.set({ 'pre-key': { 1: null } });
  assert.deepEqual(await again.state.keys.get('pre-key', ['1']), {});
  await again.wipe();
  assert.equal(db.rows.size, 0);
});

test('media store is bounded, expires, and deletes on request', () => {
  let t = 0;
  const m = createMediaStore({ ttlMs: 1000, maxBytes: 4, maxItems: 2, now: () => t });
  assert.equal(m.put('a', Buffer.from('12'), 'audio/ogg'), true);
  assert.equal(m.put('big', Buffer.from('12345'), 'audio/ogg'), false);
  assert.equal(m.put('b', Buffer.from('1'), 'audio/ogg'), true);
  assert.equal(m.put('c', Buffer.from('1'), 'audio/ogg'), false);
  assert.equal(m.delete('a'), true);
  assert.equal(m.get('a'), null);
  t = 1001;
  assert.equal(m.get('b'), null);
  assert.equal(m.size(), 0);
});

test('config validates the postgres auth store only when enabled', () => {
  const on = { WHATSAPP_BRIDGE_ENABLED: 'true', WHATSAPP_BRIDGE_TOKEN: 't', REDIS_URL: 'r' };
  assert.equal(loadConfig(on).problems.length, 0);
  assert.equal(loadConfig({ ...on, WHATSAPP_AUTH_STORE: 'postgres' }).problems.length, 2);
  assert.equal(loadConfig({ ...on, WHATSAPP_AUTH_STORE: 'postgres', WHATSAPP_AUTH_DATABASE_URL: 'u', WHATSAPP_AUTH_ENCRYPTION_KEY: KEY }).problems.length, 0);
  assert.equal(loadConfig({ ...on, WHATSAPP_AUTH_STORE: 'redis' }).problems.length, 1);
  assert.equal(loadConfig({ WHATSAPP_AUTH_STORE: 'postgres' }).problems.length, 0);
  assert.equal(loadConfig({}).voiceEnabled, false);
});
