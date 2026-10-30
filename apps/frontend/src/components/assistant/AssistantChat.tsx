'use client';

import { useRef, useState } from 'react';
import { initialState, reduce, streamAssistant, type AssistantEvent, type ChatState } from '@/lib/assistant-stream';

const ERROR_TEXT: Record<string, string> = {
  cancelled: 'Stopped.',
  provider_error: 'The assistant had a problem. Please try again.',
  provider_malformed: 'The assistant sent an unreadable reply. Please try again.',
  provider_overrun: 'The reply was too long and was cut off.',
  unavailable: 'The assistant is unavailable right now.',
};
const REJECTED_TEXT = 'This suggestion was not accepted, so nothing was done.';

// Renders server output as plain text only (React escapes it); proposals are shown as information, never as actions.
export function AssistantView({ state }: { state: ChatState }) {
  return (
    <div aria-live="polite" className="space-y-2">
      {state.items.map((item: AssistantEvent) =>
        item.type === 'text' ? <span key={item.seq}>{item.delta}</span>
        : item.type === 'product' ? (
          <div key={item.seq} data-testid="product" className="rounded border p-2">
            <strong>{item.product.name}</strong>
            {item.product.price !== null && <span> {item.product.currency} {item.product.price}</span>}
          </div>
        ) : item.type === 'proposal' ? (
          <p key={item.seq} data-testid="proposal" data-outcome={item.decision.outcome} className="text-sm">
            {item.decision.outcome === 'validated' ? 'Suggested (nothing has been done yet).' : REJECTED_TEXT}
          </p>
        ) : null,
      )}
      {state.status === 'error' && <p role="alert">{ERROR_TEXT[state.error ?? ''] ?? 'Something went wrong. Please try again.'}</p>}
    </div>
  );
}

const newId = (prefix: string) => `${prefix}${crypto.randomUUID().replace(/-/g, '')}`;

export function AssistantChat({ context = {} }: { context?: Record<string, string> }) {
  const [state, setState] = useState<ChatState>(initialState());
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const session = useRef(newId('sess_'));

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!message.trim() || abort.current) return;
    const controller = new AbortController();
    abort.current = controller;
    setBusy(true);
    let current = initialState();
    setState(current);
    const req = { session_id: session.current, idempotency_key: newId('idem_'), context, message: message.trim() };
    for await (const event of streamAssistant(req, controller.signal)) {
      current = reduce(current, event);
      setState(current);
    }
    abort.current = null;
    setBusy(false);
  }

  return (
    <form onSubmit={send} className="space-y-3">
      <input value={message} onChange={(e) => setMessage(e.target.value)} maxLength={500} aria-label="Message" className="w-full rounded border p-2" />
      <button type="submit" disabled={busy}>Send</button>
      <button type="button" onClick={() => abort.current?.abort()}>Stop</button>
      <AssistantView state={state} />
    </form>
  );
}
