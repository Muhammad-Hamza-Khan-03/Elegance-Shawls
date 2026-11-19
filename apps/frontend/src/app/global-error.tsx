'use client';

import { useEffect } from 'react';
import { reportError } from '@/lib/report-error';

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => { reportError(error, window.location.pathname); }, [error]);
  return <html lang="en"><body style={{ background: '#fbf7f0', color: '#2f241f', fontFamily: 'sans-serif', textAlign: 'center', padding: '6rem 1.5rem' }}>
    <h1>Something went wrong.</h1><p>Please try again.</p><button type="button" onClick={reset}>Try again</button>
  </body></html>;
}
