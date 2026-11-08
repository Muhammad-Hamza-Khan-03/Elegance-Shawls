import test from 'node:test';
import assert from 'node:assert/strict';
import { extractMultipartFile, simEvent } from './sim-lib.mjs';
import { isValidEvent } from '../src/events.mjs';

const T = new Date('2026-11-07T10:00:00Z');

test('simulated events are valid wa:inbound v1 events', () => {
  const chat = '923009990001@s.whatsapp.net';
  const customer = simEvent({ from: 'customer', chat, name: 'Ayesha', text: 'Ref: ES-ABCDEF' }, 'ID1', T);
  assert.ok(isValidEvent(customer));
  assert.deepEqual([customer.from_me, customer.push_name, customer.type], [false, 'Ayesha', 'text']);
  const staff = simEvent({ from: 'staff', chat, name: 'x', text: 'ok' }, 'ID2', T);
  assert.deepEqual([isValidEvent(staff), staff.from_me, staff.push_name], [true, true, null]);
  const voice = simEvent({ from: 'customer', chat, voice: true, text: 'red shawl' }, 'ID3', T);
  assert.ok(isValidEvent(voice));
  assert.deepEqual([voice.type, voice.text, voice.media], ['audio', null, 'voice:ID3']);
});

test('the fake ASR reads the simulated audio back out of a multipart body', () => {
  const body = ['--B', 'Content-Disposition: form-data; name="model"', '', 'whisper-1', '--B',
    'Content-Disposition: form-data; name="file"; filename="voice.ogg"', 'Content-Type: audio/ogg', '', 'red shawl under 3000', '--B--', ''].join('\r\n');
  assert.equal(extractMultipartFile(body, 'B'), 'red shawl under 3000');
  assert.equal(extractMultipartFile('nothing', 'B'), null);
});
