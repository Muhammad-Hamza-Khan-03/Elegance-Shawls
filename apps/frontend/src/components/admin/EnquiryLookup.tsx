'use client';

import { FormEvent, useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { formatCurrency } from '@/lib/whatsapp';
import { adminFetch, DISABLED_NOTICE, type TimelineMessage } from '@/lib/whatsapp-admin';

export type Enquiry = {
  reference: string;
  currency: string;
  total: number;
  created_at: string;
  status?: string;
  items: Array<{ product: string; color?: string | null; size?: string | null; quantity: number; unit_price: number }>;
};

const Timeline = ({ reference }: { reference: string }) => {
  const [messages, setMessages] = useState<TimelineMessage[] | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = async () => {
    const result = await adminFetch<{ items: TimelineMessage[] }>(`/api/admin/enquiries/${encodeURIComponent(reference)}/whatsapp`);
    if (result.ok) { setMessages(result.data.items); setNotice(null); }
    else setNotice(result.disabled ? DISABLED_NOTICE : result.message);
  };

  return (
    <div className="mt-4 border-t border-[#e7dac8] pt-4">
      <Button type="button" variant="outline" className="rounded-full" onClick={() => void load()}>Show WhatsApp chat</Button>
      {notice && <p className="mt-3 text-sm text-[#6f625a]">{notice}</p>}
      {messages?.length === 0 && <p className="mt-3 text-sm text-[#6f625a]">No messages linked to this enquiry yet.</p>}
      <ul className="mt-3 space-y-2">
        {messages?.map((m) => (
          <li key={m.id} className={`max-w-xl rounded-2xl px-4 py-2 text-sm ${m.sent_by === 'customer' ? 'bg-white' : m.sent_by === 'bot' ? 'ml-auto bg-[#efe3d1]' : 'ml-auto bg-[#e1ecdd]'}`}>
            <p className="text-xs font-semibold uppercase tracking-wide text-[#9a6b3f]">{m.sent_by} · {new Date(m.sent_at).toLocaleString()}</p>
            <p className="whitespace-pre-wrap">{m.text ?? `(${m.type})`}</p>
          </li>
        ))}
      </ul>
    </div>
  );
};

// Read-only: a reference is a record of what a customer was about to send on WhatsApp, not an order.
export const EnquiryLookup = () => {
  const [reference, setReference] = useState('');
  const [enquiries, setEnquiries] = useState<Enquiry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (lookup: string) => {
    setError(null);
    try {
      const response = await fetch(`/api/admin/enquiries${lookup ? `?reference=${encodeURIComponent(lookup)}` : ''}`, { cache: 'no-store' });
      if (!response.ok) throw new Error(response.status === 401 ? 'Your session has expired. Sign in again.' : 'Could not load enquiries.');
      setEnquiries(await response.json());
    } catch (caught) {
      setEnquiries(null);
      setError(caught instanceof Error ? caught.message : 'Could not load enquiries.');
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(''), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void load(reference.trim());
  };

  return (
    <main id="main-content" className="space-y-8">
      <section className="rounded-[2rem] border border-[#e7dac8] bg-white p-8 shadow-sm">
        <p className="text-xs font-bold uppercase tracking-[0.3em] text-[#9a6b3f]">Enquiries</p>
        <h1 className="font-heading mt-3 text-4xl font-semibold tracking-tight">WhatsApp enquiry references</h1>
        <p className="mt-4 max-w-3xl leading-7 text-[#6f625a]">
          A reference is issued when a customer opens WhatsApp from the cart. It records the cart as it was validated; it is not an order, a reservation or a confirmation.
        </p>
        <form onSubmit={submit} className="mt-6 flex flex-wrap gap-3">
          <label className="sr-only" htmlFor="enquiry-reference">Enquiry reference</label>
          <input id="enquiry-reference" value={reference} onChange={(event) => setReference(event.target.value)} placeholder="ES-7F3K9Q" maxLength={20}
            className="w-56 rounded-full border border-[#d8c8b4] bg-[#fbf7f0] px-4 py-2 uppercase" />
          <Button type="submit" className="rounded-full bg-[#2f241f] px-6 text-white">Look up</Button>
          {reference && <Button type="button" variant="outline" className="rounded-full" onClick={() => { setReference(''); void load(''); }}>Show latest</Button>}
        </form>
      </section>

      {error && <p role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</p>}
      {enquiries?.length === 0 && <p className="text-[#6f625a]">No enquiry found.</p>}
      <ul className="space-y-4">
        {enquiries?.map((enquiry) => (
          <li key={enquiry.reference} className="rounded-[1.75rem] border border-[#e7dac8] bg-[#fbf7f0] p-6">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="font-mono text-xl font-semibold">{enquiry.reference}{enquiry.status && enquiry.status !== 'handed_off' ? <span className="ml-3 rounded-full bg-[#e1ecdd] px-3 py-1 font-sans text-xs font-medium uppercase tracking-wide">{enquiry.status}</span> : null}</h2>
              <p className="text-sm text-[#6f625a]">{new Date(enquiry.created_at).toLocaleString()}</p>
            </div>
            <ul className="mt-3 space-y-1 text-sm">
              {enquiry.items.map((item, index) => (
                <li key={index}>
                  {item.product}{[item.color, item.size].filter(Boolean).length ? ` (${[item.color, item.size].filter(Boolean).join(' / ')})` : ''} × {item.quantity} @ {formatCurrency(item.unit_price, enquiry.currency)}
                </li>
              ))}
            </ul>
            <p className="mt-3 font-semibold">Total: {formatCurrency(enquiry.total, enquiry.currency)}</p>
            <Timeline reference={enquiry.reference} />
          </li>
        ))}
      </ul>
    </main>
  );
};
