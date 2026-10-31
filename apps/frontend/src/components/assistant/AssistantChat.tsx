'use client';

import { useRef, useState, useSyncExternalStore } from 'react';
import Link from 'next/link';
import { useCart } from '@/components/cart/CartProvider';
import { confirmAction, resolveLines } from '@/lib/assistant-actions';
import { buildCartCheckoutUrl, createCartItem } from '@/lib/cart';
import { memoryApi, type MemoryApiError } from '@/lib/memory';
import { initialState, reduce, streamAssistant, type AssistantEvent, type ChatState } from '@/lib/assistant-stream';

const ERROR_TEXT: Record<string, string> = {
  cancelled: 'Stopped.',
  provider_error: 'The assistant had a problem. Please try again.',
  provider_malformed: 'The assistant sent an unreadable reply. Please try again.',
  provider_overrun: 'The reply was too long and was cut off.',
  unavailable: 'The assistant is unavailable right now.',
};
const REJECTED_TEXT = 'This suggestion was not accepted, so nothing was done.';

const WHATSAPP_NUMBER = process.env.NEXT_PUBLIC_WHATSAPP_NUMBER || '';
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || '';
type Proposal = Extract<AssistantEvent, { type: 'proposal' }>;
type Result = { kind: 'done'; text: string; url?: string } | { kind: 'failed'; text: string } | null;
const LABEL: Record<string, string> = { add_to_cart: 'Confirm: add to cart', start_whatsapp_enquiry: 'Confirm: start WhatsApp enquiry' };

// The only thing in the chat that can act, and only when a person presses it. Each press re-checks on the server and again
// against the current catalogue; the proposal's idempotency key makes a double press (or a retry after a lost reply) harmless.
function ConfirmAction({ item, sessionId, summary }: { item: Proposal; sessionId: string; summary: string }) {
  const { addItem } = useCart();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result>(null);
  const lock = useRef(false);
  const params = item.params!;
  const rows = (item.action_type === 'add_to_cart' ? [params] : (params.items as Record<string, unknown>[])) ?? [];

  async function confirm() {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    let ok = false;
    const fail = (text: string) => setResult({ kind: 'failed', text });
    const out = await confirmAction({ session_id: sessionId, idempotency_key: item.idempotency_key!, action_type: item.action_type, params });
    const lines = out.ok ? await resolveLines(out.items, rows.map((r) => Number(r.expected_unit_price))) : null;
    if (!out.ok) fail(out.message);
    else if (!lines) fail('This item changed, so nothing was done. Please ask again to get an up-to-date suggestion.');
    else if (item.action_type === 'add_to_cart') {
      lines.forEach((l) => addItem(l.product, l.variant, l.quantity));
      ok = true;
      setResult({ kind: 'done', text: 'Added to your cart.' });
    } else {
      let url: string | undefined;
      try { url = buildCartCheckoutUrl(lines.map((l) => createCartItem(l.product, l.variant, l.quantity)!), WHATSAPP_NUMBER, { siteUrl: SITE_URL, reference: out.reference! }); } catch { /* not configured */ }
      ok = true;
      setResult({ kind: 'done', text: `Your enquiry reference is ${out.reference}.${url ? '' : ' WhatsApp is not set up here; please quote this reference when you contact us.'}`, url });
    }
    lock.current = ok; // stays locked after success; a failure can be retried with the same key
    setBusy(false);
  }

  return (
    <div data-testid="confirm-action" className="rounded border p-2 text-sm">
      <p>{summary}</p>
      {result?.kind !== 'done' && <button type="button" onClick={confirm} disabled={busy}>{busy ? 'Working…' : LABEL[item.action_type]}</button>}
      {result?.kind === 'failed' && <p role="alert" data-testid="action-failed">{result.text}</p>}
      {result?.kind === 'done' && <p role="status" data-testid="action-done">{result.text}</p>}
      {result?.kind === 'done' && item.action_type === 'add_to_cart' && <Link href="/cart">View cart</Link>}
      {result?.kind === 'done' && result.url && <a data-testid="whatsapp-handoff" href={result.url} target="_blank" rel="noopener noreferrer">Open WhatsApp to send your enquiry</a>}
    </div>
  );
}

const MEMORY_LABEL: Record<string, string> = { favourite_colour: 'favourite colour', budget_max_pkr: 'budget (PKR, at most)' };

// A question, not an action: nothing is saved until the customer presses Save, and the memory API re-applies consent and validation.
function RememberCard({ item }: { item: Extract<AssistantEvent, { type: 'memory_suggestion' }> }) {
  const [state, setState] = useState<{ kind: 'ask' | 'saving' | 'saved' | 'dismissed' | 'problem'; text?: string; link?: string }>({ kind: 'ask' });
  async function save() {
    setState({ kind: 'saving' });
    try {
      await memoryApi.create({ category: 'preference', key: item.key, value: item.value, reason: 'Saved from assistant chat', source: 'user_explicit', source_ref: 'assistant' });
      setState({ kind: 'saved' });
    } catch (caught) {
      const failure = caught as MemoryApiError;
      setState(failure.status === 401 ? { kind: 'problem', text: 'Please sign in first.', link: '/account' }
        : failure.reason === 'consent_required' ? { kind: 'problem', text: 'Memory is off. Turn it on first.', link: '/memory' }
        : failure.reason === 'duplicate_key' ? { kind: 'problem', text: 'You already saved something with that name. Change it on the memory page.', link: '/memory' }
        : { kind: 'problem', text: 'Could not save that. Please try again.' });
    }
  }
  if (state.kind === 'dismissed') return null;
  return (
    <div data-testid="remember-card" className="rounded border p-2 text-sm">
      <p>Remember your {MEMORY_LABEL[item.key]}: <strong>{item.value}</strong>?</p>
      {state.kind === 'saved' ? <p role="status">Saved. You can review it on the <Link href="/memory" className="underline">memory page</Link>.</p> : (
        <div className="flex gap-2">
          <button type="button" onClick={save} disabled={state.kind === 'saving'}>{state.kind === 'saving' ? 'Saving…' : 'Save'}</button>
          <button type="button" onClick={() => setState({ kind: 'dismissed' })}>No thanks</button>
        </div>
      )}
      {state.kind === 'problem' && <p role="alert">{state.text} {state.link && <Link href={state.link} className="underline">Open</Link>}</p>}
    </div>
  );
}

