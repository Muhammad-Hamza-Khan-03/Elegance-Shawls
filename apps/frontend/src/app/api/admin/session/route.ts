import { NextResponse } from 'next/server';
import { buildTargetUrl, fetchAdminIdentity, hasSameOrigin } from '@/lib/admin-backend';
import { clearLoginFailures, getLoginClientKey, loginRetryAfterSeconds, recordLoginFailure } from '@/lib/admin-login-throttle';
import { ADMIN_SESSION_COOKIE, adminCookieOptions, looksLikeSessionToken, readAdminSession } from '@/lib/admin-session';

const backend = (path: string) => buildTargetUrl(path, 'http://unused.invalid/');

export async function GET(request: Request) {
  const identity = await fetchAdminIdentity(readAdminSession(request));
  return NextResponse.json(identity ? { authenticated: true, email: identity.email, role: identity.role } : { authenticated: false });
}

export async function POST(request: Request) {
  const target = backend('/v1/admin/auth/login');
  if (!target) {
    return NextResponse.json({ detail: 'Administrative access is not configured.' }, { status: 503 });
  }

  // Same-origin plus JSON (which forces a CORS preflight) keep cross-site pages from signing a browser in (login CSRF).
  if (!hasSameOrigin(request)) {
    return NextResponse.json({ detail: 'Invalid request origin.' }, { status: 403 });
  }
  if (!request.headers.get('content-type')?.toLowerCase().startsWith('application/json')) {
    return NextResponse.json({ detail: 'Sign-in requests must be JSON.' }, { status: 415 });
  }

  const clientKey = getLoginClientKey(request);
  const retryAfter = loginRetryAfterSeconds(clientKey);
  if (retryAfter > 0) {
    return NextResponse.json(
      { detail: 'Too many failed sign-in attempts. Try again later.' },
      { status: 429, headers: { 'Retry-After': String(retryAfter) } },
    );
  }

  const body = (await request.json().catch(() => null)) as { email?: unknown; password?: unknown } | null;
  const email = typeof body?.email === 'string' ? body.email.trim() : '';
  const password = typeof body?.password === 'string' ? body.password : '';
  if (!email || !password) {
    return NextResponse.json({ detail: 'Enter your email and password.' }, { status: 400 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ email, password }),
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ detail: 'Sign-in is temporarily unavailable.' }, { status: 503 });
  }

  if (upstream.status === 401 || upstream.status === 422) {
    recordLoginFailure(clientKey);
    return NextResponse.json({ detail: 'Invalid email or password.' }, { status: 401 });
  }
  const session = upstream.ok ? await upstream.json().catch(() => null) : null;
  if (!session || !looksLikeSessionToken(session.token)) {
    return NextResponse.json({ detail: 'Sign-in is temporarily unavailable.' }, { status: upstream.status === 429 ? 429 : 503 });
  }

  clearLoginFailures(clientKey);
  const expiresAt = Math.floor(new Date(session.expires_at).getTime() / 1000);
  const maxAge = Math.max(1, expiresAt - Math.floor(Date.now() / 1000));
  // The token goes only into the HttpOnly cookie; the response body never contains it.
  const response = NextResponse.json({ authenticated: true, email: session.account.email, role: session.account.role, expiresAt });
  response.cookies.set(ADMIN_SESSION_COOKIE, session.token, { ...adminCookieOptions, maxAge });
  return response;
}

export async function DELETE(request: Request) {
  if (!hasSameOrigin(request)) {
    return NextResponse.json({ detail: 'Invalid request origin.' }, { status: 403 });
  }
  const token = readAdminSession(request);
  const target = backend('/v1/admin/auth/logout');
  if (looksLikeSessionToken(token) && target) {
    // Revoke server-side first, so a copied cookie is dead too. A failure must not trap the user signed in locally.
    await fetch(target, { method: 'POST', headers: { 'X-Admin-Session': token }, cache: 'no-store' }).catch(() => null);
  }
  const response = NextResponse.json({ authenticated: false });
  response.cookies.set(ADMIN_SESSION_COOKIE, '', { ...adminCookieOptions, maxAge: 0 });
  return response;
}
