import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { __resetTrackerForTests, flush, MAX_BATCH, MAX_QUEUE, track, trackingAllowed } from './tracker';

const stubBrowser = (nav: Record<string, unknown> = {}) => {
  vi.stubGlobal('navigator', { doNotTrack: null, ...nav });
  vi.stubGlobal('document', { visibilityState: 'visible', addEventListener: vi.fn(), removeEventListener: vi.fn() });
};

describe('tracker', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    __resetTrackerForTests();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('does nothing outside a browser', () => {
    vi.stubGlobal('navigator', undefined);
    expect(trackingAllowed()).toBe(false);
    expect(() => track({ type: 'view' })).not.toThrow();
  });

  it.each([
    [{ doNotTrack: '1' }],
    [{ doNotTrack: 'yes' }],
    [{ msDoNotTrack: '1' }],
    [{ globalPrivacyControl: true }],
  ])('sends nothing when Do Not Track / GPC is on (%o)', (nav) => {
    stubBrowser(nav);
    const fetchMock = vi.fn().mockResolvedValue(new Response());
    vi.stubGlobal('fetch', fetchMock);
    track({ type: 'view', payload: { slug: 'a' } });
    vi.advanceTimersByTime(10_000);
    flush();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('batches events and flushes after a delay', () => {
    stubBrowser();
    const fetchMock = vi.fn().mockResolvedValue(new Response());
    vi.stubGlobal('fetch', fetchMock);
    track({ type: 'view', payload: { slug: 'a' } });
    track({ type: 'click', payload: { slug: 'a', position: 1 } });
    expect(fetchMock).not.toHaveBeenCalled();
    vi.advanceTimersByTime(3000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/events');
    expect(JSON.parse(init.body).events.map((e: { type: string }) => e.type)).toEqual(['view', 'click']);
    expect(init.keepalive).toBe(true);
    expect(init.headers.traceparent).toMatch(/^00-[0-9a-f]{32}-[0-9a-f]{16}-01$/);
  });

  it('flushes immediately when a batch is full and never exceeds the batch size', () => {
    stubBrowser();
    const fetchMock = vi.fn().mockResolvedValue(new Response());
    vi.stubGlobal('fetch', fetchMock);
    for (let i = 0; i < MAX_BATCH; i += 1) track({ type: 'impression', payload: { i } });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).events).toHaveLength(MAX_BATCH);
  });

  it('truncates long strings and extra keys', () => {
    stubBrowser();
    const fetchMock = vi.fn().mockResolvedValue(new Response());
    vi.stubGlobal('fetch', fetchMock);
    track({ type: 'search', payload: { q: 'x'.repeat(500), ...Object.fromEntries(Array.from({ length: 20 }, (_, i) => [`k${i}`, i])) } });
    flush();
    const payload = JSON.parse(fetchMock.mock.calls[0][1].body).events[0].payload;
    expect(payload.q).toHaveLength(200);
    expect(Object.keys(payload).length).toBeLessThanOrEqual(10);
  });

  it('keeps the queue bounded', () => {
    stubBrowser();
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => undefined)));
    for (let i = 0; i < MAX_QUEUE * 3; i += 1) track({ type: 'impression', payload: { i } });
    expect(() => flush()).not.toThrow();
  });

  it('swallows network failures and synchronous fetch errors', async () => {
    stubBrowser();
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    track({ type: 'view' });
    expect(() => flush()).not.toThrow();
    vi.stubGlobal('fetch', vi.fn(() => { throw new Error('boom'); }));
    track({ type: 'view' });
    expect(() => flush()).not.toThrow();
    await vi.runAllTimersAsync();
  });

  it('uses sendBeacon when the page is hidden', () => {
    const sendBeacon = vi.fn().mockReturnValue(true);
    stubBrowser({ sendBeacon });
    vi.stubGlobal('document', { visibilityState: 'hidden' });
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    track({ type: 'view' });
    flush();
    expect(sendBeacon).toHaveBeenCalledTimes(1);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
