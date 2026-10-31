import { internalApiHeaders } from '@/lib/api';
import { hasSameOrigin } from '@/lib/admin-backend';
import { traceHeaders } from '@/lib/trace';

// Same-origin proxy for POST /v1/enquiries. The cart is validated by the backend; this only forwards it
// (with the visitor's address for rate limiting) and passes the answer, including 409 stale-cart details, through.
const MAX_BODY_BYTES = 16_384;

export async function POST(request: Request) {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '');
  if (!apiUrl) return Response.json({ detail: 'Enquiries are not configured.' }, { status: 503 });
  if (!hasSameOrigin(request)) return Response.json({ detail: 'Invalid request origin.' }, { status: 403 });
  const body = await request.text();
  if (body.length > MAX_BODY_BYTES) return Response.json({ detail: 'Request body too large.' }, { status: 413 });

  const headers: Record<string, string> = { 'content-type': 'application/json', ...internalApiHeaders(), ...traceHeaders(request.headers.get('traceparent')) };
  const forwarded = request.headers.get('x-forwarded-for');
  if (forwarded) headers['x-forwarded-for'] = forwarded;
  try {
    const upstream = await fetch(`${apiUrl}/v1/enquiries`, { method: 'POST', headers, body, cache: 'no-store', signal: AbortSignal.timeout(5000) });
    return new Response(await upstream.text(), { status: upstream.status, headers: { 'content-type': 'application/json' } });
  } catch {
    return Response.json({ detail: 'Enquiries are temporarily unavailable.' }, { status: 503 });
  }
}
