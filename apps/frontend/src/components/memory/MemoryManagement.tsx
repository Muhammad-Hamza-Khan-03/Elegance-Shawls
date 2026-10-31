'use client';

import { useCallback, useEffect, useState } from 'react';
import { memoryApi, type Consent, type MemoryItem, type MemoryApiError } from '@/lib/memory';

const policyText = 'Memory is optional, explicit, and minimised. No model or provider infers memories; only values you choose to save are shown here.';

export function MemoryManagement() {
  const [consent, setConsent] = useState<Consent | null>(null);
  const [items, setItems] = useState<MemoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loginRequired, setLoginRequired] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState({ value: '', reason: '' });
  const [fresh, setFresh] = useState<{ category: MemoryItem['category']; key: string; value: string; reason: string }>({ category: 'preference', key: '', value: '', reason: '' });

  const load = useCallback(async () => {
    setLoading(true); setError(null); setLoginRequired(false);
    try {
      const current = await memoryApi.getConsent();
      setConsent(current);
      if (current.granted) setItems((await memoryApi.list()).items);
      else setItems([]);
    } catch (caught) {
      const failure = caught as MemoryApiError;
      if (failure.status === 401) setLoginRequired(true);
      else setError(failure.message || 'Could not load memory.');
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer); }, [load]);

  const changeConsent = async (granted: boolean) => {
    setBusy('consent'); setError(null);
    try { setConsent(await memoryApi.setConsent(granted)); if (granted) setItems((await memoryApi.list()).items); else setItems([]); }
    catch (caught) { const failure = caught as MemoryApiError; if (failure.status === 401) setLoginRequired(true); else setError(failure.message); }
    finally { setBusy(null); }
  };

  const update = async (item: MemoryItem) => {
    setBusy(item.id); setError(null);
    try { const next = await memoryApi.update(item.id, draft.value, draft.reason); setItems((all) => all.map((entry) => entry.id === item.id ? next : entry)); setEditing(null); }
    catch (caught) { setError((caught as Error).message); }
    finally { setBusy(null); }
  };

  const remove = async (item: MemoryItem) => {
    if (!window.confirm('Delete this saved memory? This cannot be undone.')) return;
    setBusy(item.id); setError(null);
    try { await memoryApi.remove(item.id); setItems((all) => all.filter((entry) => entry.id !== item.id)); }
    catch (caught) { setError((caught as Error).message); }
    finally { setBusy(null); }
  };

  const add = async () => {
    setBusy('add'); setError(null);
    try {
      const made = await memoryApi.create({ category: fresh.category, key: fresh.key.trim(), value: fresh.value, ...(fresh.reason.trim() ? { reason: fresh.reason } : {}) });
      setItems((all) => [made, ...all.filter((entry) => entry.id !== made.id)]);
      setFresh({ category: 'preference', key: '', value: '', reason: '' });
    } catch (caught) {
      const failure = caught as MemoryApiError;
      setError(failure.reason === 'duplicate_key' ? 'You already saved something with that name. Correct or delete it first.'
        : failure.reason === 'limit_reached' ? 'You have reached the limit of saved memories. Delete one to add another.'
        : failure.reason === 'consent_required' ? 'Turn memory on first.'
        : failure.status === 422 || failure.status === 400 ? 'That was not accepted. Use a short name like favourite_colour, and no emails or phone numbers.' : failure.message);
    } finally { setBusy(null); }
  };

  const removeAll = async () => {
    if (!window.confirm('Delete all saved memories? This cannot be undone.')) return;
    setBusy('all'); setError(null);
    try { await memoryApi.removeAll(); setItems([]); }
    catch (caught) { setError((caught as Error).message); }
    finally { setBusy(null); }
  };

  return <main id="main-content" className="mx-auto max-w-4xl space-y-8 px-6 py-12">
    <header className="space-y-3"><p className="text-xs font-bold uppercase tracking-[0.3em] text-[#9a6b3f]">Your privacy</p><h1 className="font-heading text-4xl font-semibold">Manage saved memory</h1><p className="max-w-2xl leading-7 text-[#6f625a]">Review, correct, or erase information you explicitly chose to save. We do not select a customer or infer information in this page.</p></header>
    <aside className="rounded-2xl border border-[#e7dac8] bg-[#fbf7f0] p-5 text-sm leading-6" aria-label="Memory retention and provider policy">{policyText} Retention is limited and shown on each entry. Provider policy: explicit-only, no-training storage; policy version is provided by the authenticated service.</aside>
    {loading && <p role="status">Loading your memory…</p>}
    {loginRequired && <section className="rounded-2xl border border-[#e7dac8] bg-white p-6" role="alert"><h2 className="text-xl font-semibold">Sign in required</h2><p className="mt-2 text-[#6f625a]">Sign in to manage your saved memory. No memory details were loaded.</p></section>}
    {error && <p role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</p>}
    {!loading && !loginRequired && consent && <>
      <section className="rounded-2xl border border-[#e7dac8] bg-white p-6"><div className="flex flex-wrap items-center justify-between gap-4"><div><h2 className="text-xl font-semibold">Explicit consent</h2><p className="mt-1 text-sm text-[#6f625a]">{consent.granted ? 'Saving memory is enabled.' : 'Saving memory is off by default.'} Policy version: {consent.policy_version}</p></div><button type="button" disabled={busy === 'consent'} onClick={() => void changeConsent(!consent.granted)} className="rounded-full bg-[#2f241f] px-5 py-2 text-sm font-semibold text-white">{busy === 'consent' ? 'Saving…' : consent.granted ? 'Revoke consent' : 'Opt in to memory'}</button></div></section>
      {consent.granted && <section className="space-y-4"><form aria-label="Add a memory" className="space-y-3 rounded-2xl border border-[#e7dac8] bg-white p-6" onSubmit={(event) => { event.preventDefault(); void add(); }}><h2 className="text-xl font-semibold">Add a memory</h2><p className="text-sm text-[#6f625a]">Only what you type here is saved. Do not include emails or phone numbers.</p><div className="grid gap-3 sm:grid-cols-2"><label className="block text-sm font-semibold">Type<select className="mt-1 block w-full rounded-xl border p-2" value={fresh.category} onChange={(event) => setFresh({ ...fresh, category: event.target.value as MemoryItem['category'] })}><option value="preference">Preference</option><option value="session_constraint">For this shopping trip</option><option value="purchase_context">Purchase context</option></select></label><label className="block text-sm font-semibold">Name<input required pattern="[a-z][a-z0-9_]{0,63}" placeholder="favourite_colour" className="mt-1 block w-full rounded-xl border p-2" value={fresh.key} onChange={(event) => setFresh({ ...fresh, key: event.target.value })} /></label></div><label className="block text-sm font-semibold">Value<input required maxLength={200} placeholder="brown" className="mt-1 block w-full rounded-xl border p-2" value={fresh.value} onChange={(event) => setFresh({ ...fresh, value: event.target.value })} /></label><label className="block text-sm font-semibold">Reason (optional)<input maxLength={200} className="mt-1 block w-full rounded-xl border p-2" value={fresh.reason} onChange={(event) => setFresh({ ...fresh, reason: event.target.value })} /></label><button type="submit" disabled={busy === 'add'} className="rounded-full bg-[#2f241f] px-5 py-2 text-sm font-semibold text-white">{busy === 'add' ? 'Saving…' : 'Save memory'}</button></form><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-2xl font-semibold">Saved memories</h2>{items.length > 0 && <button type="button" onClick={() => void removeAll()} disabled={busy === 'all'} className="rounded-full border border-red-300 px-4 py-2 text-sm text-red-800">{busy === 'all' ? 'Deleting…' : 'Delete all'}</button>}</div>
        {items.length === 0 && <p className="rounded-2xl border border-dashed border-[#d8c8b4] p-6 text-[#6f625a]">You have no saved memories. Nothing is suggested or created automatically.</p>}
        <ul className="space-y-4">{items.map((item) => <li key={item.id} className="rounded-2xl border border-[#e7dac8] bg-white p-6"><div className="flex flex-wrap justify-between gap-3"><div><h3 className="font-semibold">{item.key}</h3><p className="mt-1 text-sm text-[#6f625a]">{item.value}</p></div><span className="rounded-full bg-[#fbf7f0] px-3 py-1 text-xs">{item.category}</span></div><dl className="mt-4 grid gap-2 text-sm text-[#6f625a] sm:grid-cols-2"><div><dt className="font-semibold text-[#2f241f]">Source</dt><dd>{item.source}{item.source_ref ? ` · ${item.source_ref}` : ''}</dd></div><div><dt className="font-semibold text-[#2f241f]">Reason</dt><dd>{item.reason || 'Not provided'}</dd></div><div><dt className="font-semibold text-[#2f241f]">Retention</dt><dd>{item.retention_days} days · expires {new Date(item.expires_at).toLocaleDateString()}</dd></div><div><dt className="font-semibold text-[#2f241f]">Provider policy</dt><dd>Explicit-only · no training</dd></div></dl><div className="mt-5 flex flex-wrap gap-2"><button type="button" onClick={() => { setEditing(item.id); setDraft({ value: item.value, reason: item.reason || '' }); }} className="rounded-full border px-4 py-2 text-sm">Correct</button><button type="button" onClick={() => void remove(item)} disabled={busy === item.id} className="rounded-full border border-red-300 px-4 py-2 text-sm text-red-800">Delete</button></div>{editing === item.id && <form className="mt-4 space-y-3 border-t pt-4" onSubmit={(event) => { event.preventDefault(); void update(item); }}><label className="block text-sm font-semibold">Value<input className="mt-1 block w-full rounded-xl border p-2" value={draft.value} onChange={(event) => setDraft({ ...draft, value: event.target.value })} /></label><label className="block text-sm font-semibold">Reason<input className="mt-1 block w-full rounded-xl border p-2" value={draft.reason} onChange={(event) => setDraft({ ...draft, reason: event.target.value })} /></label><div className="flex gap-2"><button type="submit" disabled={busy === item.id} className="rounded-full bg-[#2f241f] px-4 py-2 text-sm text-white">Save correction</button><button type="button" onClick={() => setEditing(null)} className="rounded-full border px-4 py-2 text-sm">Cancel</button></div></form>}</li>)}</ul></section>}
    </>}
  </main>;
}
