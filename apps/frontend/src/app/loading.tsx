export default function Loading() {
  return <main id="main-content" role="status" aria-live="polite" className="mx-auto min-h-[60vh] max-w-6xl px-6 py-12">
    <div className="h-8 w-48 animate-pulse rounded-full bg-[#efe5d5]" />
    <div className="mt-8 grid grid-cols-2 gap-4 lg:grid-cols-4">{Array.from({ length: 4 }, (_, i) => <div key={i} className="aspect-[3/4] animate-pulse rounded-3xl bg-[#efe5d5]" />)}</div>
    <span className="sr-only">Loading</span>
  </main>;
}
