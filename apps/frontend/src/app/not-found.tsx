import Link from 'next/link';

export default function NotFound() {
  return <main id="main-content" className="flex min-h-[70vh] items-center bg-[#fbf7f0] px-6 py-20 text-[#2f241f]">
    <div className="mx-auto max-w-xl text-center"><p className="text-xs font-bold uppercase tracking-[0.3em] text-[#9a6b3f]">404</p><h1 className="font-heading mt-4 text-5xl font-semibold">This page could not be found.</h1><p className="mt-5 leading-7 text-[#6f625a]">The link may be outdated, or the product may no longer be available.</p><Link href="/products" className="mt-8 inline-block rounded-full bg-[#2f241f] px-7 py-4 text-sm font-semibold text-white">Browse the collection</Link></div>
  </main>;
}
