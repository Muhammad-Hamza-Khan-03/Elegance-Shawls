import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { loadConfig } from './config.mjs';
import { toEvent, isValidEvent, isIgnoredJid } from './events.mjs';
import { backoffMs } from './backoff.mjs';

const fx = (n) => JSON.parse(readFileSync(new URL(`../fixtures/${n}`, import.meta.url)));

test('switch defaults off and only the literal true enables it', () => {
  assert.equal(loadConfig({}).enabled, false);
  assert.equal(loadConfig({ WHATSAPP_BRIDGE_ENABLED: '1' }).enabled, false);
  assert.equal(loadConfig({ WHATSAPP_BRIDGE_ENABLED: 'TRUE', WHATSAPP_BRIDGE_TOKEN: 't', REDIS_URL: 'r' }).problems.length, 0);
  assert.equal(loadConfig({ WHATSAPP_BRIDGE_ENABLED: 'true' }).problems.length, 2);
  assert.equal(loadConfig({}).problems.length, 0);
});

test('maps text, quoted and fromMe messages', () => {
  const e = toEvent({ key: { remoteJid: '92300@s.whatsapp.net', id: 'A1', fromMe: false }, pushName: 'Ayesha', messageTimestamp: 1793000000,
    message: { extendedTextMessage: { text: 'Ref: ES-ABCDEF', contextInfo: { stanzaId: 'Q1' } } } });
  assert.deepEqual([e.type, e.text, e.quoted_id, e.from_me, e.push_name], ['text', 'Ref: ES-ABCDEF', 'Q1', false, 'Ayesha']);
  assert.ok(isValidEvent(e));
  const mine = toEvent({ key: { remoteJid: '92300@s.whatsapp.net', id: 'A2', fromMe: true }, message: { conversation: 'ok' } });
  assert.equal(mine.from_me, true); assert.equal(mine.push_name, null);
});

test('ignores status, groups, newsletters and protocol messages; voice notes keep type only', () => {
  for (const jid of ['status@broadcast', '1-2@g.us', '1@newsletter']) {
    assert.ok(isIgnoredJid(jid));
    assert.equal(toEvent({ key: { remoteJid: jid, id: 'x' }, message: { conversation: 'hi' } }), null);
  }
  assert.equal(toEvent({ key: { remoteJid: '1@s.whatsapp.net', id: 'x' }, message: { protocolMessage: {} } }), null);
  const voice = toEvent({ key: { remoteJid: '1@s.whatsapp.net', id: 'v' }, message: { audioMessage: {} } });
  assert.equal(voice.type, 'audio'); assert.equal(voice.text, null);
});

test('contract fixtures: valid ones pass, invalid ones fail', () => {
  for (const f of readdirSync(new URL('../fixtures/', import.meta.url))) {
    assert.equal(isValidEvent(fx(f)), f.startsWith('valid-'), f);
  }
});

test('reconnect backoff doubles and caps at 5 minutes', () => {
  assert.deepEqual([0, 1, 2].map(backoffMs), [1000, 2000, 4000]);
  assert.equal(backoffMs(30), 300000);
});
