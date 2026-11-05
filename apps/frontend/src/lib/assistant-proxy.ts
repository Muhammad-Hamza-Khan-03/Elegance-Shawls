import { internalApiHeaders } from '@/lib/api';
import { hasSameOrigin } from '@/lib/admin-backend';
import { traceHeaders } from '@/lib/trace';

const MAX_BODY_BYTES = 16_384;
const NO_STORE = { 'cache-control': 'no-store' };

// Anonymous same-origin proxy to the assistant backend. Never sends X-Admin-Key. 404 when the flag is off.
export async function proxyAssistant(request: Request, path: string): Promise<Response> {
  if (process.env.NEXT_PUBLIC_ASSISTANT_ENABLED !== 'true') return Response.json({ error: 'assistant_disabled' }, { status: 404, headers: NO_STORE });
  const apiUrl = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '');
  if (!apiUrl) return Response.json({ error: 'assistant_unavailable' }, { status: 503, headers: NO_STORE });
  if (!hasSameOrigin(request)) return Response.json({ error: 'forbidden' }, { status: 403, headers: NO_STORE });
  const body = await request.text();
  if (body.length > MAX_BODY_BYTES) return Response.json({ error: 'too_large' }, { status: 413, headers: NO_STORE });
  const headers: Record<string, string> = { 'content-type': 'application/json', ...internalApiHeaders(), ...traceHeaders(request.headers.get('traceparent')) };
  const forwarded = request.headers.get('x-forwarded-for'); // backend rate-limits per visitor
  if (forwarded) headers['x-forwarded-for'] = forwarded;
  try {
    const upstream = await fetch(`${apiUrl}${path}`, { method: 'POST', headers, body, cache: 'no-store', signal: AbortSignal.timeout(15_000) });
    const out: Record<string, string> = { ...NO_STORE, 'content-type': upstream.headers.get('content-type') ?? 'application/json' };
    const marker = upstream.headers.get('x-vercel-ai-ui-message-stream');
    if (marker) out['x-vercel-ai-ui-message-stream'] = marker;
    return new Response(upstream.body, { status: upstream.status, headers: out });
  } catch {
    return Response.json({ error: 'assistant_unavailable' }, { status: 503, headers: NO_STORE });
  }
}
