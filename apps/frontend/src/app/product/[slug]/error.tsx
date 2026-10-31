'use client';

import { startTransition } from 'react';
import { useRouter } from 'next/navigation';

export default function ProductError({ reset }: { error: Error; reset: () => void }) {
  const router = useRouter();
  // Refresh re-runs the server fetch; reset alone would only re-render the failed tree.
  const retry = () => startTransition(() => { router.refresh(); reset(); });
  return <div role="alert" className="mx-auto my-16 max-w-xl rounded-3xl border border-[#e7dac8] bg-white/70 p-10 text-center">
    <h1 className="text-2xl font-semibold">This product could not be loaded</h1>
    <p className="mt-3 text-[#6f625a]">The collection is temporarily unavailable. Please try again.</p>
    <button type="button" onClick={retry} className="mt-6 rounded-full bg-[#2f241f] px-6 py-3 font-semibold text-white">Try again</button>
  </div>;
}
