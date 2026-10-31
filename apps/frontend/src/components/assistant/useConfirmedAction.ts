'use client';

import { useRef, useState } from 'react';
import { useCart } from '@/components/cart/CartProvider';
import { confirmAction, resolveLines } from '@/lib/assistant-actions';
import { buildCartCheckoutUrl, createCartItem } from '@/lib/cart';
import type { AssistantEvent } from '@/lib/assistant-stream';

export type Proposal = Extract<AssistantEvent, { type: 'proposal' }>;
export type ActionResult = { kind: 'done'; text: string; url?: string } | { kind: 'failed'; text: string } | null;

const WHATSAPP_NUMBER = process.env.NEXT_PUBLIC_WHATSAPP_NUMBER || '';
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || '';

// The only thing in the chat that can act, and only when a person presses a confirm control. Each press re-checks on the server and again
// against the current catalogue; the proposal's idempotency key makes a double press (or a retry after a lost reply) harmless.
export function useConfirmedAction(item: Proposal, sessionId: string) {
  const { addItem } = useCart();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ActionResult>(null);
  const lock = useRef(false);

  async function confirm() {
    const params = item.params!;
    const rows = (item.action_type === 'add_to_cart' ? [params] : (params.items as Record<string, unknown>[])) ?? [];
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

  return { busy, result, confirm };
}
