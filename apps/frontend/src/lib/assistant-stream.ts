// M3-S2 client for POST /v1/assistant/stream (via the same-origin proxy). Server output is untrusted: frames, ordering and
// every action proposal are re-checked here (mirroring the backend action kernel's allowlist), and nothing is executed here (M3-S3: only a user-confirmed call in assistant-actions.ts does that).
export const ACTIONS = ['show_product', 'add_to_cart', 'start_whatsapp_enquiry'] as const;
export const EXECUTABLE: readonly string[] = ['add_to_cart', 'start_whatsapp_enquiry'];
export const REASONS = [
  'ok', 'invalid_proposal', 'missing_context', 'unknown_action', 'permission_denied', 'invalid_idempotency_key', 'invalid_params',
  'invalid_quantity', 'invalid_currency', 'idempotency_conflict', 'product_not_found', 'product_unavailable', 'stale_revision',
  'variant_not_found', 'variant_unavailable', 'currency_mismatch', 'stale_price', 'out_of_stock', 'insufficient_stock', 'invalid_state',
] as const;
export const ERRORS = ['provider_error', 'provider_malformed', 'provider_overrun', 'invalid_stream', 'stream_interrupted', 'cancelled', 'unavailable'] as const;
export const MAX_FRAME_BYTES = 16_384;
const KEY = /^idem_[A-Za-z0-9_-]{16,64}$/;
const SESSION = /^[A-Za-z0-9_.:-]{1,128}$/;
export const PROTOCOL_VERSION = 1;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

export type Meta = { session_id: string; idempotency_key: string; context: Record<string, string | number | boolean | null> };
export type Decision = { outcome: 'validated' | 'rejected'; reason: (typeof REASONS)[number]; replayed: boolean };
export type AssistantEvent =
  | { seq: number; type: 'start'; meta: Meta }
  | { seq: number; type: 'text'; delta: string }
  | { seq: number; type: 'product'; product: { product_id: string; name: string; price: number | null; currency: string | null } }
  | { seq: number; type: 'proposal'; action_type: string; idempotency_key: string | null; decision: Decision; params?: Record<string, unknown> }
  | { seq: number; type: 'done' }
  | { seq: number; type: 'error'; code: (typeof ERRORS)[number] };

const rec = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const oneOf = <T extends readonly string[]>(list: T, v: unknown): v is T[number] => typeof v === 'string' && (list as readonly string[]).includes(v);

// Backend contract: at most 10 keys (<= 40 chars), values are str (<= 200 chars) | integer | bool | null.
const validContext = (c: unknown): c is Meta['context'] =>
  rec(c) && Object.entries(c).length <= 10 && Object.entries(c).every(([k, v]) => k.length <= 40 &&
    (v === null || typeof v === 'boolean' || Number.isInteger(v) || (typeof v === 'string' && v.length <= 200)));

// Splits a growing buffer into complete `\n\n`-terminated frames; returns the unfinished remainder.
export function splitFrames(buffer: string): { frames: string[]; rest: string } {
  const parts = buffer.split('\n\n');
  return { frames: parts.slice(0, -1), rest: parts[parts.length - 1] };
}

// One frame -> a validated event, or null when the frame is malformed (the caller ends the stream as invalid_stream).
export function parseFrame(frame: string, expected: Pick<Meta, 'session_id'> | null): AssistantEvent | null {
  if (frame.length > MAX_FRAME_BYTES) return null;
  const lines = frame.split('\n');
  if (lines.length !== 3 || !lines[0].startsWith('id: ') || !lines[1].startsWith('event: ') || !lines[2].startsWith('data: ')) return null;
  const seq = Number(lines[0].slice(4));
  const type = lines[1].slice(7);
  let d: unknown;
  try { d = JSON.parse(lines[2].slice(6)); } catch { return null; }
  if (!Number.isInteger(seq) || seq < 0 || !rec(d)) return null;
  switch (type) {
    case 'start': {
      const { session_id, idempotency_key, context } = d;
      if (d.protocol !== PROTOCOL_VERSION || typeof session_id !== 'string' || !SESSION.test(session_id)) return null;
      if (typeof idempotency_key !== 'string' || !KEY.test(idempotency_key) || !validContext(context)) return null;
      return { seq, type, meta: { session_id, idempotency_key, context: context as Meta['context'] } };
    }
    case 'text':
      return typeof d.delta === 'string' && d.delta ? { seq, type, delta: d.delta } : null;
    case 'product':
      return typeof d.product_id === 'string' && UUID.test(d.product_id) && typeof d.name === 'string'
        ? { seq, type, product: { product_id: d.product_id, name: d.name, price: typeof d.price === 'number' ? d.price : null, currency: typeof d.currency === 'string' ? d.currency : null } }
        : null;
    case 'proposal': {
      const dec = d.decision;
      if (!rec(dec) || !oneOf(REASONS, dec.reason) || (dec.outcome !== 'validated' && dec.outcome !== 'rejected')) return null;
      if (d.session_id !== expected?.session_id || dec.executed !== false) return null;
      const known = oneOf(ACTIONS, d.action_type);
      const key = typeof d.idempotency_key === 'string' && KEY.test(d.idempotency_key) ? d.idempotency_key : null;
      // Second line of defence: a "validated" decision is only believed for an allowlisted action with a well-formed, matching key.
      const ok = dec.outcome === 'validated' && dec.reason === 'ok' && known && key !== null && dec.idempotency_key === key;
      const decision: Decision = ok ? { outcome: 'validated', reason: 'ok', replayed: dec.replayed === true }
        : { outcome: 'rejected', reason: dec.outcome === 'rejected' ? dec.reason : 'invalid_proposal', replayed: false };
      // M3-S3: params are kept only for a believed, executable proposal; they are shown for confirmation and re-checked by the server.
      const params = ok && EXECUTABLE.includes(d.action_type as string) && rec(d.params) ? d.params : undefined;
      return { seq, type, action_type: known ? (d.action_type as string) : 'unknown', idempotency_key: key, decision, ...(params && { params }) };
    }
    case 'done':
      return { seq, type };
    case 'error':
      return { seq, type, code: oneOf(ERRORS, d.code) ? d.code : 'invalid_stream' };
    default:
      return null;
  }
}

