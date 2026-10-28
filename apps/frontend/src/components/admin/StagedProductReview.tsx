'use client';

import { useCallback, useEffect, useState } from 'react';
import { Archive, Check, Eye, EyeOff, Loader2, Plus, RefreshCcw, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
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

export const StagedProductCard = ({ item, busy = false, onAction, suggest = fetchPkrSuggestion }: CardProps) => {
  const [suggestion, setSuggestion] = useState<PkrSuggestion | null>(null);
  const [suggestError, setSuggestError] = useState<string | null>(null);
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

  return (
    <article className="rounded-3xl border border-[#e7dac8] bg-white p-5" data-testid="staged-product">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-heading text-xl font-semibold">{item.product.name}</h3>
          <p className="mt-1 text-sm text-[#6f625a]">
            Source: {item.source_name} ·{' '}
            <a className="break-all underline" href={item.source_url} target="_blank" rel="noreferrer noopener">
              {item.source_url}
            </a>
          </p>
        </div>
        <span className="rounded-full bg-[#f4ebe0] px-3 py-1 text-xs font-bold uppercase tracking-wide" data-testid="staged-status">
          {statusLabel(item.status)}
        </span>
      </div>

      <div className="mt-4 flex gap-2 overflow-x-auto">
        {item.product.images.slice(0, 6).map((src) => (
          // Remote, untrusted image: plain <img> so Next's optimizer never fetches it server-side.
          // eslint-disable-next-line @next/next/no-img-element
          <img key={src} src={src} alt="" loading="lazy" referrerPolicy="no-referrer" className="h-24 w-24 rounded-xl object-cover" />
        ))}
      </div>

      {item.product.main_description ? <p className="mt-4 text-sm leading-6">{item.product.main_description}</p> : null}

      <dl className="mt-4 grid gap-2 text-sm sm:grid-cols-2">
        <div><dt className="font-semibold">Source price</dt><dd>{formatSourcePrice(item.source_price, item.source_currency)}</dd></div>
        <div><dt className="font-semibold">Stock</dt><dd>{item.stock_known ? 'Set by reviewer' : 'Unknown — reviewer must set'}</dd></div>
        <div><dt className="font-semibold">Category</dt><dd>{item.product.category}</dd></div>
        <div><dt className="font-semibold">Material</dt><dd>{item.product.material ?? '—'}</dd></div>
      </dl>

      {item.missing_fields.length > 0 ? (
        <div className="mt-4 rounded-2xl border border-amber-300 bg-amber-50 p-3 text-sm" data-testid="missing-fields">
          <p className="font-semibold">Missing or needs review</p>
          <ul className="mt-1 list-disc pl-5">{item.missing_fields.map((field) => <li key={field}>{describeMissing(field)}</li>)}</ul>
        </div>
      ) : null}
      {item.latest_source_hash ? (
        <p className="mt-3 text-sm text-amber-800">The source changed after review. The changes were not applied.</p>
      ) : null}
      {item.rejection_reason ? <p className="mt-3 text-sm text-red-700">Rejected: {item.rejection_reason}</p> : null}

      {actions.includes('approve') && (suggestion || suggestError) ? (
        <div className="mt-4 rounded-2xl border border-[#d8c8b4] bg-[#faf5ee] p-3 text-sm" data-testid="pkr-suggestion">
          {suggestion ? (
            <>
              <p className="font-semibold">{formatSuggestion(suggestion)}</p>
              <p className="mt-1 text-[#6f625a]">{suggestion.note}</p>
              <Button type="button" variant="outline" className="mt-2" onClick={() => setPrice(String(suggestion.suggested_pkr))}>Use as starting price</Button>
            </>
          ) : <p role="alert" className="text-red-700">{suggestError}</p>}
        </div>
      ) : null}

      {actions.length > 0 ? (
        <div className="mt-5 flex flex-wrap items-end gap-3">
          {actions.includes('approve') ? (
            <fieldset className="flex flex-wrap items-end gap-2" disabled={busy}>
              <label className="text-sm">Retail price (PKR)
                <input className="mt-1 block w-32 rounded-lg border border-[#d8c8b4] px-2 py-1" inputMode="numeric" value={price} onChange={(e) => setPrice(e.target.value)} />
              </label>
              {canSuggest ? <Button type="button" variant="outline" onClick={() => void loadSuggestion()}>Suggest from source price</Button> : null}
              <label className="text-sm">Stock
                <input className="mt-1 block w-20 rounded-lg border border-[#d8c8b4] px-2 py-1" inputMode="numeric" value={stock} onChange={(e) => setStock(e.target.value)} />
              </label>
              <Button disabled={busy || !approveReady} onClick={() => fire('approve', { price: priceValue, stock: Number(stock) })}>
                <Check className="h-4 w-4" /> Approve
              </Button>
            </fieldset>
          ) : null}
          {actions.includes('reject') ? (
            <fieldset className="flex flex-wrap items-end gap-2" disabled={busy}>
              <label className="text-sm">Rejection reason
                <input className="mt-1 block w-56 rounded-lg border border-[#d8c8b4] px-2 py-1" value={reason} onChange={(e) => setReason(e.target.value)} />
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
        </div>
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
        <p className="mt-2 text-sm text-[#6f625a]">Imported products stay hidden until approved and published here.</p>
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

      <div className="space-y-4">
        {!loading && items.length === 0 && !error ? <p className="text-sm text-[#6f625a]">No staged products for this filter.</p> : null}
        {items.map((item) => <StagedProductCard key={item._id} item={item} busy={busyId === item._id} onAction={act} />)}
      </div>
    </section>
  );
};
