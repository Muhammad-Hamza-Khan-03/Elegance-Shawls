import Link from 'next/link';
import { ProductBrowser } from '@/components/product/ProductBrowser';
import { CatalogCategory } from '@/lib/catalog';

export const dynamic = 'force-dynamic';

export default async function ProductsPage({ searchParams }: { searchParams: Promise<{ category?: string }> }) {
  const { category } = await searchParams;
  const initialCategory: CatalogCategory = category === 'shawls' || category === 'stoles' ? category : 'all';

  return <main className="min-h-screen bg-[#fbf7f0] px-6 py-12 text-[#2f241f]">
    <section className="mx-auto max-w-6xl space-y-10">
      <div>
        <Link href="/" className="text-sm font-medium text-[#9a6b3f] hover:underline">← Back home</Link>
        <h1 className="mt-4 text-4xl font-semibold tracking-tight sm:text-5xl">Shop the collection</h1>
        <p className="mt-3 max-w-2xl leading-7 text-[#6f625a]">Explore available shawls and stoles. Choose your preferred option on the product page and send your order enquiry through WhatsApp.</p>
      </div>
      <ProductBrowser initialCategory={initialCategory} />
    </section>
  </main>;
}
