'use client';

import { useState } from 'react';
import { AssistantChat } from './AssistantChat';

// Opt-in storefront mount: renders nothing unless NEXT_PUBLIC_ASSISTANT_ENABLED=1, so the shop is unchanged until switched on.
export function AssistantLauncher() {
  const [open, setOpen] = useState(false);
  if (process.env.NEXT_PUBLIC_ASSISTANT_ENABLED !== '1') return null;
  return (
    <div className="fixed bottom-4 right-4 z-50 flex max-w-[calc(100vw-2rem)] flex-col items-end gap-2">
      {open && (
        <section aria-label="Shopping assistant" className="max-h-[70vh] w-80 overflow-y-auto rounded-lg border bg-white p-3 shadow-lg">
          <AssistantChat context={{ page: 'storefront' }} />
        </section>
      )}
      <button type="button" aria-expanded={open} onClick={() => setOpen((v) => !v)} className="rounded-full bg-black px-4 py-2 text-sm text-white shadow-lg">
        {open ? 'Close assistant' : 'Ask the assistant'}
      </button>
    </div>
  );
}
