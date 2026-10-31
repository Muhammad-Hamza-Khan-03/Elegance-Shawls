import { NextResponse } from 'next/server';
import { getBackendBaseUrl, hasSameOrigin } from '@/lib/admin-backend';
import {
  CUSTOMER_SESSION_COOKIE,
  customerCookieOptions,
  looksLikeCustomerSessionToken,
  readCustomerSession,
} from '@/lib/customer-session';

const MAX_ID_TOKEN_CHARS = 4096;
const backend = (path: string) => {
  const base = getBackendBaseUrl();
  return base ? `${base}${path}` : null;
};

const clearCookie = (response: NextResponse) => {
  response.cookies.set(CUSTOMER_SESSION_COOKIE, '', { ...customerCookieOptions, maxAge: 0 });
  return response;
};

const errorResponse = (detail: string, status: number) => NextResponse.json({ detail }, { status });

export async function POST(request: Request) {
  const target = backend('/v1/customer/auth/exchange');
  if (!target) return errorResponse('Customer sign-in is not configured.', 503);
  if (!hasSameOrigin(request)) return errorResponse('Invalid request origin.', 403);
  if (!request.headers.get('content-type')?.toLowerCase().startsWith('application/json')) {
    return errorResponse('Sign-in requests must be JSON.', 415);
  }

  const body = (await request.json().catch(() => null)) as Record<string, unknown> | null;
  const idToken = body && Object.keys(body).length === 1 && typeof body.id_token === 'string' ? body.id_token : null;
  if (!idToken || idToken.length > MAX_ID_TOKEN_CHARS) return errorResponse('Invalid identity token.', 400);

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ id_token: idToken }),
      cache: 'no-store',
    });
  } catch {
    return errorResponse('Sign-in is temporarily unavailable.', 503);
  }

  if (!upstream.ok) {
    const payload = (await upstream.json().catch(() => null)) as { detail?: unknown } | null;
    const detail = typeof payload?.detail === 'string' ? payload.detail : 'Sign-in is temporarily unavailable.';
    return errorResponse(detail, upstream.status);
  }

  const session = (await upstream.json().catch(() => null)) as { session_token?: unknown; expires_at?: unknown } | null;
  const sessionToken = typeof session?.session_token === 'string' ? session.session_token : null;
  const expiresAt = typeof session?.expires_at === 'string' ? session.expires_at : null;
  if (!looksLikeCustomerSessionToken(sessionToken) || !expiresAt) {
    return errorResponse('Sign-in is temporarily unavailable.', 503);
  }
  const expiresMs = Date.parse(expiresAt);
  if (!Number.isFinite(expiresMs) || expiresMs <= Date.now()) return errorResponse('Sign-in is temporarily unavailable.', 503);

  const response = NextResponse.json({ authenticated: true, expiresAt: Math.floor(expiresMs / 1000) });
  response.cookies.set(CUSTOMER_SESSION_COOKIE, sessionToken, {
    ...customerCookieOptions,
    maxAge: Math.max(1, Math.floor((expiresMs - Date.now()) / 1000)),
  });
  return response;
}

export async function DELETE(request: Request) {
  if (!hasSameOrigin(request)) return errorResponse('Invalid request origin.', 403);

  const token = readCustomerSession(request);
  const target = backend('/v1/customer/auth/logout');
  if (target && looksLikeCustomerSessionToken(token)) {
    try {
      await fetch(target, {
        method: 'POST',
        headers: { 'X-Customer-Session': token },
        cache: 'no-store',
      });
    } catch {
      // Local sign-out must still remove the browser handle when the backend is unavailable.
    }
  }

  return clearCookie(NextResponse.json({ authenticated: false }));
}