export type ChatState = { meta: Meta | null; items: AssistantEvent[]; status: 'streaming' | 'done' | 'error'; error?: (typeof ERRORS)[number]; next: number };
export const initialState = (): ChatState => ({ meta: null, items: [], status: 'streaming', next: 0 });

// Enforces ordering: seq is contiguous from 0, `start` first and only once, nothing after a terminal event.
export function reduce(state: ChatState, event: AssistantEvent): ChatState {
  if (state.status !== 'streaming') return state;
  const fail = (code: (typeof ERRORS)[number]): ChatState => ({ ...state, status: 'error', error: code });
  if (event.seq === -1 && event.type === 'error') return { ...state, status: 'error', error: event.code }; // local, not server order
  if (event.seq !== state.next || (event.type === 'start') !== (state.next === 0)) return fail('invalid_stream');
  const next = state.next + 1;
  switch (event.type) {
    case 'start': return { ...state, meta: event.meta, next };
    case 'done': return { ...state, status: 'done', next };
    case 'error': return { ...state, status: 'error', error: event.code, next };
    default: return { ...state, items: [...state.items, event], next };
  }
}

// Folds a response body into events; an abort (user cancel) yields `cancelled`, a body that ends early `stream_interrupted`.
export async function* readEvents(body: ReadableStream<Uint8Array>, expected: Meta, signal?: AbortSignal): AsyncGenerator<AssistantEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let terminal = false;
  const onAbort = () => void reader.cancel().catch(() => {});
  signal?.addEventListener('abort', onAbort);
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const { frames, rest } = splitFrames(buffer);
      buffer = rest;
      if (buffer.length > MAX_FRAME_BYTES) { yield { seq: -1, type: 'error', code: 'invalid_stream' }; return; }
      for (const frame of frames) {
        const event = parseFrame(frame, expected);
        if (!event) { yield { seq: -1, type: 'error', code: 'invalid_stream' }; return; }
        if (event.type === 'start' && (event.meta.session_id !== expected.session_id || event.meta.idempotency_key !== expected.idempotency_key)) {
          yield { seq: -1, type: 'error', code: 'invalid_stream' }; // metadata must round-trip unchanged
          return;
        }
        yield event;
        if (event.type === 'done' || event.type === 'error') { terminal = true; return; }
      }
    }
    if (!terminal) yield { seq: -1, type: 'error', code: signal?.aborted ? 'cancelled' : 'stream_interrupted' };
  } catch {
    yield { seq: -1, type: 'error', code: signal?.aborted ? 'cancelled' : 'stream_interrupted' };
  } finally {
    signal?.removeEventListener('abort', onAbort);
    await reader.cancel().catch(() => {});
  }
}

// Opens the stream. Locally generated errors (seq -1) are terminal and never trusted as server order.
export async function* streamAssistant(req: Meta & { message: string }, signal?: AbortSignal, fetchImpl: typeof fetch = fetch): AsyncGenerator<AssistantEvent> {
  let response: Response;
  try {
    response = await fetchImpl('/api/assistant/stream', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(req), signal });
  } catch {
    yield { seq: -1, type: 'error', code: signal?.aborted ? 'cancelled' : 'unavailable' };
    return;
  }
  if (!response.ok || !response.body || !response.headers.get('content-type')?.startsWith('text/event-stream')) {
    yield { seq: -1, type: 'error', code: 'unavailable' };
    return;
  }
  yield* readEvents(response.body, req, signal);
}
