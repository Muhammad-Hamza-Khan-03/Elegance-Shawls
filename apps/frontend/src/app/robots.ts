import { MetadataRoute } from 'next';
import { getSiteUrl } from '@/lib/site';

export default function robots(): MetadataRoute.Robots {
  const siteUrl = getSiteUrl();
  return {
    rules: { userAgent: '*', allow: '/', disallow: ['/api/', '/admin/'] },
    sitemap: siteUrl ? `${siteUrl}/sitemap.xml` : undefined,
  };
}
