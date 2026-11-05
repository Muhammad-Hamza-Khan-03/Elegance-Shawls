'use client';

import Link from 'next/link';

export default function Error({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <main id="main-content" className="flex min-h-[70vh] items-center bg-[#fbf7f0] px-6 py-20 text-[#2f241f]">
    <div role="alert" className="mx-auto max-w-xl text-center">
      <p className="text-xs font-bold uppercase tracking-[0.3em] text-[#9a6b3f]">Something went wrong</p>
      <h1 className="font-heading mt-4 text-4xl font-semibold sm:text-5xl">We could not load this page.</h1>
      <p className="mt-5 leading-7 text-[#6f625a]">This is usually temporary. Please try again, or come back in a moment.</p>
      <div className="mt-8 flex flex-wrap justify-center gap-3">
        <button type="button" onClick={reset} className="rounded-full bg-[#2f241f] px-7 py-4 text-sm font-semibold text-white">Try again</button>
        <Link href="/" className="rounded-full border border-[#bda98f] px-7 py-4 text-sm font-semibold">Back home</Link>
      </div>
    </div>
  </main>;
}
