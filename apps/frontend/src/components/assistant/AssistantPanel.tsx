'use client';

import { useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useChat } from '@ai-sdk/react';
import { DefaultChatTransport, getToolName, isToolUIPart } from 'ai';
import { useCart } from '@/components/cart/CartProvider';
import { api } from '@/lib/api';
import { applyAddToCart, buildExecuteBody, CartLine, markApplied, Proposal, toProposal, wasApplied } from '@/lib/assistant';

type Status = 'added' | 'handoff' | 'unavailable' | 'rejected' | 'failed';
const STATUS_TEXT: Record<Status, string> = {
  added: 'کارٹ میں شامل کر دیا گیا۔',
  handoff: 'آرڈر ابھی نہیں بھیجا گیا۔ کارٹ میں جا کر خود جائزہ لیں اور بھیجیں۔',
  unavailable: 'یہ آئٹم اب دستیاب نہیں؛ کچھ شامل نہیں کیا گیا۔',
  rejected: 'تصدیق قبول نہیں ہوئی؛ کچھ نہیں ہوا۔',
  failed: 'رابطہ نہیں ہو سکا؛ دوبارہ کوشش کریں۔',
};

const newSessionId = () => `sess_${crypto.randomUUID()}`;

export const AssistantPanel = () => {
  const { addItem } = useCart();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [results, setResults] = useState<Record<string, Status>>({});
  const [sessionId] = useState(newSessionId); // panel is client-only (ssr:false)
  const inFlight = useRef(new Set<string>());

  const transport = useMemo(() => new DefaultChatTransport({
    api: '/api/assistant/stream',
    prepareSendMessagesRequest: ({ messages }) => {
      const last = messages[messages.length - 1];
      const message = last.parts.map((p) => (p.type === 'text' ? p.text : '')).join('').trim();
      return { body: { session_id: sessionId, message } };
    },
  }), [sessionId]);
  const { messages, sendMessage, status, error } = useChat({ transport });

  const confirm = async (p: Proposal) => {
    if ((results[p.actionId] && results[p.actionId] !== 'failed') || inFlight.current.has(p.actionId)) return; // one execution per action id
    inFlight.current.add(p.actionId);
    const done = (s: Status) => setResults((r) => ({ ...r, [p.actionId]: s }));
    try {
      const res = await fetch('/api/assistant/actions/execute', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(buildExecuteBody(p, sessionId)),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok || data?.status !== 'executed' || data.action_id !== p.actionId) return done('rejected');
      if (p.name === 'start_whatsapp_order') return done('handoff'); // inert: the cart page does the verified WhatsApp send
      // The server may have claimed this action before a client-side failure: success only if this browser applied it.
      if (wasApplied(sessionStorage, p.actionId)) return done('added');
      const lines = data.intent?.items as CartLine[] | undefined;
      if (!Array.isArray(lines)) return done('failed');
      const catalogue = await api.findProducts(lines.map((l) => l.product_id));
      const applied = applyAddToCart(lines, catalogue, addItem);
      if (applied === 'added') markApplied(sessionStorage, p.actionId);
      done(applied);
    } catch {
      done('failed');
    } finally {
      inFlight.current.delete(p.actionId);
    }
  };

  if (!open) {
    return (
      <button type="button" dir="rtl" onClick={() => setOpen(true)}
        className="fixed bottom-4 start-4 z-40 rounded-full bg-stone-900 px-4 py-2 text-sm text-white shadow-lg">
        اسسٹنٹ
      </button>
    );
  }

  return (
    <section dir="rtl" lang="ur" aria-label="اسسٹنٹ" data-testid="assistant-panel"
      className="fixed bottom-4 start-4 z-40 flex max-h-[80vh] w-[22rem] max-w-[calc(100vw-2rem)] flex-col rounded-lg border bg-white text-start shadow-xl">
      <header className="flex items-center justify-between border-b p-3">
        <h2 className="text-sm font-semibold">اسسٹنٹ</h2>
        <button type="button" onClick={() => setOpen(false)} aria-label="بند کریں">✕</button>
      </header>
      <div className="flex-1 space-y-3 overflow-y-auto p-3" aria-live="polite">
        {messages.map((m) => (
          <div key={m.id} className={m.role === 'user' ? 'text-stone-600' : ''}>
            {m.parts.map((part, i) => {
              if (part.type === 'text') return <p key={i} className="whitespace-pre-wrap text-sm">{part.text}</p>;
              if (!isToolUIPart(part) || part.state !== 'output-available') return null;
              const p = toProposal(getToolName(part), part.input, part.output);
              if (!p) return null;
              const result = results[p.actionId];
              return (
                <div key={i} className="my-2 rounded border p-2 text-sm" data-testid="proposal-card">
                  <code dir="ltr" className="block text-start text-xs">{p.name}</code>
                  <pre dir="ltr" className="overflow-x-auto text-start text-xs">{JSON.stringify(p.input, null, 1)}</pre>
                  {p.outcome === 'rejected' && (
                    <p role="alert" className="text-red-700">
                      {p.reason === 'silent_relaxation' ? 'کوئی شرط خاموشی سے نرم نہیں کی جا سکتی۔' : 'یہ تجویز قبول نہیں ہوئی۔'}
                      {' '}<code dir="ltr">{p.reason}</code>
                    </p>
                  )}
                  {p.needsConfirmation && (!result || result === 'failed') && (
                    <button type="button" onClick={() => confirm(p)} className="mt-1 rounded bg-stone-900 px-3 py-1 text-white">
                      تصدیق کریں
                    </button>
                  )}
                  {result && <p role="status">{STATUS_TEXT[result]}{result === 'handoff' && <> <Link href="/cart" className="underline">کارٹ</Link></>}</p>}
                </div>
              );
            })}
          </div>
        ))}
        {error && <p role="alert" className="text-sm text-red-700">{STATUS_TEXT.failed}</p>}
      </div>
      <form className="flex gap-2 border-t p-3" onSubmit={(e) => {
        e.preventDefault();
        if (!text.trim() || status === 'submitted' || status === 'streaming') return;
        sendMessage({ text: text.trim() });
        setText('');
      }}>
        <input value={text} onChange={(e) => setText(e.target.value)} maxLength={500} aria-label="پیغام"
          className="min-w-0 flex-1 rounded border px-2 py-1 text-sm" />
        <button type="submit" disabled={status === 'submitted' || status === 'streaming'} className="rounded bg-stone-900 px-3 py-1 text-sm text-white disabled:opacity-50">
          بھیجیں
        </button>
      </form>
    </section>
  );
};
