import { NextResponse } from 'next/server';
import { getBackendBaseUrl, hasSameOrigin } from '@/lib/admin-backend';
import { looksLikeCustomerSessionToken, readCustomerSession } from '@/lib/customer-session';

// Same-origin proxy for /v1/me/memory. The browser holds the session only as an HttpOnly cookie; this handler is the one place that
// turns it into the X-Customer-Session header. It never accepts a customer id, and passes only fixed errors back.
const SEGMENT = /^[A-Za-z0-9_-]{1,64}$/;
const MAX_BODY_BYTES = 2_048;
// The backend's refusal codes are fixed, client-safe strings (memory/service.py). Only these are relayed, never free text.
const REASONS = new Set(['consent_required', 'not_found', 'idempotency_conflict', 'duplicate_key', 'limit_reached', 'gone']);
const PASS_THROUGH = new Set([400, 401, 403, 404, 409, 410, 422, 429]);
const fail = (detail: string, status: number) => NextResponse.json({ detail }, { status, headers: { 'cache-control': 'no-store' } });

async function forward(request: Request, { params }: { params: Promise<{ path?: string[] }> }) {
  const base = getBackendBaseUrl();
  if (!base) return fail('Memory is not configured.', 503);
  const mutating = request.method !== 'GET';
  if (mutating && !hasSameOrigin(request)) return fail('Invalid request origin.', 403);

  const token = readCustomerSession(request);
  if (!looksLikeCustomerSessionToken(token)) return fail('Sign in is required.', 401);

  const segments = (await params).path ?? [];
  if (segments.length > 2 || !segments.every((s) => s === 'consent' || SEGMENT.test(s))) return fail('Not found.', 404);

  let body: string | undefined;
  if (request.method === 'POST' || request.method === 'PUT' || request.method === 'PATCH') {
    body = await request.text();
    if (body.length > MAX_BODY_BYTES) return fail('Request body too large.', 413);
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${base}/v1/me/memory${segments.length ? `/${segments.join('/')}` : ''}`, {
      method: request.method,
      headers: { 'X-Customer-Session': token, ...(body !== undefined ? { 'content-type': 'application/json' } : {}) },
      body,
      cache: 'no-store',
    });
  } catch {
    return fail('Memory is temporarily unavailable.', 503);
  }

  if (upstream.status === 204) return new Response(null, { status: 204, headers: { 'cache-control': 'no-store' } });
  if (!upstream.ok) {
    // Status plus, at most, an allowlisted reason code. Everything else about a refusal stays out; unknown statuses become 503.
    const detail = (await upstream.json().catch(() => null))?.detail;
    const reason = typeof detail?.reason === 'string' && REASONS.has(detail.reason) ? detail.reason : undefined;
    const status = PASS_THROUGH.has(upstream.status) ? upstream.status : 503;
    return NextResponse.json({ detail: status === 401 ? 'Sign in is required.' : 'Request was not accepted.', ...(reason ? { reason } : {}) },
      { status, headers: { 'cache-control': 'no-store' } });
  }
  return NextResponse.json(await upstream.json().catch(() => null), { status: upstream.status, headers: { 'cache-control': 'no-store' } });
}

export { forward as GET, forward as POST, forward as PUT, forward as PATCH, forward as DELETE };
