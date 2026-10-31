'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';

const CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || '';
const GSI = 'https://accounts.google.com/gsi/client';

type Gsi = { accounts: { id: { initialize: (o: { client_id: string; callback: (r: { credential?: string }) => void }) => void; renderButton: (el: HTMLElement, o: object) => void } } };
declare global { interface Window { google?: Gsi } }

// Google Identity Services hands us an ID token; only the same-origin route handler exchanges it for the opaque session cookie.
export function AccountSignIn() {
  const button = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<'checking' | 'idle' | 'busy' | 'in' | 'error'>(CLIENT_ID ? 'checking' : 'idle');
  const [gsiReady, setGsiReady] = useState(false);

  // A returning visitor with a live session sees that, not the Google button.
  useEffect(() => {
    if (!CLIENT_ID) return;
    void fetch('/api/customer/session', { cache: 'no-store' }).then((r) => r.json())
      .then((s) => setState(s?.authenticated ? 'in' : 'idle')).catch(() => setState('idle'));
  }, []);

  useEffect(() => {
    if (!CLIENT_ID) return;
    const start = () => {
      window.google?.accounts.id.initialize({
        client_id: CLIENT_ID,
        callback: async ({ credential }) => {
          if (!credential) return setState('error');
          setState('busy');
          const res = await fetch('/api/customer/session', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ id_token: credential }) }).catch(() => null);
          setState(res?.ok ? 'in' : 'error');
        },
      });
      setGsiReady(true);
    };
    if (window.google) { start(); return; }
    const script = document.createElement('script');
    script.src = GSI;
    script.async = true;
    script.onload = start;
    document.head.appendChild(script);
    return () => { script.remove(); };
  }, []);

  // Draw the button whenever the signed-out view is on screen (first load, after sign-out, after an error).
  useEffect(() => {
    if ((state === 'idle' || state === 'error') && gsiReady && button.current) window.google?.accounts.id.renderButton(button.current, { theme: 'outline', size: 'large' });
  }, [state, gsiReady]);

  async function signOut() {
    await fetch('/api/customer/session', { method: 'DELETE' }).catch(() => null);
    setState('idle');
  }

  if (!CLIENT_ID) return <p>Customer sign-in is not set up on this shop yet.</p>;
  return (
    <div className="space-y-4">
      {state === 'checking' && <p role="status">Checking your sign-in…</p>}
      {(state === 'idle' || state === 'error') && <div ref={button} />}
      {state === 'busy' && <p role="status">Signing you in…</p>}
      {state === 'error' && <p role="alert">Sign-in did not work. Please try again.</p>}
      {state === 'in' && (
        <div className="space-y-3">
          <p role="status">You are signed in.</p>
          <Link href="/memory" className="underline">Manage what the assistant remembers</Link>
          <div><button type="button" onClick={signOut} className="rounded border px-3 py-1 text-sm">Sign out</button></div>
        </div>
      )}
    </div>
  );
}
