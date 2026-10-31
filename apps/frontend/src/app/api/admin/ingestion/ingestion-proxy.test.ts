import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GET as listStagedRoute } from './staged/route';
import { GET as pkrSuggestion } from './staged/[stagedId]/pkr-suggestion/route';
import { POST as stagedAction } from './staged/[stagedId]/[action]/route';
import { GET as getEnrichment, POST as postEnrichment } from './staged/[stagedId]/enrichment/route';
import { POST as cancelEnrichmentRoute } from './staged/[stagedId]/enrichment/[suggestionId]/cancel/route';
import { GET as listJobs, POST as createJob } from './jobs/route';
import { ADMIN_SESSION_COOKIE } from '@/lib/admin-session';

const TOKEN = `es1.${'a'.repeat(43)}`;

const origin = 'https://store.example.invalid';
const id = '507f1f77bcf86cd799439011';
const uuid = '22222222-2222-4222-8222-222222222222';
const suggestionId = '11111111-1111-4111-8111-111111111111';

const routes = [
  { name: 'list staged', method: 'GET', path: '/api/admin/ingestion/staged?status=pending_review', backend: '/products/admin/ingestion/staged?status=pending_review', handler: listStagedRoute },
  { name: 'approve', method: 'POST', path: `/api/admin/ingestion/staged/${id}/approve`, backend: `/products/admin/ingestion/staged/${id}/approve`, handler: stagedAction },
  { name: 'reject', method: 'POST', path: `/api/admin/ingestion/staged/${id}/reject`, backend: `/products/admin/ingestion/staged/${id}/reject`, handler: stagedAction },
  { name: 'publish', method: 'POST', path: `/api/admin/ingestion/staged/${id}/publish`, backend: `/products/admin/ingestion/staged/${id}/publish`, handler: stagedAction },
  { name: 'unpublish', method: 'POST', path: `/api/admin/ingestion/staged/${id}/unpublish`, backend: `/products/admin/ingestion/staged/${id}/unpublish`, handler: stagedAction },
  { name: 'archive', method: 'POST', path: `/api/admin/ingestion/staged/${id}/archive`, backend: `/products/admin/ingestion/staged/${id}/archive`, handler: stagedAction },
  { name: 'pkr suggestion', method: 'GET', path: `/api/admin/ingestion/staged/${id}/pkr-suggestion`, backend: `/products/admin/ingestion/staged/${id}/pkr-suggestion`, handler: pkrSuggestion },
  { name: 'uuid approve', method: 'POST', path: `/api/admin/ingestion/staged/${uuid}/approve`, backend: `/products/admin/ingestion/staged/${uuid}/approve`, handler: stagedAction },
  { name: 'uuid pkr suggestion', method: 'GET', path: `/api/admin/ingestion/staged/${uuid}/pkr-suggestion`, backend: `/products/admin/ingestion/staged/${uuid}/pkr-suggestion`, handler: pkrSuggestion },
  { name: 'get enrichment', method: 'GET', path: `/api/admin/ingestion/staged/${uuid}/enrichment`, backend: `/products/admin/ingestion/staged/${uuid}/enrichment`, handler: getEnrichment },
  { name: 'request enrichment', method: 'POST', path: `/api/admin/ingestion/staged/${uuid}/enrichment`, backend: `/products/admin/ingestion/staged/${uuid}/enrichment`, handler: postEnrichment },
  { name: 'cancel enrichment', method: 'POST', path: `/api/admin/ingestion/staged/${uuid}/enrichment/${suggestionId}/cancel`, backend: `/products/admin/ingestion/staged/${uuid}/enrichment/${suggestionId}/cancel`, handler: cancelEnrichmentRoute },
  { name: 'list jobs', method: 'GET', path: '/api/admin/ingestion/jobs', backend: '/products/admin/ingestion/jobs', handler: listJobs },
  { name: 'queue job', method: 'POST', path: '/api/admin/ingestion/jobs', backend: '/products/admin/ingestion/jobs', handler: createJob },
] as const;

const make = (route: (typeof routes)[number], cookie?: string, requestOrigin?: string) =>
  new Request(`${origin}${route.path}`, {
    method: route.method,
    headers: {
      ...(cookie ? { cookie: `${ADMIN_SESSION_COOKIE}=${cookie}` } : {}),
      ...(requestOrigin ? { origin: requestOrigin } : {}),
      ...(route.method === 'GET' ? {} : { 'content-type': 'application/json' }),
    },
    ...(route.method === 'GET' ? {} : { body: JSON.stringify({ fixture: true }) }),
  });

