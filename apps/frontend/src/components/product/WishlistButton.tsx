'use client';

import { useEffect, useState } from 'react';
import { readWishlist, toggleWishlist, writeWishlist } from '@/lib/wishlist';

export function WishlistButton({ slug }: { slug: string }) {
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    const sync = () => setSaved(readWishlist().includes(slug));
    sync();
    window.addEventListener('wishlist-change', sync);
    window.addEventListener('storage', sync);
    return () => { window.removeEventListener('wishlist-change', sync); window.removeEventListener('storage', sync); };
  }, [slug]);
  return <button type="button" aria-pressed={saved} onClick={() => writeWishlist(toggleWishlist(readWishlist(), slug))} className="rounded-full border border-[#2f241f] px-6 py-3 text-sm font-semibold">
    {saved ? 'Saved ♥ (remove)' : 'Save for later ♡'}
  </button>;
}
