import { internalApiHeaders } from '@/lib/api';
import { hasSameOrigin } from '@/lib/admin-backend';
import { traceHeaders } from '@/lib/trace';

// Same-origin streaming proxy for POST /v1/assistant/stream. Validation stays in the backend; this passes the SSE body through
// and propagates the browser's abort upstream so a cancelled chat stops the backend stream.
const MAX_BODY_BYTES = 4_096;

export async function POST(request: Request) {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '');
  if (!apiUrl) return Response.json({ detail: 'The assistant is not configured.' }, { status: 503 });
  if (!hasSameOrigin(request)) return Response.json({ detail: 'Invalid request origin.' }, { status: 403 });
  const body = await request.text();
  if (body.length > MAX_BODY_BYTES) return Response.json({ detail: 'Request body too large.' }, { status: 413 });

  const headers: Record<string, string> = { 'content-type': 'application/json', ...internalApiHeaders(), ...traceHeaders(request.headers.get('traceparent')) };
  const forwarded = request.headers.get('x-forwarded-for');
  if (forwarded) headers['x-forwarded-for'] = forwarded;
  try {
    const upstream = await fetch(`${apiUrl}/v1/assistant/stream`, { method: 'POST', headers, body, cache: 'no-store', signal: AbortSignal.any([request.signal, AbortSignal.timeout(30_000)]) });
    const type = upstream.headers.get('content-type') ?? 'application/json';
    return new Response(upstream.body, { status: upstream.status, headers: { 'content-type': type, 'cache-control': 'no-store' } });
  } catch {
    return Response.json({ detail: 'The assistant is temporarily unavailable.' }, { status: 503 });
  }
}
