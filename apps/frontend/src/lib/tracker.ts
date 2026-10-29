import { traceHeaders } from './trace';

// Anonymous interaction tracker. It must never block or break rendering: every public function
// swallows errors, honours Do Not Track / Global Privacy Control, and drops events rather than retry.

export type TrackedEventType = 'view' | 'search' | 'impression' | 'click' | 'add_to_cart';
type Scalar = string | number | boolean | null;
export interface TrackedEvent { type: TrackedEventType; payload?: Record<string, Scalar> }

export const MAX_BATCH = 20;
export const MAX_QUEUE = 100;
const FLUSH_DELAY_MS = 3000;
const ENDPOINT = '/api/events';

let queue: TrackedEvent[] = [];
let timer: ReturnType<typeof setTimeout> | undefined;

export const trackingAllowed = (): boolean => {
  try {
    const nav = (globalThis as unknown as { navigator?: Record<string, unknown> }).navigator;
    const win = globalThis as { doNotTrack?: unknown };
    if (!nav) return false; // server render or non-browser: nothing to track
    return !(nav.doNotTrack === '1' || nav.doNotTrack === 'yes' || win.doNotTrack === '1' || nav.msDoNotTrack === '1' || nav.globalPrivacyControl === true);
  } catch {
    return false;
  }
};

const clean = (payload: Record<string, Scalar> = {}): Record<string, Scalar> =>
  Object.fromEntries(
    Object.entries(payload).slice(0, 10).map(([key, value]) => [key.slice(0, 40), typeof value === 'string' ? value.slice(0, 200) : value]),
  );

export const flush = (): void => {
  try {
    if (timer) clearTimeout(timer);
    timer = undefined;
    const events = queue.splice(0, MAX_BATCH);
    if (queue.length) timer = setTimeout(flush, FLUSH_DELAY_MS);
    if (!events.length || !trackingAllowed()) return;
    const body = JSON.stringify({ events });
    const beacon = (globalThis as unknown as { navigator?: { sendBeacon?: (url: string, data: Blob) => boolean } }).navigator?.sendBeacon;
    if (document.visibilityState === 'hidden' && beacon) {
      beacon.call(navigator, ENDPOINT, new Blob([body], { type: 'application/json' }));
      return;
    }
    void fetch(ENDPOINT, { method: 'POST', headers: { 'content-type': 'application/json', ...traceHeaders() }, body, keepalive: true, credentials: 'same-origin' }).catch(() => undefined);
  } catch {
    queue = [];
  }
};

export const track = (event: TrackedEvent): void => {
  try {
    if (!trackingAllowed()) return;
    if (queue.length >= MAX_QUEUE) queue.shift(); // bounded memory: oldest event is dropped
    queue.push({ type: event.type, payload: clean(event.payload) });
    if (queue.length >= MAX_BATCH) flush();
    else if (!timer) timer = setTimeout(flush, FLUSH_DELAY_MS);
  } catch {
    // tracking is best effort
  }
};

export const installFlushOnHide = (): (() => void) => {
  const onHide = () => { if (document.visibilityState === 'hidden') flush(); };
  document.addEventListener('visibilitychange', onHide);
  return () => document.removeEventListener('visibilitychange', onHide);
};

export const __resetTrackerForTests = () => { queue = []; if (timer) clearTimeout(timer); timer = undefined; };
