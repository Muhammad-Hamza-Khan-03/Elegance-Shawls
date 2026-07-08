import Link from 'next/link';
import { api } from '@/lib/api';
import { formatCurrency } from '@/lib/whatsapp';

export const dynamic = 'force-dynamic';

export default async function ProductsPage() {
  const products = await api.getProducts();

  return (
    <main className="min-h-screen bg-[#fbf7f0] px-6 py-12 text-[#2f241f]">
      <section className="mx-auto max-w-6xl space-y-10">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <Link href="/" className="text-sm font-medium text-[#9a6b3f] hover:underline">
              ← Back home
            </Link>
            <h1 className="mt-4 text-4xl font-semibold tracking-tight sm:text-5xl">
              Shop the collection
            </h1>
            <p className="mt-3 max-w-2xl text-[#6f625a]">
              Browse active shawls and stoles uploaded from Quill Panel. Orders are confirmed through WhatsApp.
            </p>
          </div>
        </div>

        {products.length === 0 ? (
          <div className="rounded-3xl border border-[#e7dac8] bg-white/70 p-10 text-center shadow-sm">
            <h2 className="text-2xl font-semibold">No products available yet</h2>
            <p className="mt-3 text-[#6f625a]">
              Add active products from Quill Panel and make sure the storefront API URL is configured.
            </p>
          </div>
        ) : (
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {products.map((product) => (
              <Link
                key={product.id || product.slug}
                href={`/product/${product.slug}`}
                className="group overflow-hidden rounded-3xl border border-[#e7dac8] bg-white shadow-sm transition hover:-translate-y-1 hover:shadow-md"
              >
                <div className="aspect-[3/4] overflow-hidden bg-[#efe5d5]">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={product.images[0]}
                    alt={product.name}
                    className="h-full w-full object-cover transition duration-500 group-hover:scale-105"
                  />
                </div>
                <div className="space-y-3 p-5">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.25em] text-[#9a6b3f]">
                      {product.category}
                    </p>
                    <h2 className="mt-2 line-clamp-2 text-xl font-semibold">{product.name}</h2>
                  </div>
                  <p className="text-lg font-semibold">
                    {formatCurrency(product.price, product.currency)}
                  </p>
                  <p className="text-sm text-[#6f625a]">
                    {product.variants.length} color option{product.variants.length === 1 ? '' : 's'} available
                  </p>
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
