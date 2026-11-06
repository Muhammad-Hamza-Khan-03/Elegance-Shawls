// Pure mapping from a Baileys message to the wa:inbound v1 event (schema/inbound-event.v1.json). No I/O.
const MEDIA = { imageMessage: 'image', audioMessage: 'audio', videoMessage: 'video', documentMessage: 'document' };

export const isIgnoredJid = (jid = '') =>
  jid === 'status@broadcast' || jid.endsWith('@g.us') || jid.endsWith('@newsletter') || jid.endsWith('@broadcast');

export function toEvent(msg) {
  const chat = msg?.key?.remoteJid;
  const id = msg?.key?.id;
  if (!chat || !id || isIgnoredJid(chat) || !msg.message) return null;
  const m = msg.message;
  const kind = Object.keys(MEDIA).find((k) => m[k]);
  const text = m.conversation ?? m.extendedTextMessage?.text ?? (kind ? m[kind].caption : undefined) ?? null;
  const type = kind ? MEDIA[kind] : text !== null ? 'text' : 'other';
  if (type === 'other' && m.protocolMessage) return null; // key/history housekeeping, not a chat message
  const seconds = Number(msg.messageTimestamp?.toString?.() ?? msg.messageTimestamp ?? 0) || Math.floor(Date.now() / 1000);
  return {
    v: 1,
    wa_id: id,
    chat,
    lid: msg.key.remoteJidAlt?.endsWith('@lid') ? msg.key.remoteJidAlt : chat.endsWith('@lid') ? chat : null,
    from_me: Boolean(msg.key.fromMe),
    type,
    text: text === null ? null : String(text).slice(0, 8192),
    quoted_id: m.extendedTextMessage?.contextInfo?.stanzaId ?? null,
    media: null, // set by the bridge to "voice:<wa_id>" only when it is holding the audio (WHATSAPP_VOICE_ENABLED)
    push_name: msg.key.fromMe ? null : (msg.pushName ?? null),
    ts: new Date(seconds * 1000).toISOString(),
  };
}

// Dependency-free check against the shared schema's required shape; fixtures keep it in step with Python's pydantic model.
export function isValidEvent(e) {
  const allowed = ['v', 'wa_id', 'chat', 'lid', 'from_me', 'type', 'text', 'quoted_id', 'media', 'push_name', 'via_bot', 'ts'];
  return Boolean(e) && typeof e === 'object' && Object.keys(e).every((k) => allowed.includes(k)) && e.v === 1 &&
    typeof e.wa_id === 'string' && e.wa_id.length > 0 && typeof e.chat === 'string' && e.chat.length > 0 &&
    typeof e.from_me === 'boolean' && ['text', 'image', 'audio', 'video', 'document', 'other'].includes(e.type) &&
    typeof e.ts === 'string' && !Number.isNaN(Date.parse(e.ts));
}
