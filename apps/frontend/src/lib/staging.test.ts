import { readFileSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  STAGED_STATUSES,
  StagingApiError,
  availableActions,
  describeMissing,
  formatSourcePrice,
  listStaged,
  runStagedAction,
} from './staging';

afterEach(() => vi.unstubAllGlobals());

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

describe('review action rules', () => {
  it.each([
    ['pending_review', ['approve', 'reject']],
    ['approved', ['publish', 'archive']],
    ['published', ['unpublish', 'archive']],
    ['unpublished', ['publish', 'archive']],
    ['rejected', ['archive']],
    ['archived', []],
  ] as const)('%s offers %j', (status, expected) => {
    expect(availableActions(status)).toEqual(expected);
  });

  it('only offers publish after approval', () => {
    for (const status of STAGED_STATUSES) {
      if (availableActions(status).includes('publish')) {
        expect(['approved', 'unpublished']).toContain(status);
      }
    }
    expect(availableActions('pending_review')).not.toContain('publish');
    expect(availableActions('rejected')).not.toContain('publish');
  });
});

describe('formatting', () => {
  it('never guesses a currency or converts the source price', () => {
    expect(formatSourcePrice(189, 'AUD')).toBe('189.00 AUD');
    expect(formatSourcePrice(189, null)).toBe('189.00 (currency unknown)');
    expect(formatSourcePrice(null, null)).toBe('Not provided');
  });

  it('explains missing fields and passes unknown ones through', () => {
    expect(describeMissing('price')).toContain('PKR');
    expect(describeMissing('mystery')).toBe('mystery');
  });
});

describe('staging client', () => {
  it('lists with an optional status filter through the admin proxy only', async () => {
    const fetchMock = vi.fn().mockImplementation(async () => json({ items: [] }));
    vi.stubGlobal('fetch', fetchMock);
    await listStaged('pending_review');
    await listStaged('all');
    expect(fetchMock.mock.calls[0][0]).toBe('/api/admin/ingestion/staged?status=pending_review');
    expect(fetchMock.mock.calls[1][0]).toBe('/api/admin/ingestion/staged');
  });

  it('posts actions with a JSON body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({ _id: 'x' }));
    vi.stubGlobal('fetch', fetchMock);
    await runStagedAction('abc', 'approve', { price: 4500, stock: 2 });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/admin/ingestion/staged/abc/approve');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ price: 4500, stock: 2 });
  });

  it.each([
    ['backend detail', json({ detail: 'Cannot publish a staged product that is pending_review' }, 409), 'Cannot publish a staged product that is pending_review', 409],
    ['validation list', json({ detail: [{ msg: 'Field required' }] }, 422), 'Field required', 422],
    ['unauthenticated', json({ detail: 'Administrative authentication is required.' }, 401), 'Administrative authentication is required.', 401],
    ['non-JSON failure', new Response('<html>', { status: 502 }), 'Request failed (502)', 502],
  ])('surfaces %s', async (_label, response, message, status) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
    await expect(runStagedAction('abc', 'publish')).rejects.toMatchObject({ message, status });
  });

  it('reports network failure without leaking details', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('connect ECONNREFUSED 10.0.0.1')));
    const error = await listStaged().catch((e) => e);
    expect(error).toBeInstanceOf(StagingApiError);
    expect(error.message).toBe('Could not reach the server.');
  });
});

describe('public storefront isolation', () => {
  const walk = (dir: string): string[] =>
    readdirSync(dir).flatMap((name) => {
      const full = path.join(dir, name);
      return statSync(full).isDirectory() ? walk(full) : [full];
    });
  const root = path.resolve(__dirname, '..');

  it('storefront code never reads staged products or the ingestion API', () => {
    const publicFiles = [
      path.join(root, 'lib/api.ts'),
      path.join(root, 'lib/catalog.ts'),
      ...walk(path.join(root, 'app/products')),
      ...walk(path.join(root, 'app/product')),
      path.join(root, 'app/page.tsx'),
      path.join(root, 'app/sitemap.ts'),
    ];
    for (const file of publicFiles) {
      const source = readFileSync(file, 'utf8');
      expect(source, file).not.toMatch(/ingestion|staged|\/products\/admin/);
    }
  });
});
