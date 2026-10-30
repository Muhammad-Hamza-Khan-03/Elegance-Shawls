'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Search } from 'lucide-react';

type Hit = { product: { _id: string; name: string; category?: string } };

export const AdminSearch = () => {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [hits, setHits] = useState<Hit[]>([]);
  const [state, setState] = useState<'idle' | 'loading' | 'done' | 'error'>('idle');
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setState('idle');
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setState('loading');
      try {
        const response = await fetch('/api/admin/search', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ q, limit: 8 }),
          signal: controller.signal,
        });
        if (!response.ok) throw new Error();
        setHits(((await response.json()) as { items: Hit[] }).items);
        setState('done');
      } catch (err) {
        if ((err as Error).name !== 'AbortError') setState('error');
      }
    }, 300);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query]);

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (!box.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  const pick = (id: string) => {
    setOpen(false);
    router.push(`/admin/products?product=${encodeURIComponent(id)}`);
  };

  return (
    <div ref={box} className="relative w-full max-w-md">
      <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#9a6b3f]" />
      <input
        type="search"
        aria-label="Search products"
        placeholder="Search products, e.g. soft pink wedding wrap"
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(event) => event.key === 'Escape' && setOpen(false)}
        className="w-full rounded-full border border-[#d8c8b4] bg-white py-2.5 pl-11 pr-4 text-sm outline-none focus:border-[#9a6b3f]"
      />
      {open && state !== 'idle' ? (
        <ul role="listbox" className="absolute z-20 mt-2 max-h-96 w-full overflow-auto rounded-2xl border border-[#e7dac8] bg-white p-2 shadow-lg">
          {state === 'loading' ? <li className="px-3 py-2 text-sm text-[#6f625a]">Searching…</li> : null}
          {state === 'error' ? <li className="px-3 py-2 text-sm text-red-700">Search is unavailable right now.</li> : null}
          {state === 'done' && hits.length === 0 ? <li className="px-3 py-2 text-sm text-[#6f625a]">No published products match.</li> : null}
          {state === 'done'
            ? hits.map(({ product }) => (
                <li key={product._id} role="option" aria-selected={false}>
                  <button type="button" onClick={() => pick(product._id)} className="w-full rounded-xl px-3 py-2 text-left text-sm hover:bg-[#f4ebe0]">
                    <span className="font-medium">{product.name}</span>
                    {product.category ? <span className="ml-2 text-xs uppercase tracking-wider text-[#9a6b3f]">{product.category}</span> : null}
                  </button>
                </li>
              ))
            : null}
        </ul>
      ) : null}
    </div>
  );
};
