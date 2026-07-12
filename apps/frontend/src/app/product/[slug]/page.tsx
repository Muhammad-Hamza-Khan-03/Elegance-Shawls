import { notFound } from 'next/navigation';
import { api } from '@/lib/api';
import { ProductExperience } from '@/components/product/ProductExperience';

export const dynamic = 'force-dynamic';

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

  return <ProductExperience product={product} siteUrl={process.env.NEXT_PUBLIC_SITE_URL || ''} whatsappNumber={process.env.NEXT_PUBLIC_WHATSAPP_NUMBER || ''} />;
}