// Renders server output as plain text only (React escapes it); a proposal only becomes a control through ConfirmAction.
export function AssistantView({ state }: { state: ChatState }) {
  const names = new Map(state.items.flatMap((i) => (i.type === 'product' ? [[i.product.product_id, i.product.name] as const] : [])));
  const summarise = (p: Proposal) => {
    const rows = p.action_type === 'add_to_cart' ? [p.params!] : ((p.params!.items as Record<string, unknown>[]) ?? []);
    const what = rows.map((r) => `${names.get(String(r.product_id)) ?? 'item'} × ${String(r.quantity)} (${String(r.currency)} ${String(r.expected_unit_price)} each)`).join(', ');
    return p.action_type === 'add_to_cart' ? `Add ${what} to your cart?` : `Start a WhatsApp enquiry for ${what}? Nothing is sent until you open WhatsApp and press send.`;
  };
  return (
    <div aria-live="polite" className="space-y-2">
      {state.items.map((item: AssistantEvent) =>
        item.type === 'text' ? <span key={item.seq}>{item.delta}</span>
        : item.type === 'product' ? (
          <div key={item.seq} data-testid="product" className="rounded border p-2">
            <strong>{item.product.name}</strong>
            {item.product.price !== null && <span> {item.product.currency} {item.product.price}</span>}
          </div>
        ) : item.type === 'memory_suggestion' ? <RememberCard key={item.seq} item={item} />
        : item.type === 'proposal' ? (
          <div key={item.seq}>
            <p data-testid="proposal" data-outcome={item.decision.outcome} className="text-sm">
              {item.decision.outcome === 'validated' ? 'Suggested (nothing has been done yet).' : REJECTED_TEXT}
            </p>
            {item.params && item.decision.outcome === 'validated' && state.meta && <ConfirmAction item={item} sessionId={state.meta.session_id} summary={summarise(item)} />}
          </div>
        ) : null,
      )}
      {state.status === 'error' && <p role="alert">{ERROR_TEXT[state.error ?? ''] ?? 'Something went wrong. Please try again.'}</p>}
    </div>
  );
}

type Recognizer = { lang: string; interimResults: boolean; onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null; onend: (() => void) | null; onerror: (() => void) | null; start: () => void; stop: () => void };
const speechApi = (): (new () => Recognizer) | undefined =>
  typeof window === 'undefined' ? undefined : (window as unknown as Record<string, new () => Recognizer>).SpeechRecognition || (window as unknown as Record<string, new () => Recognizer>).webkitSpeechRecognition;

const newId = (prefix: string) => `${prefix}${crypto.randomUUID().replace(/-/g, '')}`;

export function AssistantChat({ context = {} }: { context?: Record<string, string> }) {
  const [state, setState] = useState<ChatState>(initialState());
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const session = useRef(newId('sess_'));
  const viaVoice = useRef(false);
  const [listening, setListening] = useState(false);
  const Speech = useSyncExternalStore(() => () => {}, speechApi, () => undefined); // undefined on the server, so hydration matches

  // The transcript only fills the box: the customer reads it, can fix it, and presses Send. Typing clears the voice flag.
  function listen() {
    if (!Speech || listening) return;
    const recognizer = new Speech();
    recognizer.lang = 'en-PK';
    recognizer.interimResults = false;
    recognizer.onresult = (e) => { viaVoice.current = true; setMessage(e.results[0][0].transcript.slice(0, 500)); };
    recognizer.onend = recognizer.onerror = () => setListening(false);
    setListening(true);
    recognizer.start();
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!message.trim() || abort.current) return;
    const controller = new AbortController();
    abort.current = controller;
    setBusy(true);
    let current = initialState();
    setState(current);
    const req = { session_id: session.current, idempotency_key: newId('idem_'), context: viaVoice.current ? { ...context, input: 'voice' } : context, message: message.trim() };
    for await (const event of streamAssistant(req, controller.signal)) {
      current = reduce(current, event);
      setState(current);
    }
    abort.current = null;
    setBusy(false);
  }

  return (
    <form onSubmit={send} className="space-y-3">
      <input value={message} onChange={(e) => { viaVoice.current = false; setMessage(e.target.value); }} maxLength={500} aria-label="Message" className="w-full rounded border p-2" />
      <button type="submit" disabled={busy}>Send</button>
      {Speech && <button type="button" onClick={listen} disabled={listening || busy} aria-label="Speak your request">{listening ? 'Listening…' : 'Speak'}</button>}
      {Speech && <p className="text-xs text-muted-foreground">Speaking uses your browser&apos;s speech service. You can always type instead.</p>}
      <button type="button" onClick={() => abort.current?.abort()}>Stop</button>
      <AssistantView state={state} />
    </form>
  );
}
