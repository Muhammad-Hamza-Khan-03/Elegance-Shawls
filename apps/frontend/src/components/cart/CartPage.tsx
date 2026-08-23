'use client';

import Image from 'next/image';
import Link from 'next/link';
import { Minus, Plus, ShoppingBag, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useCart } from '@/components/cart/CartProvider';
import { buildCartCheckoutUrl, getCartSummary } from '@/lib/cart';
import { formatCurrency } from '@/lib/whatsapp';

const whatsappNumber = process.env.NEXT_PUBLIC_WHATSAPP_NUMBER || '';

export const CartPage = () => {
  const { items, hydrated, incrementItem, decrementItem, removeItem, clearCart, setItemQuantity } = useCart();
  const summary = getCartSummary(items);
  const checkoutUrl = hydrated && items.length > 0 ? (() => {
    try {
      return buildCartCheckoutUrl(items, whatsappNumber);
    } catch {
      return null;
    }
  })() : null;

  return (
    <main id="main-content" className="min-h-screen bg-[#fbf7f0] px-6 py-12 text-[#2f241f]">
      <section className="mx-auto max-w-6xl space-y-10">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <Link href="/products" className="text-sm font-medium text-[#9a6b3f] hover:underline">← Back to collection</Link>
            <h1 className="mt-4 text-4xl font-semibold tracking-tight sm:text-5xl">Your cart</h1>
            <p className="mt-3 max-w-2xl leading-7 text-[#6f625a]">
              Keep more than one shawl or stole in the same shared cart, then adjust quantities before sending your order enquiry.
            </p>
          </div>
          <div className="rounded-2xl border border-[#e7dac8] bg-white/80 px-5 py-4 text-sm text-[#6f625a]">
            <p className="font-semibold text-[#2f241f]">{summary.itemCount} item{summary.itemCount === 1 ? '' : 's'}</p>
            <p>{formatCurrency(summary.subtotal, summary.currency)}</p>
          </div>
        </div>

        {!hydrated ? (
          <div className="rounded-3xl border border-[#e7dac8] bg-white/70 p-10 text-center text-[#6f625a]">Loading your saved cart…</div>
        ) : items.length === 0 ? (
          <div className="rounded-3xl border border-[#e7dac8] bg-white/70 p-10 text-center">
            <ShoppingBag className="mx-auto h-10 w-10 text-[#9a6b3f]" />
            <h2 className="mt-4 text-2xl font-semibold">Your cart is empty</h2>
            <p className="mt-3 text-[#6f625a]">Browse the collection and add one or more products to keep them together here.</p>
            <Button asChild className="mt-6 rounded-full bg-[#2f241f] px-6 py-3 font-semibold text-white hover:bg-[#4a382f]">
              <Link href="/products">Browse products</Link>
            </Button>
          </div>
        ) : (
          <div className="grid gap-8 lg:grid-cols-[1.3fr_0.7fr]">
            <div className="space-y-4">
              {items.map((item) => (
                <article key={item.lineId} className="grid gap-5 rounded-3xl border border-[#e7dac8] bg-white/80 p-5 shadow-sm sm:grid-cols-[140px_1fr]">
                  <div className="relative aspect-[3/4] overflow-hidden rounded-2xl bg-[#efe5d5]">
                    <Image src={item.product.images[0]} alt={item.product.name} fill sizes="140px" className="object-cover" />
                  </div>
                  <div className="space-y-4">
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.25em] text-[#9a6b3f]">{item.product.category}</p>
                        <h2 className="mt-1 text-2xl font-semibold">{item.product.name}</h2>
                        <p className="mt-1 text-sm text-[#6f625a]">{item.variant.color} · {item.variant.size}</p>
                      </div>
                      <button type="button" onClick={() => removeItem(item.lineId)} className="inline-flex items-center gap-2 text-sm font-semibold text-red-700 hover:underline">
                        <Trash2 className="h-4 w-4" />
                        Remove
                      </button>
                    </div>

                    <div className="flex flex-wrap items-center gap-4 text-sm">
                      <span className="font-semibold">{formatCurrency(item.variant.price, item.product.currency)}</span>
                      <span className="text-[#6f625a]">{item.variant.stock} available</span>
                      <span className="text-[#6f625a]">Line total: {formatCurrency(item.variant.price * item.quantity, item.product.currency)}</span>
                    </div>

                    <div className="flex flex-wrap items-center gap-3">
                      <div className="flex items-center overflow-hidden rounded-full border border-[#e7dac8] bg-[#fbf7f0]">
                        <button type="button" aria-label={`Decrease ${item.product.name} quantity`} onClick={() => decrementItem(item.lineId)} disabled={item.quantity <= 1} className="p-3 disabled:opacity-35">
                          <Minus className="h-4 w-4" />
                        </button>
                        <input
                          aria-label={`Quantity for ${item.product.name}`}
                          type="number"
                          min={1}
                          max={item.variant.stock}
                          value={item.quantity}
                          onChange={(event) => setItemQuantity(item.lineId, Number(event.target.value))}
                          className="w-16 bg-transparent text-center font-semibold outline-none"
                        />
                        <button type="button" aria-label={`Increase ${item.product.name} quantity`} onClick={() => incrementItem(item.lineId)} disabled={item.quantity >= item.variant.stock} className="p-3 disabled:opacity-35">
                          <Plus className="h-4 w-4" />
                        </button>
                      </div>
                      <p className="text-xs leading-6 text-[#6f625a]">Quantity is capped at the available stock for the chosen option.</p>
                    </div>
                  </div>
                </article>
              ))}
            </div>

            <aside className="space-y-4 rounded-3xl border border-[#e7dac8] bg-white/80 p-6 shadow-sm lg:sticky lg:top-24 lg:self-start">
              <h2 className="text-2xl font-semibold">Summary</h2>
              <div className="space-y-2 text-sm text-[#6f625a]">
                <div className="flex items-center justify-between"><span>Products</span><span>{summary.itemCount}</span></div>
                <div className="flex items-center justify-between"><span>Subtotal</span><strong className="text-[#2f241f]">{formatCurrency(summary.subtotal, summary.currency)}</strong></div>
              </div>
              <div className="rounded-2xl bg-[#fbf7f0] p-4 text-sm text-[#6f625a]">
                This cart is saved in your browser so it survives a refresh on the same device.
              </div>
              {checkoutUrl ? (
                <Button asChild className="w-full rounded-full bg-[#2f241f] px-6 py-3 font-semibold text-white hover:bg-[#4a382f]">
                  <a href={checkoutUrl} target="_blank" rel="noreferrer">Send cart on WhatsApp</a>
                </Button>
              ) : (
                <Button disabled className="w-full rounded-full bg-[#8b817c] px-6 py-3 font-semibold text-white">WhatsApp unavailable</Button>
              )}
              <Button variant="outline" className="w-full rounded-full border-[#d8c8b4] bg-transparent px-6 py-3 font-semibold" onClick={clearCart}>
                Clear cart
              </Button>
            </aside>
          </div>
        )}
      </section>
    </main>
  );
};
