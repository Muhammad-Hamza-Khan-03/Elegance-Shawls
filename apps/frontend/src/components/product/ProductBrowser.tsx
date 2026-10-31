'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { api } from '@/lib/api';
import { CATEGORY_LABELS, PRODUCT_CATEGORIES } from '@/lib/categories';
import { CatalogCategory, CatalogSort, filterAndSortProducts } from '@/lib/catalog';
import { formatCurrency } from '@/lib/whatsapp';
import { installFlushOnHide, track } from '@/lib/tracker';
import { Product } from '@/types/types';

const PAGE_SIZE = 9;

export function CategoryFilter({ value, onChange }: { value: CatalogCategory; onChange: (category: CatalogCategory) => void }) {
  return <div><label htmlFor="category" className="mb-2 block text-sm font-semibold">Category</label><select id="category" value={value} onChange={(event) => onChange(event.target.value as CatalogCategory)} className="w-full rounded-xl border border-[#d8c8b4] bg-white px-4 py-3"><option value="all">All products</option>{PRODUCT_CATEGORIES.map((key) => <option key={key} value={key}>{CATEGORY_LABELS[key]}</option>)}</select></div>;
}

export function ProductBrowser({ initialCategory = 'all' }: { initialCategory?: CatalogCategory }) {
  const [products, setProducts] = useState<Product[]>([]);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState<CatalogCategory>(initialCategory);
  const [sort, setSort] = useState<CatalogSort>('newest');
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [request, setRequest] = useState(0);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState(false);

  const generation = useRef(0);

  useEffect(() => {
    let active = true;
    generation.current = request;
    api.getProductPage()
      .then((result) => { if (!active) return; setProducts(result.items); setNextCursor(result.nextCursor); })
      .catch(() => active && setError('We could not load the collection. Please try again.'))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [request]);

  // Progressive: the first 100 products load up front; further cursor pages only on request, then search/category/sort apply to everything fetched.
  const loadMore = () => {
    if (!nextCursor || loadingMore) return;
    const started = generation.current;
    setLoadingMore(true); setMoreError(false);
    api.getProductPage(nextCursor)
      .then((result) => {
        if (started !== generation.current) return; // a reload replaced the list meanwhile
        setProducts((current) => { const known = new Set(current.map((item) => item.id || item.slug)); return [...current, ...result.items.filter((item) => !known.has(item.id || item.slug))]; });
        setNextCursor(result.nextCursor === nextCursor ? null : result.nextCursor);
      })
      .catch(() => started === generation.current && setMoreError(true))
      .finally(() => setLoadingMore(false));
  };

  const filtered = useMemo(() => filterAndSortProducts(products, { query, category, sort }), [products, query, category, sort]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const visible = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const updateFilters = (action: () => void) => { action(); setPage(1); };

  useEffect(() => installFlushOnHide(), []);
  // Debounced so typing logs one search, not one event per keystroke. Best effort: never blocks rendering.
  useEffect(() => {
    if (loading || (!query.trim() && category === 'all')) return;
    const timer = setTimeout(() => track({ type: 'search', payload: { q: query.trim(), category, results: filtered.length } }), 800);
    return () => clearTimeout(timer);
  }, [loading, query, category, filtered.length]);

  if (loading) return <div role="status" aria-live="polite" className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">{Array.from({ length: 6 }, (_, index) => <div key={index} className="h-[30rem] animate-pulse rounded-3xl bg-[#efe5d5]" />)}<span className="sr-only">Loading products</span></div>;

  if (error) return <div role="alert" className="rounded-3xl border border-[#e7dac8] bg-white/70 p-10 text-center"><h2 className="text-2xl font-semibold">Collection unavailable</h2><p className="mt-3 text-[#6f625a]">{error}</p><button type="button" onClick={() => { setLoading(true); setError(null); setRequest((value) => value + 1); }} className="mt-6 rounded-full bg-[#2f241f] px-6 py-3 font-semibold text-white">Try again</button></div>;

  return <div className="space-y-8">
    <div className="grid gap-4 rounded-3xl border border-[#e7dac8] bg-white/70 p-5 md:grid-cols-[1fr_auto_auto]">
      <div><label htmlFor="product-search" className="mb-2 block text-sm font-semibold">Search</label><input id="product-search" type="search" value={query} onChange={(event) => updateFilters(() => setQuery(event.target.value))} placeholder="Search by name or material" className="w-full rounded-xl border border-[#d8c8b4] bg-white px-4 py-3" /></div>
      <CategoryFilter value={category} onChange={(next) => updateFilters(() => setCategory(next))} />
      <div><label htmlFor="sort" className="mb-2 block text-sm font-semibold">Sort by</label><select id="sort" value={sort} onChange={(event) => updateFilters(() => setSort(event.target.value as CatalogSort))} className="w-full rounded-xl border border-[#d8c8b4] bg-white px-4 py-3"><option value="newest">Newest</option><option value="name">Name</option><option value="price_asc">Price: low to high</option><option value="price_desc">Price: high to low</option></select></div>
    </div>

    <p className="text-sm text-[#6f625a]" aria-live="polite">{filtered.length} product{filtered.length === 1 ? '' : 's'} found{nextCursor ? ' so far' : ''}</p>
    {products.length === 0 ? <div className="rounded-3xl border border-[#e7dac8] bg-white/70 p-10 text-center"><h2 className="text-2xl font-semibold">The collection is being prepared</h2><p className="mt-3 text-[#6f625a]">Please check back soon for available shawls and stoles.</p></div> : visible.length === 0 ? <div className="rounded-3xl border border-[#e7dac8] bg-white/70 p-10 text-center"><h2 className="text-2xl font-semibold">No matching products</h2><p className="mt-3 text-[#6f625a]">Try a different search or category.</p><button type="button" onClick={() => { setQuery(''); setCategory('all'); setPage(1); }} className="mt-6 rounded-full border border-[#2f241f] px-6 py-3 font-semibold">Clear filters</button></div> : <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">{visible.map((product, index) => <Link key={product.id || product.slug} href={`/product/${product.slug}`} onClick={() => track({ type: 'click', payload: { product_id: product.id, slug: product.slug, position: (page - 1) * PAGE_SIZE + index } })} className="group overflow-hidden rounded-3xl border border-[#e7dac8] bg-white shadow-sm transition hover:-translate-y-1 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2f241f]"><div className="relative aspect-[3/4] overflow-hidden bg-[#efe5d5]"><Image src={product.images[0]} alt={product.name} fill sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw" className="object-cover transition duration-500 group-hover:scale-105" /></div><div className="space-y-3 p-5"><p className="text-xs font-semibold uppercase tracking-[0.25em] text-[#9a6b3f]">{product.category}</p><h2 className="line-clamp-2 text-xl font-semibold">{product.name}</h2><p className="text-lg font-semibold">{formatCurrency(product.price, product.currency)}</p><p className="text-sm text-[#6f625a]">{product.stock > 0 ? `${product.variants.length || 1} option${product.variants.length === 1 ? '' : 's'}` : 'Currently out of stock'}</p></div></Link>)}</div>}

    {filtered.length > PAGE_SIZE && <nav aria-label="Product pages" className="flex items-center justify-center gap-4"><button type="button" disabled={page === 1} onClick={() => setPage((value) => Math.max(1, value - 1))} className="rounded-full border border-[#2f241f] px-5 py-2 disabled:opacity-40">Previous</button><span className="text-sm">Page {page} of {pageCount}</span><button type="button" disabled={page === pageCount} onClick={() => setPage((value) => Math.min(pageCount, value + 1))} className="rounded-full border border-[#2f241f] px-5 py-2 disabled:opacity-40">Next</button></nav>}
    {nextCursor && <div className="text-center">{moreError && <p role="alert" className="mb-3 text-sm text-[#6f625a]">We could not load more products. Please try again.</p>}<button type="button" disabled={loadingMore} onClick={loadMore} className="rounded-full border border-[#2f241f] px-6 py-3 font-semibold disabled:opacity-40">{loadingMore ? 'Loading…' : 'Load more products'}</button></div>}
  </div>;
}
