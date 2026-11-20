'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { formatCurrency } from '@/lib/whatsapp';
import { readWishlist, toggleWishlist, writeWishlist } from '@/lib/wishlist';
import { Product } from '@/types/types';

export function SavedProducts() {
  const [slugs, setSlugs] = useState<string[] | null>(null);
  const [products, setProducts] = useState<Map<string, Product | null>>(new Map());
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const sync = () => setSlugs(readWishlist());
    sync();
    window.addEventListener('wishlist-change', sync);
    return () => window.removeEventListener('wishlist-change', sync);
  }, []);

  useEffect(() => {
    if (!slugs?.length) return;
    let live = true;
    api.getPublishedProducts(slugs).then((map) => { if (live) setProducts(map); }).catch(() => { if (live) setFailed(true); });
    return () => { live = false; };
  }, [slugs]);

  return <main id="main-content" className="min-h-screen bg-[#fbf7f0] px-6 py-12 text-[#2f241f]">
    <div className="mx-auto max-w-3xl">
      <h1 className="font-heading text-4xl font-semibold">Saved products</h1>
      <p className="mt-2 text-sm text-[#6f625a]">Stored only on this device. Prices and availability are shown live.</p>
      {slugs === null ? null : slugs.length === 0 ? <p className="mt-8">Nothing saved yet. <Link href="/products" className="underline">Browse the collection</Link>.</p> : failed ? <p role="alert" className="mt-8 text-red-700">Could not load saved products. Please try again.</p> : <ul className="mt-8 space-y-4">
        {slugs.map((slug) => {
          const product = products.get(slug);
          return <li key={slug} className="flex items-center justify-between gap-4 rounded-2xl border border-[#e7dac8] bg-white p-4">
            {product ? <Link href={`/product/${slug}`} className="font-semibold underline">{product.name} · {formatCurrency(product.price, product.currency)}{product.stock > 0 ? '' : ' (out of stock)'}</Link> : products.has(slug) ? <span className="text-[#6f625a]">No longer available</span> : <span className="text-[#6f625a]">Loading…</span>}
            <button type="button" onClick={() => writeWishlist(toggleWishlist(readWishlist(), slug))} className="text-sm underline">Remove</button>
          </li>;
        })}
      </ul>}
    </div>
  </main>;
}
