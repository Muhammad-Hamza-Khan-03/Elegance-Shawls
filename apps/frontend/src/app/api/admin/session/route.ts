import { NextResponse } from 'next/server';
import { ADMIN_SESSION_COOKIE, hasAdminSecret, issueAdminSession, verifyAdminSession } from '@/lib/admin-session';

const cookieOptions = {
  httpOnly: true,
  sameSite: 'lax' as const,
  secure: process.env.NODE_ENV === 'production',
  path: '/',
};

export async function GET(request: Request) {
  const cookie = request.headers.get('cookie') || '';
  const session = cookie
    .split(';')
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${ADMIN_SESSION_COOKIE}=`))
    ?.slice(`${ADMIN_SESSION_COOKIE}=`.length);

  return NextResponse.json({ authenticated: verifyAdminSession(session ? decodeURIComponent(session) : undefined) });
}

export async function POST(request: Request) {
  if (!hasAdminSecret()) {
    return NextResponse.json({ detail: 'Administrative access is not configured.' }, { status: 503 });
  }

  const body = (await request.json().catch(() => null)) as { key?: string } | null;
  const providedKey = body?.key?.trim() || '';

  if (!providedKey || providedKey !== process.env.ADMIN_API_KEY?.trim()) {
    return NextResponse.json({ detail: 'Invalid administrative credentials.' }, { status: 401 });
  }

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
