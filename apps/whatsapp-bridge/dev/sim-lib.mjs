// Pure helpers for the local simulator (no I/O). The simulator stands in for WhatsApp so the whole flow can be seen on a laptop.
import crypto from 'node:crypto';

export const newId = () => '3EB0' + crypto.randomBytes(8).toString('hex').toUpperCase();

// The fake "audio" of a simulated voice note is its transcript's bytes; the fake ASR reads them back out of the multipart body.
export function extractMultipartFile(body, boundary) {
  for (const part of body.split(`--${boundary}`)) {
    const split = part.indexOf('\r\n\r\n');
    if (split > 0 && /name="file"/.test(part.slice(0, split))) return part.slice(split + 4).replace(/\r\n$/, '');
  }
  return null;
}

// Builds a wa:inbound v1 event for a message typed into the simulator.
export function simEvent({ from, chat, name, text, voice }, id = newId(), now = new Date()) {
  const base = { v: 1, wa_id: id, chat, lid: null, from_me: from === 'staff', quoted_id: null, push_name: from === 'staff' ? null : name || null, ts: now.toISOString() };
  if (voice) return { ...base, type: 'audio', text: null, media: `voice:${id}` };
  return { ...base, type: 'text', text, media: null };
}
