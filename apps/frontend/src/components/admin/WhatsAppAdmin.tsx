'use client';

import { FormEvent, useCallback, useEffect, useState } from 'react';
import QRCode from 'qrcode';
import { Button } from '@/components/ui/button';
import {
  adminFetch, DISABLED_NOTICE, type BridgeStatus, type PairingView, type UnlinkedChat,
} from '@/lib/whatsapp-admin';

const STATE_LABEL: Record<string, string> = {
  connected: 'Connected', connecting: 'Connecting…', pairing: 'Waiting for scan', needs_pairing: 'Needs reconnect',
  misconfigured: 'Misconfigured', unreachable: 'Bridge unreachable',
};

const PairingPanel = ({ connected, number, onChange }: { connected: boolean; number?: string | null; onChange: () => void }) => {
  const [view, setView] = useState<PairingView | null>(null);
  const [qrImage, setQrImage] = useState<string | null>(null);
  const [phone, setPhone] = useState('');
  const [error, setError] = useState<string | null>(null);
  const active = Boolean(view?.pairing);

  const poll = useCallback(async () => {
    const result = await adminFetch<PairingView>('/api/admin/whatsapp/pairing');
    if (!result.ok) { setError(result.message); return; }
    setView(result.data);
    if (result.data.state === 'connected') onChange();
  }, [onChange]);

  // Poll every 2 seconds while a pairing session is open; Baileys rotates the QR and the new one replaces the old.
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => void poll(), 2000);
    return () => window.clearInterval(timer);
  }, [active, poll]);

  // Drawn locally: the QR is a login credential and must never go to an online QR service.
  useEffect(() => {
    const qr = view?.pairing?.qr;
    let cancelled = false;
    if (!qr) { Promise.resolve().then(() => !cancelled && setQrImage(null)); return () => { cancelled = true; }; }
    void QRCode.toDataURL(qr, { margin: 1, width: 240 }).then((url) => !cancelled && setQrImage(url));
    return () => { cancelled = true; };
  }, [view?.pairing?.qr]);

  const act = async (url: string, method: string, body?: unknown) => {
    setError(null);
    const result = await adminFetch<PairingView>(url, { method, body: body ? JSON.stringify(body) : undefined });
    if (!result.ok) { setError(result.message); return; }
    await poll();
    onChange();
  };

  const connect = () => {
    if (connected && !window.confirm('This replaces the linked WhatsApp number. Continue?')) return;
    void act('/api/admin/whatsapp/pairing', 'POST');
  };
  const disconnect = () => {
    if (window.confirm('Log this device out of WhatsApp? The bot stops until you pair again.')) void act('/api/admin/whatsapp/pairing', 'DELETE');
  };
  const useCode = (event: FormEvent) => { event.preventDefault(); void act('/api/admin/whatsapp/pairing/code', 'POST', { phone: phone.replace(/\D/g, '') }); };

  return (
    <div className="mt-6 space-y-4">
      <div className="flex flex-wrap gap-3">
        <Button type="button" className="rounded-full bg-[#2f241f] px-6 text-white" onClick={connect}>{connected ? 'Replace number' : 'Connect WhatsApp'}</Button>
        {connected && <Button type="button" variant="outline" className="rounded-full" onClick={disconnect}>Disconnect {number ? `+${number}` : ''}</Button>}
      </div>
      {error && <p role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>}
      {view?.pairing && (
        <div className="rounded-2xl border border-[#e7dac8] bg-[#fbf7f0] p-5">
          <p className="text-sm text-[#6f625a]">On the shop phone: WhatsApp → Settings → Linked devices → Link a device, then scan. The code expires in 2 minutes.</p>
          {qrImage ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={qrImage} alt="WhatsApp pairing QR code" width={240} height={240} className="mt-4 rounded-xl bg-white p-2" />
          ) : <p className="mt-4 text-sm">Waiting for a QR code…</p>}
          {view.pairing.code ? (
            <p className="mt-4 text-sm">Enter this code on the phone: <span data-testid="pairing-code" className="font-mono text-xl font-semibold tracking-widest">{view.pairing.code}</span></p>
          ) : (
            <form onSubmit={useCode} className="mt-4 flex flex-wrap items-center gap-3">
              <label htmlFor="pairing-phone" className="text-sm font-semibold">Use a code instead</label>
              <input id="pairing-phone" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="923001234567" inputMode="numeric" maxLength={16}
                className="w-48 rounded-full border border-[#d8c8b4] bg-white px-4 py-2" />
              <Button type="submit" variant="outline" className="rounded-full" disabled={phone.replace(/\D/g, '').length < 8}>Get code</Button>
            </form>
          )}
        </div>
      )}
    </div>
  );
};

