import Link from 'next/link';
import { ProductBrowser } from '@/components/product/ProductBrowser';
import { CatalogCategory } from '@/lib/catalog';
import { isProductCategory } from '@/lib/categories';
import { Metadata } from 'next';
import { absoluteUrl } from '@/lib/site';
import { api } from '@/lib/api';

export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Shop shawls and stoles', description: 'Search, filter and browse available shawls and stoles.', alternates: absoluteUrl('/products') ? { canonical: absoluteUrl('/products')! } : undefined };

export default async function ProductsPage({ searchParams }: { searchParams: Promise<{ category?: string }> }) {
  const { category } = await searchParams;
  const initialCategory: CatalogCategory = isProductCategory(category) ? category : 'all';
  // null (not []) tells the browser to retry itself instead of showing an empty shop.
  const initialPage = await api.getProductPage().catch(() => null);

  return <main id="main-content" className="min-h-screen bg-[#fbf7f0] px-4 py-10 text-[#2f241f] sm:px-6 sm:py-12">
    <section className="mx-auto max-w-6xl space-y-10">
      <div>
        <Link href="/" className="text-sm font-medium text-[#9a6b3f] hover:underline">← Back home</Link>
        <h1 className="font-heading mt-4 text-4xl font-semibold tracking-tight sm:text-5xl">Shop the collection</h1>
        <p className="mt-3 max-w-2xl leading-7 text-[#6f625a]">Explore available shawls and stoles. Choose your preferred option on the product page and send your order enquiry through WhatsApp.</p>
      </div>
      <ProductBrowser key={initialCategory} initialCategory={initialCategory} initialPage={initialPage} />
    </section>
  </main>;
}
