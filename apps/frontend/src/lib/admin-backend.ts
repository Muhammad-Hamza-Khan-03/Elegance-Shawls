import { readAdminSession, verifyAdminSession } from '@/lib/admin-session';

const getBackendBaseUrl = () => {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (!apiUrl) {
    return null;
  }

  return apiUrl.replace(/\/$/, '');
};

const getAdminKey = () => process.env.ADMIN_API_KEY?.trim() || '';

const hasSameOrigin = (request: Request) => {
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

const buildTargetUrl = (backendPath: string, requestUrl: string) => {
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

export const proxyAdminRequest = async (request: Request, backendPath: string) => {
  if (!verifyAdminSession(readAdminSession(request))) {
    return Response.json({ detail: 'Administrative authentication is required.' }, { status: 401 });
  }

  if (request.method !== 'GET' && request.method !== 'HEAD' && !hasSameOrigin(request)) {
    return Response.json({ detail: 'Invalid request origin.' }, { status: 403 });
  }

  const adminKey = getAdminKey();
  const target = buildTargetUrl(backendPath, request.url);

  if (!target || !adminKey) {
    return new Response(
      JSON.stringify({ detail: 'Admin product management is not configured.' }),
      {
        status: 503,
        headers: { 'content-type': 'application/json' },
      }
    );
  }

  const headers = new Headers({ 'X-Admin-Key': adminKey });
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

  return new Response(await response.text(), {
    status: response.status,
    headers: responseHeaders,
  });
};
