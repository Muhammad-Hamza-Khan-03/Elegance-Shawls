'use client';

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { Archive, Check, Eye, EyeOff, Loader2, Plus, RefreshCcw, Sparkles, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { MarkdownText } from '@/components/common/MarkdownText';
import { CATEGORY_LABELS } from '@/lib/categories';
import {
  STAGED_STATUSES,
  StagingApiError,
  UUID,
  availableActions,
  canRequestEnrichment,
  cancelEnrichment,
  fetchEnrichment,
  isActiveEnrichment,
  requestEnrichment,
  describeMissing,
  formatSourcePrice,
  fetchPkrSuggestion,
  formatSuggestion,
  listStaged,
  queueProductPath,
  runStagedAction,
  type ActionBody,
  type Enrichment,
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

type EnrichmentApi = {
  load: typeof fetchEnrichment;
  request: typeof requestEnrichment;
  cancel: typeof cancelEnrichment;
};
const enrichmentApi: EnrichmentApi = { load: fetchEnrichment, request: requestEnrichment, cancel: cancelEnrichment };

const FIELD_LABELS: Record<string, string> = {
  color_family: 'Colour family', color_name: 'Colour', pattern: 'Pattern', occasion: 'Occasion',
  season: 'Season', style: 'Style', description: 'Description', seo_title: 'SEO title', seo_description: 'SEO description',
};

const fmtTime = (value?: string | null) => (value ? value.replace('T', ' ').replace(/(\.\d+)?(Z|[+-]\d\d:\d\d)?$/, ' UTC') : '—');

type EnrichmentViewProps = {
  stagedStatus: StagedStatus;
  data: Enrichment | null | undefined; // undefined = still loading, null = none requested yet
  busy: boolean;
  error: string | null;
  notice: string | null;
  onRequest: () => void;
  onCancel: () => void;
  onRefresh: () => void;
};

// Read-only and advisory: there is deliberately no apply, edit or auto-fill control here.
export const EnrichmentView = ({ stagedStatus, data, busy, error, notice, onRequest, onCancel, onRefresh }: EnrichmentViewProps) => {
  const canRequest = canRequestEnrichment(stagedStatus, data);
  const meta: [string, string][] = data
    ? [
        ['Provider', data.provider], ['Model', data.model], ['Prompt', data.prompt_version], ['Vocabulary', data.vocabulary_version],
        ['Input hash', data.input_content_hash], ['Attempts', String(data.attempts)], ['Trace', data.trace_id || '—'],
        ['Requested', fmtTime(data.created_at)], ['Started', fmtTime(data.started_at)], ['Finished', fmtTime(data.finished_at)],
      ]
    : [];
  return (
    <section aria-label="Enrichment suggestions" className="mx-6 mb-4 rounded-2xl border border-dashed border-[#c9a577] bg-[#fffdf9] p-4 text-sm" data-testid="enrichment">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#9a6b3f]">Enrichment suggestions</h4>
        <p className="rounded-full bg-amber-100 px-3 py-0.5 text-xs font-semibold text-amber-900">Advisory suggestion — not catalogue truth</p>
      </div>
      <p className="mt-1 text-xs text-[#6f625a]">Nothing here changes the product. Use the review fields to set real values.</p>

      {error ? <p role="alert" className="mt-3 rounded-xl bg-red-50 p-2 text-red-800">{error}</p> : null}
      {notice ? <p role="status" className="mt-3 rounded-xl bg-green-50 p-2 text-green-800">{notice}</p> : null}
      {data === undefined && !error ? <p role="status" className="mt-3 text-[#6f625a]">Loading suggestions…</p> : null}
      {data === null ? <p className="mt-3 text-[#6f625a]" data-testid="enrichment-empty">No suggestions have been requested for this product yet.</p> : null}

      {data ? (
        <div className="mt-3 space-y-3">
          <p>
            <span className="sr-only">Run status: </span>
            <span className="rounded-full border border-[#e2d2bb] bg-white px-3 py-0.5 text-xs font-bold uppercase tracking-wide" data-testid="enrichment-status">{data.status}</span>
            {isActiveEnrichment(data) ? <span role="status" className="ml-2 text-[#6f625a]">Run in progress — refresh to see the result.</span> : null}
          </p>
          {data.status === 'failed' ? (
            <p role="alert" className="rounded-xl bg-red-50 p-2 text-red-800">
              The run failed{data.last_error ? `: ${data.last_error}` : '.'}
            </p>
          ) : null}
          {data.validation_errors.length > 0 ? (
            <div role="alert" className="rounded-xl border border-amber-300 bg-amber-50 p-2 text-amber-900" data-testid="enrichment-warnings">
              <p className="font-semibold">Validation warnings — suggestions were rejected</p>
              <ul className="list-disc pl-5">{data.validation_errors.map((message, i) => <li key={i}>{message}</li>)}</ul>
            </div>
          ) : null}
          {data.suggestions && Object.keys(data.suggestions).length > 0 ? (
            <ul className="grid gap-2 md:grid-cols-2" aria-label="Suggested fields">
              {Object.entries(data.suggestions).map(([name, s]) => (
                <li key={name} className="min-w-0 rounded-xl border border-[#efe4d3] bg-white px-3 py-2" data-testid="enrichment-field">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-[#9a6b3f]">{FIELD_LABELS[name] ?? name}</p>
                  <p className="break-words font-medium text-[#2f241f]">{s.value ?? <span className="text-[#8a7b70]">No suggestion</span>}</p>
                  {s.reason ? <p className="break-words text-xs text-[#6f625a]">Reason: {s.reason}</p> : null}
                  <p className="text-xs text-[#8a7b70]">Source: {s.source}</p>
                </li>
              ))}
            </ul>
          ) : null}
          <dl className="grid gap-x-4 gap-y-1 text-xs text-[#6f625a] sm:grid-cols-2">
            {meta.map(([label, value]) => (
              <div key={label} className="flex min-w-0 gap-1"><dt className="shrink-0 font-semibold">{label}:</dt><dd className="break-all">{value}</dd></div>
            ))}
          </dl>
        </div>
      ) : null}

      <div className="mt-3 flex flex-wrap gap-2">
        {canRequest ? (
          <Button type="button" variant="outline" disabled={busy || data === undefined} onClick={onRequest}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} {data ? 'Request new suggestions' : 'Request suggestions'}
          </Button>
        ) : null}
        {isActiveEnrichment(data) ? (
          <Button type="button" variant="outline" disabled={busy} onClick={onCancel}><X className="h-4 w-4" /> Cancel run</Button>
        ) : null}
        <Button type="button" variant="outline" disabled={busy} onClick={onRefresh}><RefreshCcw className="h-4 w-4" /> Reload suggestions</Button>
      </div>
      {stagedStatus === 'rejected' || stagedStatus === 'archived' ? (
        <p className="mt-2 text-xs text-[#6f625a]">Suggestions cannot be requested for {statusLabel(stagedStatus)} products.</p>
      ) : null}
    </section>
  );
};

export const EnrichmentPanel = ({ stagedId, stagedStatus, api = enrichmentApi }: { stagedId: string; stagedStatus: StagedStatus; api?: EnrichmentApi }) => {
  const [data, setData] = useState<Enrichment | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const inflight = useRef(false); // blocks repeated clicks before React re-renders the disabled button

  const reload = useCallback(async () => {
    try {
      setData(await api.load(stagedId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load suggestions.');
    }
  }, [api, stagedId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reload();
  }, [reload]);

  const run = async (call: () => Promise<Enrichment>, done: string) => {
    if (inflight.current) return;
    inflight.current = true;
    setBusy(true);
    setNotice(null);
    setError(null);
    try {
      setData(await call());
      setNotice(done);
    } catch (err) {
      const status = err instanceof StagingApiError ? err.status : 0;
      const message = err instanceof Error ? err.message : 'Action failed.';
      setError(status === 503 || status === 502 || status === 0 ? `${message} Try again shortly.` : message);
      if (status === 409) await reload(); // someone else changed the run; show what the backend now says
    } finally {
      inflight.current = false;
      setBusy(false);
    }
  };

  return (
    <EnrichmentView
      stagedStatus={stagedStatus}
      data={data}
      busy={busy}
      error={error}
      notice={notice}
      onRequest={() => void run(() => api.request(stagedId), 'Suggestion run requested.')}
      onCancel={() => data && void run(() => api.cancel(stagedId, data.id), 'Suggestion run cancelled.')}
      onRefresh={() => void reload()}
    />
  );
};

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

      {UUID.test(item._id) ? <EnrichmentPanel stagedId={item._id} stagedStatus={item.status} /> : null}

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
      // Follow the product to its next stage so its next action (e.g. Publish after Approve) is on screen.
      const next = { approve: 'approved', publish: 'published', unpublish: 'unpublished', reject: 'rejected', archive: 'archived' } as const;
      setFilter(next[action]);
      setNotice(`${item.product.name}: ${action} succeeded.${action === 'approve' ? ' It is now an inactive draft; use Publish below to make it live.' : ''}`);
      setError(null);
      if (next[action] === filter) await load(); // otherwise the filter change reloads the list
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
