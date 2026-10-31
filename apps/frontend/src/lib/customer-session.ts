export const CUSTOMER_SESSION_COOKIE = 'cs_customer_session';

export const customerCookieOptions = {
  httpOnly: true,
  sameSite: 'lax' as const,
  secure: process.env.NODE_ENV === 'production',
  path: '/',
};

export const looksLikeCustomerSessionToken = (token?: string | null): token is string =>
  Boolean(token && /^cs1\.[A-Za-z0-9_-]{20,100}$/.test(token));

export const readCustomerSession = (request: Request) => {
  const value = (request.headers.get('cookie') || '')
    .split(';')
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${CUSTOMER_SESSION_COOKIE}=`))
    ?.slice(`${CUSTOMER_SESSION_COOKIE}=`.length);
  if (!value) return undefined;
  try {
    return decodeURIComponent(value);
  } catch {
    return undefined;
  }
};
