'use client';

import { useEffect } from 'react';
import { reportError } from '@/lib/report-error';

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => { reportError(error, window.location.pathname); }, [error]);
  return <main id="main-content" className="flex min-h-[70vh] items-center bg-[#fbf7f0] px-6 py-20 text-[#2f241f]">
    <div className="mx-auto max-w-xl text-center"><h1 className="font-heading text-4xl font-semibold">Something went wrong.</h1><p className="mt-5 leading-7 text-[#6f625a]">Please try again. If it keeps happening, message us on WhatsApp.</p><button type="button" onClick={reset} className="mt-8 rounded-full bg-[#2f241f] px-7 py-4 text-sm font-semibold text-white">Try again</button></div>
  </main>;
}
