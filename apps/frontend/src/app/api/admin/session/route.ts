import { NextResponse } from 'next/server';
import { clearLoginFailures, getLoginClientKey, loginRetryAfterSeconds, recordLoginFailure } from '@/lib/admin-login-throttle';
import { ADMIN_SESSION_COOKIE, adminKeyMatches, hasAdminSecret, issueAdminSession, readAdminSession, verifyAdminSession } from '@/lib/admin-session';

const cookieOptions = {
  httpOnly: true,
  sameSite: 'lax' as const,
  secure: process.env.NODE_ENV === 'production',
  path: '/',
};

export async function GET(request: Request) {
  return NextResponse.json({ authenticated: verifyAdminSession(readAdminSession(request)) });
}

export async function POST(request: Request) {
  if (!hasAdminSecret()) {
    return NextResponse.json({ detail: 'Administrative access is not configured.' }, { status: 503 });
  }

  // Requiring JSON forces a CORS preflight, so cross-site forms cannot submit sign-in attempts.
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

  const body = (await request.json().catch(() => null)) as { key?: unknown } | null;
  const providedKey = typeof body?.key === 'string' ? body.key.trim() : '';

  if (!adminKeyMatches(providedKey)) {
    recordLoginFailure(clientKey);
    return NextResponse.json({ detail: 'Invalid administrative credentials.' }, { status: 401 });
  }

  clearLoginFailures(clientKey);
  const session = issueAdminSession();
  if (!session) {
    return NextResponse.json({ detail: 'Administrative access is not configured.' }, { status: 503 });
  }

  const response = NextResponse.json({ authenticated: true, expiresAt: session.expiresAt });
  response.cookies.set(ADMIN_SESSION_COOKIE, session.token, { ...cookieOptions, maxAge: session.maxAge });
  return response;
}

export async function DELETE() {
  const response = NextResponse.json({ authenticated: false });
  response.cookies.set(ADMIN_SESSION_COOKIE, '', { ...cookieOptions, maxAge: 0 });
  return response;
}
