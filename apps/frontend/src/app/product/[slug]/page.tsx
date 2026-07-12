import { notFound } from 'next/navigation';
import { api } from '@/lib/api';
import { ProductExperience } from '@/components/product/ProductExperience';
import { Metadata } from 'next';
import { absoluteUrl } from '@/lib/site';

export const dynamic = 'force-dynamic';

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const product = await api.getProductBySlug(slug);
  if (!product || product.status !== 'active') return { title: 'Product not found', robots: { index: false, follow: false } };
  const description = product.description?.slice(0, 160) || `View ${product.name}, available options and stock.`;
  const canonical = absoluteUrl(`/product/${product.slug}`);
  return {
    title: product.name,
    description,
    alternates: canonical ? { canonical } : undefined,
    openGraph: { type: 'website', title: product.name, description, url: canonical || undefined, images: product.images.map((url) => ({ url, alt: product.name })) },
    twitter: { card: 'summary_large_image', title: product.name, description, images: product.images.slice(0, 1) },
  };
}

export default async function ProductDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const product = await api.getProductBySlug(slug);

  if (!product || product.status !== 'active') {
    notFound();
  }

  const productUrl = absoluteUrl(`/product/${product.slug}`);
  const structuredData = {
    '@context': 'https://schema.org',
    '@type': 'Product',
    name: product.name,
    description: product.description || undefined,
    image: product.images,
    sku: product.itemNumber ? String(product.itemNumber) : undefined,
    category: product.category,
    brand: { '@type': 'Brand', name: 'Elegance Shawls' },
    offers: {
      '@type': 'Offer',
      priceCurrency: product.currency,
      price: product.price,
      availability: product.stock > 0 ? 'https://schema.org/InStock' : 'https://schema.org/OutOfStock',
      url: productUrl || undefined,
    },
  };

  return <>
    <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData).replace(/</g, '\\u003c') }} />
    <ProductExperience product={product} siteUrl={process.env.NEXT_PUBLIC_SITE_URL || ''} whatsappNumber={process.env.NEXT_PUBLIC_WHATSAPP_NUMBER || ''} />
  </>;
}
