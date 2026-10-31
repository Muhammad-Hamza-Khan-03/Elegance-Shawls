'use client';

import dynamic from 'next/dynamic';
import { usePathname } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { MessageCircle } from 'lucide-react';
import { isAssistantEnabled, isAssistantRoute } from '@/lib/assistant/ui';

// Panel code only loads once the visitor opens it.
const AssistantPanel = dynamic(() => import('./AssistantPanel'), { ssr: false });

export const AssistantLauncher = () => {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [opened, setOpened] = useState(false);   // once opened, the panel stays mounted (hidden) so the conversation survives close and reopen
  const button = useRef<HTMLButtonElement>(null);
  const wasOpen = useRef(false);

  // Restore focus only after close commits, when the launcher is visible again (hidden on mobile while open).
  useEffect(() => {
    if (wasOpen.current && !open) button.current?.focus();
    wasOpen.current = open;
  }, [open]);

  if (!isAssistantEnabled() || !isAssistantRoute(pathname)) return null;

  const close = () => setOpen(false);
  return (
    <>
      {opened ? <AssistantPanel open={open} onClose={close} /> : null}
      <button
        ref={button} type="button" onClick={() => { setOpened(true); setOpen((v) => !v); }}
        aria-label={open ? 'Close shopping assistant' : 'Open shopping assistant'}
        aria-expanded={open}
        className={`fixed bottom-5 end-5 z-40 flex size-14 items-center justify-center rounded-full bg-[#2f241f] text-white shadow-xl motion-safe:transition-transform motion-safe:hover:scale-105 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#9a6b3f] ${open ? 'max-sm:hidden' : ''}`}
      >
        <MessageCircle className="size-6" aria-hidden />
      </button>
    </>
  );
};
