'use client';

import Image from 'next/image';
import Link from 'next/link';
import { FormEvent, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { Check, Mic, Plus, Send, Sparkles, Square, SquarePen, X } from 'lucide-react';
import { MarkdownText } from '@/components/common/MarkdownText';
import { initialState, reduce, streamAssistant, type AssistantEvent, type ChatState } from '@/lib/assistant-stream';
import { SUGGESTED_PROMPTS } from '@/lib/assistant/ui';
import { memoryApi, type MemoryApiError } from '@/lib/memory';
import { useConfirmedAction, type Proposal } from './useConfirmedAction';

type ProductEvent = Extract<AssistantEvent, { type: 'product' }>['product'];
type Suggestion = Extract<AssistantEvent, { type: 'memory_suggestion' }>;

const ERROR_TEXT: Record<string, string> = {
  cancelled: 'Stopped.',
  provider_error: 'The assistant had a problem. Please try again.',
  provider_malformed: 'The assistant sent an unreadable reply. Please try again.',
  provider_overrun: 'The reply was too long and was cut off.',
  unavailable: 'The assistant is unavailable right now.',
};
const REJECTED_TEXT = 'This suggestion was not accepted, so nothing was done.';
const MEMORY_LABEL: Record<string, string> = { favourite_colour: 'favourite colour', budget_max_pkr: 'budget (PKR, at most)', preferred_category: 'preferred category' };
const FOCUS = 'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#9a6b3f]';
const PRIMARY = `rounded-full bg-[#2f241f] px-3 py-1.5 text-xs font-medium text-white disabled:opacity-60 ${FOCUS}`;
const OUTLINE = `rounded-full border border-[#c9a577] px-3 py-1.5 text-xs text-[#2f241f] ${FOCUS}`;
const money = (currency: string | null, price: number | null) => (price === null ? '' : `${currency ?? 'PKR'} ${price}`);

// A product the assistant found. Its button is the server-checked add-to-cart suggestion for exactly this product: pressing "Yes, add"
// re-validates price and stock on the server, then again against the live product, before the cart is touched.
function ProductCard({ product, proposal, sessionId }: { product: ProductEvent; proposal?: Proposal; sessionId: string }) {
  const [confirming, setConfirming] = useState(false);
  const { busy, result, confirm } = useConfirmedAction(proposal ?? ({} as Proposal), sessionId);
  const params = proposal?.params;
  const price = params ? Number(params.expected_unit_price) : product.price;
  const detail = [product.color, money(product.currency, price)].filter(Boolean).join(' · ');
  const done = result?.kind === 'done';
  return (
    <li className="flex gap-3 rounded-xl border border-[#e5d4bf] bg-white p-3" data-testid="assistant-product-card">
      {product.image ? <Image src={product.image} alt={product.name} width={64} height={80} className="h-20 w-16 shrink-0 rounded-lg object-cover" unoptimized /> : null}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-[#2f241f]" dir="auto" data-testid="product">{product.name}</p>
        <p className="text-xs text-[#6f5a4c]">{detail || ' '}</p>
        {proposal && confirming && !done ? (
          <div role="group" aria-label={`Confirm adding ${product.name}`} className="mt-2 space-y-2">
            <p className="text-xs text-[#3b302a]">Add 1 × {product.name}{product.color ? ` (${product.color})` : ''} to your cart?</p>
            <div className="flex gap-2">
              <button type="button" disabled={busy} onClick={() => { setConfirming(false); void confirm(); }} className={PRIMARY}>Yes, add</button>
              <button type="button" onClick={() => setConfirming(false)} className={OUTLINE}>Cancel</button>
            </div>
          </div>
        ) : (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {product.slug ? <Link href={`/product/${product.slug}`} className={OUTLINE}>View product</Link> : null}
            {done ? (
              <>
                <span className="inline-flex items-center gap-1 px-1 py-1.5 text-xs text-[#2f241f]" role="status" data-testid="action-done"><Check className="size-3" aria-hidden /> {result.text}</span>
                <Link href="/cart" className={PRIMARY}>Go to cart</Link>
              </>
            ) : proposal ? (
              <button type="button" disabled={busy} onClick={() => setConfirming(true)} className={`inline-flex items-center gap-1 ${PRIMARY}`}><Plus className="size-3" aria-hidden /> {busy ? 'Adding…' : 'Add to cart'}</button>
            ) : <span className="text-xs text-[#6f5a4c]">Not available to add right now</span>}
          </div>
        )}
        {result?.kind === 'failed' ? <p role="alert" data-testid="action-failed" className="mt-2 text-xs text-red-900">{result.text}</p> : null}
      </div>
    </li>
  );
}

// Any other validated suggestion (for example a WhatsApp enquiry): inert until the person presses the confirm button.
function ConfirmBlock({ item, sessionId, summary }: { item: Proposal; sessionId: string; summary: string }) {
  const { busy, result, confirm } = useConfirmedAction(item, sessionId);
  const label = item.action_type === 'add_to_cart' ? 'Confirm: add to cart' : 'Confirm: start WhatsApp enquiry';
  return (
    <div data-testid="confirm-action" className="space-y-2 rounded-xl border border-[#e5d4bf] bg-white p-3 text-sm">
      <p>{summary}</p>
      {result?.kind !== 'done' && <button type="button" onClick={() => void confirm()} disabled={busy} className={PRIMARY}>{busy ? 'Working…' : label}</button>}
      {result?.kind === 'failed' && <p role="alert" data-testid="action-failed" className="text-xs text-red-900">{result.text}</p>}
      {result?.kind === 'done' && <p role="status" data-testid="action-done" className="text-xs">{result.text}</p>}
      {result?.kind === 'done' && item.action_type === 'add_to_cart' && <Link href="/cart" className={PRIMARY}>Go to cart</Link>}
      {result?.kind === 'done' && result.url && <a data-testid="whatsapp-handoff" href={result.url} target="_blank" rel="noopener noreferrer" className={`inline-block ${PRIMARY}`}>Open WhatsApp to send your enquiry</a>}
    </div>
  );
}

// A question, not an action: nothing is saved until the customer presses Save, and the memory API re-applies consent and validation.
function RememberCard({ item }: { item: Suggestion }) {
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
    <div data-testid="remember-card" className="space-y-2 rounded-xl border border-dashed border-[#c9a577] bg-[#f3e9dc] p-3 text-sm">
      <p>Remember your {MEMORY_LABEL[item.key]}: <strong dir="auto">{item.value}</strong>?</p>
      {state.kind === 'saved' ? <p role="status" className="text-xs">Saved. You can review it on the <Link href="/memory" className="underline">memory page</Link>.</p> : (
        <div className="flex gap-2">
          <button type="button" onClick={() => void save()} disabled={state.kind === 'saving'} className={PRIMARY}>{state.kind === 'saving' ? 'Saving…' : 'Save'}</button>
          <button type="button" onClick={() => setState({ kind: 'dismissed' })} className={OUTLINE}>No thanks</button>
        </div>
      )}
      {state.kind === 'problem' && <p role="alert" className="text-xs">{state.text} {state.link && <Link href={state.link} className="underline">Open</Link>}</p>}
    </div>
  );
}

// One assistant answer, rendered from the validated stream. Server text is shown as plain text (React escapes it); only the controls
// above can act, and only on a press.
export function AssistantTurn({ state, onRetry }: { state: ChatState; onRetry?: () => void }) {
  const text = state.items.map((i) => (i.type === 'text' ? i.delta : '')).join('');
  const products = state.items.flatMap((i) => (i.type === 'product' ? [i] : []));
  const proposals = state.items.flatMap((i) => (i.type === 'proposal' ? [i] : []));
  const suggestions = state.items.flatMap((i) => (i.type === 'memory_suggestion' ? [i] : []));
  const believed = (p: Proposal) => p.decision.outcome === 'validated' && p.params !== undefined;
  const tied = new Map(proposals.filter((p) => believed(p) && p.action_type === 'add_to_cart').map((p) => [String(p.params!.product_id), p]));
  const shown = new Set(products.map((p) => p.product.product_id));
  const standalone = proposals.filter((p) => !(believed(p) && p.action_type === 'add_to_cart' && shown.has(String(p.params!.product_id))));
  const names = new Map(products.map((p) => [p.product.product_id, p.product.name] as const));
  const summarise = (p: Proposal) => {
    const rows = p.action_type === 'add_to_cart' ? [p.params!] : ((p.params!.items as Record<string, unknown>[]) ?? []);
    const what = rows.map((r) => `${names.get(String(r.product_id)) ?? 'item'} × ${String(r.quantity)} (${String(r.currency)} ${String(r.expected_unit_price)} each)`).join(', ');
    return p.action_type === 'add_to_cart' ? `Add ${what} to your cart?` : `Start a WhatsApp enquiry for ${what}? Nothing is sent until you open WhatsApp and press send.`;
  };
  return (
    <div className="space-y-2" data-testid="assistant-message" aria-live="polite">
      {text ? <div dir="auto" className="max-w-[92%] break-words rounded-2xl rounded-es-sm border border-[#e5d4bf] bg-white px-3 py-2"><MarkdownText text={text} /></div> : null}
      {products.length ? (
        <ul className="space-y-2" aria-label="Recommended products">
          {products.map((i) => <ProductCard key={i.seq} product={i.product} proposal={tied.get(i.product.product_id)} sessionId={state.meta?.session_id ?? ''} />)}
        </ul>
      ) : null}
      {standalone.map((p) => (
        <div key={p.seq}>
          <p data-testid="proposal" data-outcome={p.decision.outcome} className="text-xs text-[#6f5a4c]">
            {p.decision.outcome === 'validated' ? 'Suggested (nothing has been done yet).' : REJECTED_TEXT}
          </p>
          {believed(p) && state.meta ? <ConfirmBlock item={p} sessionId={state.meta.session_id} summary={summarise(p)} /> : null}
        </div>
      ))}
      {proposals.filter((p) => !standalone.includes(p)).map((p) => <span key={p.seq} data-testid="proposal" data-outcome={p.decision.outcome} className="sr-only">Suggested (nothing has been done yet).</span>)}
      {suggestions.map((s) => <RememberCard key={s.seq} item={s} />)}
      {state.status === 'error' ? (
        <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-900" data-testid="assistant-error">
          <p>{ERROR_TEXT[state.error ?? ''] ?? 'Something went wrong. Please try again.'}</p>
          {onRetry ? <button type="button" onClick={onRetry} className="mt-2 rounded-full border border-red-300 px-3 py-1 text-xs focus-visible:outline-2 focus-visible:outline-red-700">Try again</button> : null}
        </div>
      ) : null}
    </div>
  );
}

type Recognizer = { lang: string; interimResults: boolean; onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null; onend: (() => void) | null; onerror: (() => void) | null; start: () => void; stop: () => void };
const speechApi = (): (new () => Recognizer) | undefined =>
  typeof window === 'undefined' ? undefined : (window as unknown as Record<string, new () => Recognizer>).SpeechRecognition || (window as unknown as Record<string, new () => Recognizer>).webkitSpeechRecognition;
const newId = (prefix: string) => `${prefix}${crypto.randomUUID().replace(/-/g, '')}`;

type Turn = { id: string; user: string; state: ChatState };

export default function AssistantPanel({ onClose }: { onClose: () => void }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const session = useRef(newId('sess_'));
  const viaVoice = useRef(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const Speech = useSyncExternalStore(() => () => {}, speechApi, () => undefined); // undefined on the server, so hydration matches

  useEffect(() => { inputRef.current?.focus(); }, []);
  useEffect(() => { endRef.current?.scrollIntoView?.({ block: 'end' }); }, [turns]);

  async function send(raw: string) {
    const text = raw.trim();
    if (!text || abort.current) return;
    const controller = new AbortController();
    abort.current = controller;
    setBusy(true);
    const id = newId('turn_');
    let current = initialState();
    setTurns((all) => [...all, { id, user: text, state: current }]);
    setInput('');
    const context: Record<string, string> = viaVoice.current ? { input: 'voice' } : {};
    const req = { session_id: session.current, idempotency_key: newId('idem_'), context, message: text };
    viaVoice.current = false;
    for await (const event of streamAssistant(req, controller.signal)) {
      current = reduce(current, event);
      const next = current;
      setTurns((all) => all.map((t) => (t.id === id ? { ...t, state: next } : t)));
    }
    abort.current = null;
    setBusy(false);
  }

  const submit = (event: FormEvent) => { event.preventDefault(); void send(input); };
  const newChat = () => { abort.current?.abort(); abort.current = null; setBusy(false); setTurns([]); setInput(''); session.current = newId('sess_'); inputRef.current?.focus(); };
  const last = turns.at(-1);
  const retry = () => { if (last) { setTurns((all) => all.slice(0, -1)); void send(last.user); } };
  const thinking = busy && !!last && !last.state.items.some((i) => i.type === 'text' || i.type === 'product');

  // The transcript only fills the box: the customer reads it, can fix it, and presses Send. Typing clears the voice flag.
  function listen() {
    if (!Speech || listening) return;
    const recognizer = new Speech();
    recognizer.lang = 'en-PK';
    recognizer.interimResults = false;
    recognizer.onresult = (e) => { viaVoice.current = true; setInput(e.results[0][0].transcript.slice(0, 500)); };
    recognizer.onend = recognizer.onerror = () => setListening(false);
    setListening(true);
    recognizer.start();
  }

  return (
    <section
      role="dialog"
      aria-label="Elegance Shawls shopping assistant"
      onKeyDown={(e) => { if (e.key === 'Escape') { e.stopPropagation(); onClose(); } }}
      className="fixed inset-0 z-50 flex flex-col overflow-hidden bg-[#fbf7f2] text-[#2f241f] motion-safe:animate-in motion-safe:fade-in sm:inset-auto sm:bottom-24 sm:end-5 sm:h-[640px] sm:max-h-[calc(100vh-7rem)] sm:w-[400px] sm:rounded-2xl sm:border sm:border-[#e5d4bf] sm:shadow-2xl"
    >
      <header className="flex items-center gap-2 border-b border-[#e5d4bf] bg-[#2f241f] px-4 py-3 text-white">
        <Sparkles className="size-4 text-[#c9a577]" aria-hidden />
        <div className="min-w-0 flex-1">
          <h2 className="font-heading text-base leading-tight">Shopping concierge</h2>
          <p className="text-xs text-[#e5d4bf]">Ask in English, Roman Urdu or Urdu</p>
        </div>
        <button type="button" onClick={newChat} aria-label="New chat" className="rounded-full p-2 hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-white"><SquarePen className="size-4" aria-hidden /></button>
        <button type="button" onClick={onClose} aria-label="Close assistant" className="rounded-full p-2 hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-white"><X className="size-4" aria-hidden /></button>
      </header>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto overflow-x-hidden px-4 py-4" role="log" aria-label="Conversation">
        {turns.length === 0 ? (
          <div className="space-y-4 py-6 text-center" data-testid="assistant-welcome">
            <h3 className="font-heading text-xl">Welcome to Elegance Shawls</h3>
            <p className="text-sm text-[#6f5a4c]">Tell me what you are looking for and I will suggest pieces from the collection.</p>
            <div className="flex flex-col gap-2">
              {SUGGESTED_PROMPTS.map((prompt) => (
                <button key={prompt} type="button" onClick={() => void send(prompt)} className={`rounded-full border border-[#c9a577] bg-white px-4 py-2 text-sm hover:bg-[#f3e9dc] ${FOCUS}`}>{prompt}</button>
              ))}
            </div>
          </div>
        ) : null}

        {turns.map((turn, index) => (
          <div key={turn.id} className="space-y-3">
            <div className="flex justify-end"><p dir="auto" className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-ee-sm bg-[#2f241f] px-3 py-2 text-sm text-white" data-testid="assistant-user-message">{turn.user}</p></div>
            <AssistantTurn state={turn.state} onRetry={index === turns.length - 1 && !busy ? retry : undefined} />
          </div>
        ))}

        {thinking ? <p className="text-sm text-[#6f5a4c] motion-safe:animate-pulse" role="status" data-testid="assistant-thinking">Choosing pieces for you…</p> : null}
        <div ref={endRef} />
      </div>

      <form onSubmit={submit} className="border-t border-[#e5d4bf] bg-white p-3">
        <div className="flex items-end gap-2 rounded-2xl border border-[#c9a577] bg-[#fbf7f2] p-2 focus-within:ring-2 focus-within:ring-[#9a6b3f]">
          <label htmlFor="assistant-input" className="sr-only">Message the shopping assistant</label>
          <textarea
            id="assistant-input" ref={inputRef} dir="auto" rows={1} value={input} maxLength={500}
            onChange={(e) => { viaVoice.current = false; setInput(e.target.value); }}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send(input); } }}
            placeholder="Ask about shawls, stoles, colours…"
            className="max-h-28 min-h-9 flex-1 resize-none bg-transparent px-1 py-1.5 text-sm outline-none"
          />
          {Speech ? (
            <button type="button" onClick={listen} disabled={listening || busy} aria-label="Speak your request" className={`rounded-full border border-[#c9a577] p-2 text-[#2f241f] disabled:opacity-40 ${FOCUS}`}>
              <Mic className={`size-4 ${listening ? 'motion-safe:animate-pulse text-red-700' : ''}`} aria-hidden />
            </button>
          ) : null}
          {busy ? (
            <button type="button" onClick={() => abort.current?.abort()} aria-label="Stop response" className={`rounded-full bg-[#2f241f] p-2 text-white ${FOCUS}`}><Square className="size-4" aria-hidden /></button>
          ) : (
            <button type="submit" disabled={!input.trim()} aria-label="Send message" className={`rounded-full bg-[#2f241f] p-2 text-white disabled:opacity-40 ${FOCUS}`}><Send className="size-4" aria-hidden /></button>
          )}
        </div>
        <p className="mt-2 text-center text-[11px] text-[#6f5a4c]">
          {Speech ? 'Speaking uses your browser’s speech service; you can always type. ' : ''}Orders are confirmed through <Link href="/cart" className="underline">your cart and WhatsApp</Link>
        </p>
      </form>
    </section>
  );
}
