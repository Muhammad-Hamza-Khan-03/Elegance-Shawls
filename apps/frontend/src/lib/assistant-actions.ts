// M3-S3 client for the user-confirmed assistant actions. Nothing here runs until a person presses a confirm button; the server
// re-checks everything, and the browser re-checks the current published product before touching its own cart or handing off.
import { api } from '@/lib/api';
import type { Product, ProductVariant } from '@/types/types';

export type ExecItem = { product_id: string; variant_id: string; quantity: number; slug: string };
export type ActionRequest = { session_id: string; idempotency_key: string; action_type: string; params: Record<string, unknown> };
export type ActionOutcome = { ok: true; replayed: boolean; items: ExecItem[]; reference: string | null } | { ok: false; reason: string; message: string };

const CHANGED = 'This item changed, so nothing was done. Please ask again to get an up-to-date suggestion.';
const FAILURE_TEXT: Record<string, string> = {
  stale_price: 'The price changed, so nothing was done. Please ask again to see the new price.',
  stale_revision: CHANGED, product_unavailable: CHANGED, product_not_found: CHANGED, variant_not_found: CHANGED, variant_unavailable: CHANGED,
  out_of_stock: 'Sorry, this item is out of stock, so nothing was done.',
  insufficient_stock: 'Not enough stock for that quantity, so nothing was done.',
  idempotency_conflict: 'This request was already used for something different. Please ask again.',
  execution_failed: 'That did not go through. You can try again.',
};
const DEFAULT_TEXT = 'We could not do that, so nothing was done. Please try again.';
const fail = (reason: string): ActionOutcome => ({ ok: false, reason, message: FAILURE_TEXT[reason] ?? DEFAULT_TEXT });

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const validItem = (i: unknown): i is ExecItem => {
  const r = i as Record<string, unknown> | null;
  return !!r && typeof r.product_id === 'string' && UUID.test(r.product_id) && typeof r.variant_id === 'string' && UUID.test(r.variant_id)
    && Number.isInteger(r.quantity) && (r.quantity as number) >= 1 && typeof r.slug === 'string' && r.slug.length > 0;
};

export async function confirmAction(req: ActionRequest, fetchImpl: typeof fetch = fetch): Promise<ActionOutcome> {
  let response: Response;
  try {
    response = await fetchImpl('/api/assistant/actions/execute', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ ...req, confirmed: true }) });
  } catch {
    return fail('unavailable');
  }
  const body = await response.json().catch(() => null);
  if (response.status === 409 && typeof body?.detail?.reason === 'string') return fail(body.detail.reason);
  const items = body?.result?.items;
  if (!response.ok || body?.status !== 'executed' || !Array.isArray(items) || !items.length || !items.every(validItem)) return fail('unavailable');
  const reference = typeof body.result.reference === 'string' ? body.result.reference : null;
  if (req.action_type === 'start_whatsapp_enquiry' && !reference) return fail('unavailable');
  return { ok: true, replayed: body.replayed === true, items, reference };
}

export type ResolvedLine = { product: Product; variant: ProductVariant; quantity: number };

// Pairs server-verified items with the current published catalogue; null if anything drifted since the server check.
export async function resolveLines(items: ExecItem[], expectedPrices: number[], getProducts: (slugs: string[]) => Promise<Map<string, Product | null>> = api.getPublishedProducts): Promise<ResolvedLine[] | null> {
  const current = await getProducts(items.map((i) => i.slug)).catch(() => null);
  if (!current) return null;
  const lines: ResolvedLine[] = [];
  for (const [n, item] of items.entries()) {
    const product = current.get(item.slug);
    const variant = product?.variants.find((v) => v.id === item.variant_id);
    if (!product || product.id !== item.product_id || !variant || variant.price !== expectedPrices[n] || variant.stock < item.quantity) return null;
    lines.push({ product, variant, quantity: item.quantity });
  }
  return lines;
}
