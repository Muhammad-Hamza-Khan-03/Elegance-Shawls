import { internalApiHeaders } from '@/lib/api';
import { hasSameOrigin } from '@/lib/admin-backend';
import { traceHeaders } from '@/lib/trace';

// Same-origin proxy for anonymous interaction events. The HTTP-only session cookie lives on the
// storefront origin; the backend signs and verifies it. Tracking is best effort, so every
// failure answers 202 and the page never sees an error.
const MAX_BODY_BYTES = 32_768;
const COOKIE = 'es_sid';
const accepted = (count = 0, headers?: HeadersInit) => Response.json({ accepted: count }, { status: 202, headers });

const readCookie = (request: Request) =>
  request.headers.get('cookie')?.split(';').map((part) => part.trim()).find((part) => part.startsWith(`${COOKIE}=`))?.slice(COOKIE.length + 1);

export async function POST(request: Request) {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '');
  if (!apiUrl || !hasSameOrigin(request)) return accepted();
  try {
    const body = await request.text();
    if (body.length > MAX_BODY_BYTES) return accepted();
    const headers: Record<string, string> = { 'content-type': 'application/json', ...internalApiHeaders(), ...traceHeaders(request.headers.get('traceparent')) };
    // Pass the browser's privacy signals through: the backend stores nothing when either is set.
    for (const name of ['dnt', 'sec-gpc']) {
      const value = request.headers.get(name);
      if (value) headers[name] = value;
    }
    const session = readCookie(request);
    if (session) headers['x-session-token'] = session;
    // The backend rate-limits per client address, so forward the visitor's address, not this server's.
    const forwarded = request.headers.get('x-forwarded-for');
    if (forwarded) headers['x-forwarded-for'] = forwarded;
    const upstream = await fetch(`${apiUrl}/v1/events`, { method: 'POST', headers, body, cache: 'no-store', signal: AbortSignal.timeout(2000) });
    if (!upstream.ok) return accepted();
    const data = (await upstream.json()) as { accepted?: number; session_token?: string };
    const cookie = data.session_token
      ? `${COOKIE}=${data.session_token}; Path=/; Max-Age=${30 * 24 * 3600}; HttpOnly; SameSite=Lax${process.env.NODE_ENV === 'production' ? '; Secure' : ''}`
      : undefined;
    return accepted(data.accepted ?? 0, cookie ? { 'set-cookie': cookie } : undefined);
  } catch {
    return accepted();
  }
}
