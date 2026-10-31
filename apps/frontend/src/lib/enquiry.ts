import type { CartItem } from '@/lib/cart';

export type EnquiryIssue = {
  product_id: string;
  variant_id: string;
  reason: 'unavailable' | 'out_of_stock' | 'insufficient_stock' | 'price_changed';
};

// The server found the cart out of date: re-verify against the catalogue before trying again.
export class StaleCartError extends Error {
  constructor(public issues: EnquiryIssue[]) {
    super('Your cart is out of date.');
  }
}

// Asks the same-origin proxy for a reference. It records the cart server-side; it sends nothing and orders nothing.
export const createEnquiry = async (items: CartItem[]): Promise<string> => {
  const response = await fetch('/api/enquiries', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      items: items.map((item) => ({
        product_id: item.productId,
        variant_id: item.variantId,
        quantity: item.quantity,
        unit_price: item.variant.price,
        currency: item.product.currency,
      })),
    }),
  });
  const body = await response.json().catch(() => null);
  if (response.status === 409 && body?.detail?.code === 'cart_stale') throw new StaleCartError(body.detail.issues ?? []);
  if (!response.ok || typeof body?.reference !== 'string') throw new Error('We could not create your enquiry reference. Please try again.');
  return body.reference;
};
