import { MetadataRoute } from 'next';
import { api } from '@/lib/api';
import { getSiteUrl } from '@/lib/site';

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const siteUrl = getSiteUrl();
  if (!siteUrl) return [];
  const products = await api.getProducts().catch(() => []);
  const staticPaths = ['', '/products', '/delivery', '/returns', '/privacy', '/terms', '/contact'];
  return [
    ...staticPaths.map((path) => ({ url: `${siteUrl}${path}`, changeFrequency: path === '' ? 'weekly' as const : 'monthly' as const, priority: path === '' ? 1 : 0.7 })),
    ...products.map((product) => ({ url: `${siteUrl}/product/${product.slug}`, lastModified: product.updatedAt || undefined, changeFrequency: 'weekly' as const, priority: 0.8 })),
  ];
}