describe('ingestion admin proxy', () => {
  const oldUrl = process.env.NEXT_PUBLIC_API_URL;
  const fetchMock = vi.fn();

  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = 'https://backend.example.invalid';
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    if (oldUrl === undefined) delete process.env.NEXT_PUBLIC_API_URL;
    else process.env.NEXT_PUBLIC_API_URL = oldUrl;
    vi.unstubAllGlobals();
  });

  it.each(routes)('rejects anonymous and forged $name without calling the backend', async (route) => {
    expect((await route.handler(make(route, undefined, origin))).status).toBe(401);
    expect((await route.handler(make(route, 'forged', origin))).status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each(routes.filter((r) => r.method === 'POST'))('rejects cross-origin and origin-less $name', async (route) => {
    expect((await route.handler(make(route, TOKEN, 'https://other.example.invalid'))).status).toBe(403);
    expect((await route.handler(make(route, TOKEN))).status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each(routes)('forwards signed-in $name with only the session token and never returns it', async (route) => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'content-type': 'application/json' } }));
    const response = await route.handler(make(route, TOKEN, origin));
    expect(response.status).toBe(200);
    expect(fetchMock.mock.calls[0][0].toString()).toBe(`https://backend.example.invalid${route.backend}`);
    expect(fetchMock.mock.calls[0][1].method).toBe(route.method);
    expect(fetchMock.mock.calls[0][1].headers.get('X-Admin-Session')).toBe(TOKEN);
    expect(fetchMock.mock.calls[0][1].headers.get('X-Admin-Key')).toBeNull();
    expect(await response.text()).not.toContain(TOKEN);
  });

  it.each(['delete', 'publish-all', '..', 'approve%2f..%2f..'])('does not forward unknown action "%s"', async (action) => {
    const request = new Request(`${origin}/api/admin/ingestion/staged/${id}/${action}`, {
      method: 'POST',
      headers: { cookie: `${ADMIN_SESSION_COOKIE}=${TOKEN}`, origin },
    });
    expect((await stagedAction(request)).status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('does not forward a malformed staged id', async () => {
    const request = new Request(`${origin}/api/admin/ingestion/staged/not-an-id/publish`, {
      method: 'POST',
      headers: { cookie: `${ADMIN_SESSION_COOKIE}=${TOKEN}`, origin },
    });
    expect((await stagedAction(request)).status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([
    ['get', getEnrichment, 'GET', '/staged/not-an-id/enrichment'],
    ['get 24-hex', getEnrichment, 'GET', `/staged/${id}/enrichment`],
    ['request', postEnrichment, 'POST', '/staged/..%2f/enrichment'],
    ['cancel bad staged', cancelEnrichmentRoute, 'POST', `/staged/nope/enrichment/${suggestionId}/cancel`],
    ['cancel bad suggestion', cancelEnrichmentRoute, 'POST', `/staged/${uuid}/enrichment/${id}/cancel`],
  ])('does not forward malformed enrichment ids (%s)', async (_name, handler, method, path) => {
    const session = { token: TOKEN };
    const request = new Request(`${origin}/api/admin/ingestion${path}`, { method, headers: { cookie: `${ADMIN_SESSION_COOKIE}=${session.token}`, origin } });
    expect((await handler(request)).status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([404, 409, 502, 503])('relays enrichment backend %i unchanged', async (status) => {
    const session = { token: TOKEN };
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: `backend ${status}` }), { status, headers: { 'content-type': 'application/json' } }));
    const route = routes.find((r) => r.name === 'request enrichment')!;
    const response = await route.handler(make(route, session.token, origin));
    expect(response.status).toBe(status);
    expect((await response.json()).detail).toBe(`backend ${status}`);
  });

  it('relays backend state errors unchanged', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: 'Cannot publish a staged product that is pending_review' }), { status: 409, headers: { 'content-type': 'application/json' } }));
    const publish = routes.find((r) => r.name === 'publish')!;
    const response = await publish.handler(make(publish, TOKEN, origin));
    expect(response.status).toBe(409);
    expect((await response.json()).detail).toContain('pending_review');
  });
});
