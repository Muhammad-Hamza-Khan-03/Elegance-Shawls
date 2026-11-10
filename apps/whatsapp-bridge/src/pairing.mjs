// Pairing session bookkeeping (pure): one session at a time, expires after 2 minutes. The QR is a login credential:
// it lives only here, is returned only to the authenticated internal caller, and is never logged.
export const PAIRING_TTL_MS = 2 * 60 * 1000;

export function createPairing(now = Date.now) {
  let session = null;
  const active = () => {
    if (session && now() >= session.expiresAt) session = null;
    return session;
  };
  return {
    active,
    start() { return (session = active() ?? { expiresAt: now() + PAIRING_TTL_MS, qr: null, code: null }); },
    setQr(qr) { if (active()) session.qr = qr; },
    setCode(code) { if (active()) session.code = code; },
    end() { session = null; },
    view() { const s = active(); return s ? { qr: s.qr, code: s.code, expires_at: new Date(s.expiresAt).toISOString() } : null; },
  };
}
