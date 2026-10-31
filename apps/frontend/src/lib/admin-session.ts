// The cookie holds an opaque, server-side session token issued by the backend at sign-in. The frontend cannot
// verify it (and so cannot be fooled by a forged one): the backend checks expiry, revocation and the account on every call.
export const ADMIN_SESSION_COOKIE = 'es_admin_session';

export const adminCookieOptions = {
  httpOnly: true,
  sameSite: 'lax' as const,
  secure: process.env.NODE_ENV === 'production',
  path: '/',
};

export const expiredAdminSessionCookie = () =>
  `${ADMIN_SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax${adminCookieOptions.secure ? '; Secure' : ''}`;

export const readAdminSession = (request: Request) => {
  const value = (request.headers.get('cookie') || '')
    .split(';')
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${ADMIN_SESSION_COOKIE}=`))
    ?.slice(`${ADMIN_SESSION_COOKIE}=`.length);
  if (!value) return undefined;
  try {
    return decodeURIComponent(value);
  } catch {
    return undefined;
  }
};

// Shape check only, so garbage never costs a backend round trip. Validity is the backend's decision.
export const looksLikeSessionToken = (token?: string | null): token is string =>
  Boolean(token && /^es1\.[A-Za-z0-9_-]{20,100}$/.test(token));
