// Short-lived, in-memory holder for voice notes. Audio is never written to disk or Redis: the backend fetches it once,
// transcribes it, and deletes it; anything left is dropped after the TTL. Bounded so a flood cannot exhaust memory.
export function createMediaStore({ ttlMs = 5 * 60 * 1000, maxBytes = 2 * 1024 * 1024, maxItems = 20, now = Date.now } = {}) {
  const items = new Map();
  const sweep = () => { for (const [id, v] of items) if (now() - v.at > ttlMs) items.delete(id); };
  return {
    put(id, buffer, mimetype) {
      sweep();
      if (!Buffer.isBuffer(buffer) || buffer.length === 0 || buffer.length > maxBytes || items.size >= maxItems) return false;
      items.set(id, { buffer, mimetype, at: now() });
      return true;
    },
    get(id) { sweep(); return items.get(id) ?? null; },
    delete(id) { return items.delete(id); },
    size() { sweep(); return items.size; },
  };
}
