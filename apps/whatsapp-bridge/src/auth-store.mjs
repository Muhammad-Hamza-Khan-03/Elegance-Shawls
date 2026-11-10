// Baileys auth state stores. Two interchangeable backends behind one shape:
//   { state, saveCreds, isPaired(), wipe() }
// "file": useMultiFileAuthState on a named volume (default). "postgres": a dedicated table and role (migration 0020,
// deploy/postgres/whatsapp-auth-role.sh). Postgres values are AES-256-GCM encrypted with a key the database never sees,
// so a database dump or the backup role cannot read the Signal keys (they are as sensitive as an SSH key).
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

export function createCipher(keyHex) {
  const key = Buffer.from(keyHex ?? '', 'hex');
  if (key.length !== 32) throw new Error('WHATSAPP_AUTH_ENCRYPTION_KEY must be 64 hex characters (32 bytes): openssl rand -hex 32');
  return {
    seal(plain) {
      const iv = crypto.randomBytes(12);
      const c = crypto.createCipheriv('aes-256-gcm', key, iv);
      const body = Buffer.concat([c.update(plain, 'utf8'), c.final()]);
      return Buffer.concat([iv, c.getAuthTag(), body]);
    },
    open(blob) {
      const d = crypto.createDecipheriv('aes-256-gcm', key, blob.subarray(0, 12));
      d.setAuthTag(blob.subarray(12, 28));
      return Buffer.concat([d.update(blob.subarray(28)), d.final()]).toString('utf8');
    },
  };
}

export async function fileStore({ dir, baileys }) {
  const { state, saveCreds } = await baileys.useMultiFileAuthState(dir);
  fs.chmodSync(dir, 0o700);
  return { state, saveCreds, isPaired: () => isPairedFile(dir), wipe: () => fs.rmSync(dir, { recursive: true, force: true }) };
}

export function isPairedFile(dir) {
  try { return Boolean(JSON.parse(fs.readFileSync(path.join(dir, 'creds.json'), 'utf8')).me); } catch { return false; }
}

// `db` is any object with query(text, params) -> { rows } (a pg Pool). `baileys` supplies initAuthCreds, BufferJSON, proto.
export async function postgresStore({ db, cipher, baileys, name = 'default' }) {
  const { initAuthCreds, BufferJSON, proto } = baileys;
  const dump = (value) => cipher.seal(JSON.stringify(value, BufferJSON.replacer));
  const load = (blob) => JSON.parse(cipher.open(blob), BufferJSON.reviver);

  const row = async (kind, id) => (await db.query('SELECT value FROM whatsapp_auth_entries WHERE session = $1 AND kind = $2 AND key_id = $3', [name, kind, id])).rows[0];
  const put = (kind, id, value) => db.query(
    'INSERT INTO whatsapp_auth_entries (session, kind, key_id, value) VALUES ($1, $2, $3, $4) ON CONFLICT (session, kind, key_id) DO UPDATE SET value = EXCLUDED.value, updated_at = now()',
    [name, kind, id, dump(value)]);
  const del = (kind, id) => db.query('DELETE FROM whatsapp_auth_entries WHERE session = $1 AND kind = $2 AND key_id = $3', [name, kind, id]);

  const stored = await row('creds', 'creds');
  const creds = stored ? load(stored.value) : initAuthCreds();
  return {
    state: {
      creds,
      keys: {
        get: async (type, ids) => {
          const out = {};
          for (const id of ids) {
            const found = await row(type, id);
            if (!found) continue;
            let value = load(found.value);
            if (type === 'app-state-sync-key' && value) value = proto.Message.AppStateSyncKeyData.fromObject(value);
            out[id] = value;
          }
          return out;
        },
        set: async (data) => {
          for (const [type, entries] of Object.entries(data)) {
            for (const [id, value] of Object.entries(entries)) await (value ? put(type, id, value) : del(type, id));
          }
        },
      },
    },
    saveCreds: () => put('creds', 'creds', creds),
    isPaired: () => Boolean(creds.me),
    wipe: async () => { await db.query('DELETE FROM whatsapp_auth_entries WHERE session = $1', [name]); },
  };
}
