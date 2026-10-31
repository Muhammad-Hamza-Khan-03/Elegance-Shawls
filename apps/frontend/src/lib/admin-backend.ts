import { expiredAdminSessionCookie, looksLikeSessionToken, readAdminSession } from '@/lib/admin-session';

export const getBackendBaseUrl = () => {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (!apiUrl) {
    return null;
  }

  return apiUrl.replace(/\/$/, '');
};

export const hasSameOrigin = (request: Request) => {
  const origin = request.headers.get('origin');
  if (!origin) return false;

  try {
    const requestUrl = new URL(request.url);
    // Next.js can canonicalize request.url to localhost while preserving the public Host header.
    const host = request.headers.get('host') || requestUrl.host;
    return origin === new URL(`${requestUrl.protocol}//${host}`).origin;
  } catch {
    return false;
  }
};

export const buildTargetUrl = (backendPath: string, requestUrl: string) => {
  const baseUrl = getBackendBaseUrl();
  if (!baseUrl) {
    return null;
  }

  const target = new URL(`${baseUrl}${backendPath.startsWith('/') ? backendPath : `/${backendPath}`}`);
  const incoming = new URL(requestUrl);
  incoming.searchParams.forEach((value, key) => {
    target.searchParams.append(key, value);
  });
  return target;
};

export type AdminIdentity = { email: string; role: 'viewer' | 'editor' | 'owner'; displayName: string | null };

// Asks the backend who this session belongs to (null when it is invalid, expired, revoked or the backend is down).
export const fetchAdminIdentity = async (token?: string | null): Promise<AdminIdentity | null> => {
  const baseUrl = getBackendBaseUrl();
  if (!baseUrl || !looksLikeSessionToken(token)) return null;
  try {
    const response = await fetch(`${baseUrl}/v1/admin/auth/me`, { headers: { 'X-Admin-Session': token }, cache: 'no-store' });
    if (!response.ok) return null;
    const body = await response.json();
    if (!body?.account?.email) return null;
    return { email: body.account.email, role: body.role, displayName: body.account.display_name ?? null };
  } catch {
    return null;
  }
};

export const proxyAdminRequest = async (request: Request, backendPath: string) => {
  const token = readAdminSession(request);
  if (!looksLikeSessionToken(token)) {
    return Response.json({ detail: 'Administrative authentication is required.' }, { status: 401 });
  }

  if (request.method !== 'GET' && request.method !== 'HEAD' && !hasSameOrigin(request)) {
    return Response.json({ detail: 'Invalid request origin.' }, { status: 403 });
  }

  const target = buildTargetUrl(backendPath, request.url);

  if (!target) {
    return new Response(
      JSON.stringify({ detail: 'Admin product management is not configured.' }),
      {
        status: 503,
        headers: { 'content-type': 'application/json' },
      }
    );
  }

  const headers = new Headers({ 'X-Admin-Session': token });
  const contentType = request.headers.get('content-type');
  if (contentType) {
    headers.set('content-type', contentType);
  }

  let body: BodyInit | undefined;
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    const text = await request.text();
    if (text) {
      body = text;
    }
  }

  const response = await fetch(target, {
    method: request.method,
    headers,
    body,
    cache: 'no-store',
  });

  const responseHeaders = new Headers();
  const responseContentType = response.headers.get('content-type');
  responseHeaders.set('content-type', responseContentType || 'application/json');
  // The backend says the session is gone (expired, revoked, account disabled): drop the dead cookie too.
  if (response.status === 401) responseHeaders.append('set-cookie', expiredAdminSessionCookie());

  return new Response(await response.text(), {
    status: response.status,
    headers: responseHeaders,
  });
};