const UnlinkedList = () => {
  const [items, setItems] = useState<UnlinkedChat[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [refs, setRefs] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async (cursor?: string) => {
    const result = await adminFetch<{ items: UnlinkedChat[]; next_cursor: string | null }>(`/api/admin/whatsapp/unlinked${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''}`);
    if (!result.ok) { setMessage(result.message); return; }
    setItems((current) => (cursor ? [...current, ...result.data.items] : result.data.items));
    setNext(result.data.next_cursor);
  }, []);

  useEffect(() => { const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer); }, [load]);

  const link = async (id: string) => {
    setMessage(null);
    const result = await adminFetch('/api/admin/whatsapp/link', { method: 'POST', body: JSON.stringify({ contact_id: id, enquiry_reference: refs[id]?.trim() }) });
    if (!result.ok) { setMessage(result.status === 409 ? 'That enquiry is already linked to another chat.' : result.status === 404 ? 'No such enquiry or chat.' : result.message); return; }
    setItems((current) => current.filter((chat) => chat.id !== id));
  };

  return (
    <section className="rounded-[2rem] border border-[#e7dac8] bg-white p-8 shadow-sm">
      <h2 className="font-heading text-2xl font-semibold">Unlinked chats</h2>
      <p className="mt-2 text-sm text-[#6f625a]">Chats that arrived without a valid enquiry reference. Attach one by hand to see the conversation on the enquiry.</p>
      {message && <p role="alert" className="mt-4 rounded-2xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">{message}</p>}
      {items.length === 0 && !message && <p className="mt-4 text-[#6f625a]">No unlinked chats.</p>}
      <ul className="mt-4 space-y-3">
        {items.map((chat) => (
          <li key={chat.id} data-testid="unlinked-chat" className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[#e7dac8] bg-[#fbf7f0] p-4">
            <div>
              <p className="font-semibold">{chat.display_name || 'Unknown'} <span className="font-normal text-[#6f625a]">{chat.phone ?? 'no number'}</span></p>
              <p className="text-xs text-[#6f625a]">Last message {new Date(chat.last_seen_at).toLocaleString()}</p>
            </div>
            <div className="flex gap-2">
              <label className="sr-only" htmlFor={`ref-${chat.id}`}>Enquiry reference for {chat.phone ?? 'chat'}</label>
              <input id={`ref-${chat.id}`} value={refs[chat.id] ?? ''} onChange={(e) => setRefs({ ...refs, [chat.id]: e.target.value })} placeholder="ES-7F3K9Q" maxLength={20}
                className="w-40 rounded-full border border-[#d8c8b4] bg-white px-4 py-2 uppercase" />
              <Button type="button" className="rounded-full bg-[#2f241f] text-white" disabled={!refs[chat.id]?.trim()} onClick={() => void link(chat.id)}>Link</Button>
            </div>
          </li>
        ))}
      </ul>
      {next && <Button type="button" variant="outline" className="mt-4 rounded-full" onClick={() => void load(next)}>Load more</Button>}
    </section>
  );
};

export const WhatsAppAdmin = () => {
  const [status, setStatus] = useState<BridgeStatus | null>(null);
  const [disabled, setDisabled] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const result = await adminFetch<BridgeStatus>('/api/admin/whatsapp/status');
    if (result.ok) { setStatus(result.data); setError(null); setDisabled(false); }
    else { setDisabled(result.disabled); setError(result.disabled ? null : result.message); }
  }, []);

  useEffect(() => { const timer = window.setTimeout(() => void refresh(), 0); return () => window.clearTimeout(timer); }, [refresh]);

  return (
    <main id="main-content" className="space-y-8">
      <section className="rounded-[2rem] border border-[#e7dac8] bg-white p-8 shadow-sm">
        <p className="text-xs font-bold uppercase tracking-[0.3em] text-[#9a6b3f]">WhatsApp</p>
        <h1 className="font-heading mt-3 text-4xl font-semibold tracking-tight">WhatsApp automation</h1>
        {disabled && <p data-testid="whatsapp-disabled" className="mt-4 max-w-3xl leading-7 text-[#6f625a]">{DISABLED_NOTICE} To turn it on, set <code>WHATSAPP_BRIDGE_ENABLED=true</code> on the server and restart the WhatsApp services.</p>}
        {error && <p role="alert" className="mt-4 rounded-2xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>}
        {status && (
          <div className="mt-6" data-testid="status-card">
            <p className="text-lg font-semibold">
              {STATE_LABEL[status.state] ?? status.state}{status.state === 'connected' && status.number ? ` as +${status.number}` : ''}
            </p>
            {status.detail && <p className="text-sm text-[#6f625a]">{status.detail}</p>}
            <p className="mt-1 text-sm text-[#6f625a]">
              {status.last_event_at ? `Last message ${new Date(status.last_event_at).toLocaleString()}` : 'No messages yet'}
              {typeof status.stream_lag === 'number' ? ` · ${status.stream_lag} waiting to be processed` : ''}
            </p>
            {status.state !== 'misconfigured' && <PairingPanel connected={status.state === 'connected'} number={status.number} onChange={() => void refresh()} />}
          </div>
        )}
      </section>
      {!disabled && <UnlinkedList />}
    </main>
  );
};
