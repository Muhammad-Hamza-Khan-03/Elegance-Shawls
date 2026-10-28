'use client';

import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { Archive, Check, Eye, EyeOff, Loader2, Plus, RefreshCcw, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { MarkdownText } from '@/components/admin/MarkdownText';
import { CATEGORY_LABELS } from '@/lib/categories';
import {
  STAGED_STATUSES,
  availableActions,
  describeMissing,
  formatSourcePrice,
  fetchPkrSuggestion,
  formatSuggestion,
  listStaged,
  queueProductPath,
  runStagedAction,
  type ActionBody,
  type PkrSuggestion,
  type StagedAction,
  type StagedProduct,
  type StagedStatus,
} from '@/lib/staging';

const statusLabel = (status: StagedStatus) => status.replace('_', ' ');

type CardProps = {
  item: StagedProduct;
  busy?: boolean;
  onAction?: (item: StagedProduct, action: StagedAction, body?: ActionBody) => void;
  suggest?: (id: string) => Promise<PkrSuggestion>;
};

const sourceLabel = (url: string) => {
  try {
    const parsed = new URL(url);
    return `${parsed.hostname}${parsed.pathname}`;
  } catch {
    return url;
  }
};

const categoryLabel = (key: string) =>
  (CATEGORY_LABELS as Record<string, string>)[key] ?? key.charAt(0).toUpperCase() + key.slice(1);

const Fact = ({ label, children, muted = false }: { label: string; children: ReactNode; muted?: boolean }) => (
  <div className="rounded-2xl border border-[#efe4d3] bg-[#fdfaf5] px-4 py-3">
    <dt className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#9a6b3f]">{label}</dt>
    <dd className={`mt-1 text-sm ${muted ? 'text-[#8a7b70]' : 'font-medium text-[#2f241f]'}`}>{children}</dd>
  </div>
);

export const StagedProductCard = ({ item, busy = false, onAction, suggest = fetchPkrSuggestion }: CardProps) => {
  const [suggestion, setSuggestion] = useState<PkrSuggestion | null>(null);
  const [suggestError, setSuggestError] = useState<string | null>(null);
  const [selected, setSelected] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const canSuggest = item.source_price != null && Boolean(item.source_currency);
  const loadSuggestion = async () => {
    setSuggestError(null);
    try {
      setSuggestion(await suggest(item._id));
    } catch (err) {
      setSuggestion(null);
      setSuggestError(err instanceof Error ? err.message : 'Could not get an exchange rate.');
    }
  };
  const [price, setPrice] = useState('');
  const [stock, setStock] = useState('0');
  const [reason, setReason] = useState('');
  const actions = availableActions(item.status);
  const priceValue = Number(price);
  const approveReady = price.trim() !== '' && Number.isInteger(priceValue) && priceValue >= 0 && Number.isInteger(Number(stock)) && Number(stock) >= 0;
  const rejectReady = reason.trim().length >= 3;
  const fire = (action: StagedAction, body?: ActionBody) => onAction?.(item, action, body);
  const images = item.product.images.length ? item.product.images : [item.product.cover_image_url].filter(Boolean);
  const current = images[Math.min(selected, Math.max(images.length - 1, 0))];
  const description = item.product.main_description ?? '';
  const longDescription = description.length > 700;
  const field = (value?: string | null) => (value ? value : <span aria-label="not provided">Not provided</span>);

  return (
    <article className="overflow-hidden rounded-3xl border border-[#e7dac8] bg-white shadow-sm" data-testid="staged-product">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-[#efe4d3] bg-[#fbf7f1] px-6 py-5">
        <div className="min-w-0 space-y-2">
          <span className="inline-block rounded-full bg-[#2f241f] px-3 py-0.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-white">
            {categoryLabel(item.product.category)}
          </span>
          <h3 className="font-heading text-2xl font-semibold leading-tight text-[#2f241f]">{item.product.name}</h3>
          <p className="text-sm text-[#6f625a]">
            {item.source_name} ·{' '}
            <a className="break-all underline decoration-[#c9a577] underline-offset-2 hover:text-[#2f241f]" href={item.source_url} target="_blank" rel="noreferrer noopener" title={item.source_url}>
              {sourceLabel(item.source_url)}
            </a>
            <span className="sr-only"> ({item.source_url})</span>
          </p>
        </div>
        <span className="rounded-full border border-[#e2d2bb] bg-white px-3 py-1 text-xs font-bold uppercase tracking-wide text-[#2f241f]" data-testid="staged-status">
          {statusLabel(item.status)}
        </span>
      </header>

      <div className="grid gap-6 p-6 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
        <div className="space-y-3">
          {current ? (
            <div className="overflow-hidden rounded-2xl border border-[#efe4d3] bg-[#f6efe4]">
              {/* Remote, untrusted image: plain <img> so Next's optimizer never fetches it server-side. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={current} alt={`${item.product.name} — photo ${selected + 1} of ${images.length}`} referrerPolicy="no-referrer" className="aspect-[4/5] w-full object-cover" />
            </div>
          ) : null}
          {images.length > 1 ? (
            <ul className="flex flex-wrap gap-2" aria-label="Product photos">
              {images.slice(0, 12).map((src, index) => (
                <li key={src}>
                  <button type="button" onClick={() => setSelected(index)} aria-label={`Show photo ${index + 1}`} aria-current={index === selected}
                    className={`block overflow-hidden rounded-xl border-2 ${index === selected ? 'border-[#2f241f]' : 'border-transparent opacity-80 hover:opacity-100'}`}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={src} alt="" loading="lazy" referrerPolicy="no-referrer" className="h-14 w-14 object-cover" />
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>

        <div className="min-w-0 space-y-5">
          <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <Fact label="Source price">{formatSourcePrice(item.source_price, item.source_currency)}</Fact>
            <Fact label="Stock" muted={!item.stock_known}>{item.stock_known ? 'Set by reviewer' : 'Unknown — reviewer must set'}</Fact>
            <Fact label="Category">{categoryLabel(item.product.category)}</Fact>
            <Fact label="Material" muted={!item.product.material}>{field(item.product.material)}</Fact>
            <Fact label="Size" muted={!item.product.sizing}>{field(item.product.sizing)}</Fact>
            <Fact label="Weight" muted={!item.product.weight}>{field(item.product.weight)}</Fact>
          </dl>

          {item.missing_fields.length > 0 ? (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm" data-testid="missing-fields">
              <p className="font-semibold text-amber-900">Needs your attention</p>
              <ul className="mt-2 flex flex-wrap gap-2">
                {item.missing_fields.map((missing) => (
                  <li key={missing} className="rounded-full border border-amber-300 bg-white px-3 py-0.5 text-xs text-amber-900">{describeMissing(missing)}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {item.latest_source_hash ? (
            <p className="rounded-2xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">The source changed after review. The changes were not applied.</p>
          ) : null}
          {item.rejection_reason ? <p className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">Rejected: {item.rejection_reason}</p> : null}

          {description ? (
            <section aria-labelledby={`desc-${item._id}`}>
              <h4 id={`desc-${item._id}`} className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#9a6b3f]">Description</h4>
              <div className={`relative rounded-2xl border border-[#efe4d3] bg-white px-5 py-4 ${longDescription && !expanded ? 'max-h-72 overflow-hidden' : ''}`}>
                <MarkdownText text={description} />
                {longDescription && !expanded ? <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-white to-transparent" /> : null}
              </div>
              {longDescription ? (
                <button type="button" className="mt-2 text-sm font-semibold text-[#2f241f] underline underline-offset-2" aria-expanded={expanded} onClick={() => setExpanded((open) => !open)}>
                  {expanded ? 'Show less' : 'Read full description'}
                </button>
              ) : null}
            </section>
          ) : null}
        </div>
      </div>

      {actions.includes('approve') && (suggestion || suggestError) ? (
        <div className="mx-6 mb-4 rounded-2xl border border-[#d8c8b4] bg-[#faf5ee] p-4 text-sm" data-testid="pkr-suggestion">
          {suggestion ? (
            <>
              <p className="font-semibold">{formatSuggestion(suggestion)}</p>
              <p className="mt-1 text-[#6f625a]">{suggestion.note}</p>
              <Button type="button" variant="outline" className="mt-3" onClick={() => setPrice(String(suggestion.suggested_pkr))}>Use as starting price</Button>
            </>
          ) : <p role="alert" className="text-red-700">{suggestError}</p>}
        </div>
      ) : null}

      {actions.length > 0 ? (
        <footer className="flex flex-wrap items-end gap-x-8 gap-y-4 border-t border-[#efe4d3] bg-[#fbf7f1] px-6 py-5">
          {actions.includes('approve') ? (
            <fieldset className="flex flex-wrap items-end gap-3" disabled={busy}>
              <legend className="sr-only">Approve</legend>
              <label className="text-xs font-semibold uppercase tracking-wide text-[#6f625a]">Retail price (PKR)
                <input className="mt-1 block w-36 rounded-xl border border-[#d8c8b4] bg-white px-3 py-2 text-sm normal-case tracking-normal text-[#2f241f]" inputMode="numeric" value={price} onChange={(e) => setPrice(e.target.value)} />
              </label>
              {canSuggest ? <Button type="button" variant="outline" onClick={() => void loadSuggestion()}>Suggest from source price</Button> : null}
              <label className="text-xs font-semibold uppercase tracking-wide text-[#6f625a]">Stock
                <input className="mt-1 block w-24 rounded-xl border border-[#d8c8b4] bg-white px-3 py-2 text-sm normal-case tracking-normal text-[#2f241f]" inputMode="numeric" value={stock} onChange={(e) => setStock(e.target.value)} />
              </label>
              <Button disabled={busy || !approveReady} onClick={() => fire('approve', { price: priceValue, stock: Number(stock) })}>
                <Check className="h-4 w-4" /> Approve
              </Button>
            </fieldset>
          ) : null}
          {actions.includes('reject') ? (
            <fieldset className="flex flex-wrap items-end gap-3 sm:ml-auto" disabled={busy}>
              <label className="text-xs font-semibold uppercase tracking-wide text-[#6f625a]">Rejection reason
                <input className="mt-1 block w-60 rounded-xl border border-[#d8c8b4] bg-white px-3 py-2 text-sm normal-case tracking-normal text-[#2f241f]" value={reason} onChange={(e) => setReason(e.target.value)} />
              </label>
              <Button variant="outline" disabled={busy || !rejectReady} onClick={() => fire('reject', { reason: reason.trim() })}>
                <X className="h-4 w-4" /> Reject
              </Button>
            </fieldset>
          ) : null}
          {actions.includes('publish') ? (
            <Button disabled={busy} onClick={() => fire('publish')}><Eye className="h-4 w-4" /> Publish</Button>
          ) : null}
          {actions.includes('unpublish') ? (
            <Button variant="outline" disabled={busy} onClick={() => fire('unpublish')}><EyeOff className="h-4 w-4" /> Unpublish</Button>
          ) : null}
          {actions.includes('archive') ? (
            <Button variant="outline" disabled={busy} onClick={() => fire('archive')}><Archive className="h-4 w-4" /> Archive</Button>
          ) : null}
        </footer>
      ) : null}
    </article>
  );
};

export const StagedProductReview = () => {
  const [items, setItems] = useState<StagedProduct[]>([]);
  const [filter, setFilter] = useState<StagedStatus | 'all'>('pending_review');
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [path, setPath] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems((await listStaged(filter)).items);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load staged products.');
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  const act = async (item: StagedProduct, action: StagedAction, body?: ActionBody) => {
    setBusyId(item._id);
    setNotice(null);
    try {
      await runStagedAction(item._id, action, body);
      setNotice(`${item.product.name}: ${action} succeeded.`);
      setError(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Action failed.');
    } finally {
      setBusyId(null);
    }
  };

  const queue = async () => {
    setNotice(null);
    try {
      const job = await queueProductPath(path.trim());
      setNotice(`Queued job ${job._id} (${job.status}).`);
      setError(null);
      setPath('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not queue the product.');
    }
  };

  return (
    <section className="space-y-6">
      <div>
        <h2 className="font-heading text-3xl font-semibold">Staged products</h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-[#6f625a]">Imported products stay hidden until you approve and publish them. Check the details, set the PKR price and stock, then approve.</p>
      </div>

      <div className="flex flex-wrap items-end gap-3 rounded-3xl border border-[#e7dac8] bg-white p-4">
        <label className="text-sm">Product path on the configured source
          <input className="mt-1 block w-72 rounded-lg border border-[#d8c8b4] px-2 py-1" placeholder="/products/example-handle" value={path} onChange={(e) => setPath(e.target.value)} />
        </label>
        <Button disabled={!path.trim()} onClick={queue}><Plus className="h-4 w-4" /> Queue ingestion</Button>
        <label className="ml-auto text-sm">Status
          <select className="mt-1 block rounded-lg border border-[#d8c8b4] px-2 py-1" value={filter} onChange={(e) => setFilter(e.target.value as StagedStatus | 'all')}>
            <option value="all">All</option>
            {STAGED_STATUSES.map((s) => <option key={s} value={s}>{statusLabel(s)}</option>)}
          </select>
        </label>
        <Button variant="outline" onClick={() => void load()} disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCcw className="h-4 w-4" />} Refresh
        </Button>
      </div>

      {error ? <p role="alert" className="rounded-2xl bg-red-50 p-3 text-sm text-red-800">{error}</p> : null}
      {notice ? <p role="status" className="rounded-2xl bg-green-50 p-3 text-sm text-green-800">{notice}</p> : null}

      <div className="space-y-8">
        {!loading && items.length === 0 && !error ? <p className="text-sm text-[#6f625a]">No staged products for this filter.</p> : null}
        {items.map((item) => <StagedProductCard key={item._id} item={item} busy={busyId === item._id} onAction={act} />)}
      </div>
    </section>
  );
};
