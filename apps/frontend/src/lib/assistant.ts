import { Product } from '@/types/types';
import { createCartItem } from '@/lib/cart';

// Off unless explicitly "true"; inlined at build time, so the panel code is absent when off.
export const ASSISTANT_ENABLED = process.env.NEXT_PUBLIC_ASSISTANT_ENABLED === 'true';

export const ACTION_NAMES = ['show_products', 'open_product', 'apply_filters', 'add_to_cart', 'start_whatsapp_order'] as const;
export type ActionName = (typeof ACTION_NAMES)[number];
export const CONFIRM_ACTIONS: readonly ActionName[] = ['add_to_cart', 'start_whatsapp_order'];

// Mirrors backend MAX_CONFIRMATION_TTL = 300s.
const CONFIRMATION_TTL = 120;
// confirmed_at must not be in the server's future; back-date to absorb client clock skew.
const SKEW_ALLOWANCE = 5;

export interface Proposal {
  actionId: string;
  name: ActionName;
  input: Record<string, unknown>;
  outcome: string;
  reason: string;
  fingerprint?: string;
  needsConfirmation: boolean;
}

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);

/** Builds a proposal from a streamed tool part; anything off-contract is dropped, never guessed. */
export const toProposal = (toolName: string, input: unknown, output: unknown): Proposal | null => {
  if (!(ACTION_NAMES as readonly string[]).includes(toolName) || !isRecord(input) || !isRecord(output)) return null;
  if (typeof output.action_id !== 'string' || typeof output.outcome !== 'string') return null;
  const name = toolName as ActionName;
  return {
    actionId: output.action_id,
    name,
    input,
    outcome: output.outcome,
    reason: typeof output.reason === 'string' ? output.reason : '',
    fingerprint: typeof output.fingerprint === 'string' ? output.fingerprint : undefined,
    needsConfirmation: output.outcome === 'needs_confirmation' && output.requires_confirmation === true
      && CONFIRM_ACTIONS.includes(name) && typeof output.fingerprint === 'string',
  };
};

/** Body for /api/assistant/actions/execute. `explicit` is true only because the caller is a user's confirm click. */
export const buildExecuteBody = (p: Proposal, sessionId: string, nowMs = Date.now()) => {
  const confirmedAt = nowMs / 1000 - SKEW_ALLOWANCE;
  return {
    action_id: p.actionId,
    name: p.name,
    session_id: sessionId,
    params: p.input,
    constraints: { hard: {} },
    confirmation: {
      action_id: p.actionId,
      session_id: sessionId,
      fingerprint: p.fingerprint,
      confirmed_at: confirmedAt,
      expires_at: confirmedAt + CONFIRMATION_TTL,
      explicit: true,
    },
  };
};

export interface CartLine { product_id: string; variant_id: string; quantity: number }
export type CartApply = 'added' | 'unavailable';

/** Applies server-validated add_to_cart lines through the client cart. All-or-nothing: no clamping, no substitution. */
export const applyAddToCart = (
  lines: CartLine[],
  catalogue: Product[],
  addItem: (product: Product, variant: Product['variants'][number], quantity: number) => void,
): CartApply => {
  const resolved = lines.map((l) => {
    const product = catalogue.find((p) => p.id === l.product_id && p.status === 'active');
    const variant = product?.variants.find((v) => v.id === l.variant_id);
    return product && variant && createCartItem(product, variant, l.quantity)?.quantity === l.quantity
      ? { product, variant, quantity: l.quantity } : null;
  });
  if (resolved.length === 0 || resolved.some((r) => !r)) return 'unavailable';
  resolved.forEach((r) => addItem(r!.product, r!.variant, r!.quantity));
  return 'added';
};

// Action ids this browser tab has actually put in the cart. Ids only, no cart or personal data.
const APPLIED_KEY = 'es_assistant_applied';
const readApplied = (storage: Pick<Storage, 'getItem'>): string[] => {
  try {
    const v = JSON.parse(storage.getItem(APPLIED_KEY) ?? '[]');
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : [];
  } catch { return []; }
};
export const wasApplied = (storage: Pick<Storage, 'getItem'>, actionId: string) => readApplied(storage).includes(actionId);
export const markApplied = (storage: Pick<Storage, 'getItem' | 'setItem'>, actionId: string) => {
  try { storage.setItem(APPLIED_KEY, JSON.stringify([...readApplied(storage), actionId].slice(-200))); } catch { /* storage blocked: replay then re-applies at most once per page load */ }
};
