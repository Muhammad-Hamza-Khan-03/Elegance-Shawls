import { internalApiHeaders } from '@/lib/api';

// NEXT_PUBLIC_* values are inlined at build time only when referenced
// statically; container runtimes do not receive them as environment variables.
const publicConfig = {
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  NEXT_PUBLIC_SITE_URL: process.env.NEXT_PUBLIC_SITE_URL,
  NEXT_PUBLIC_WHATSAPP_NUMBER: process.env.NEXT_PUBLIC_WHATSAPP_NUMBER,
};

export async function GET() {
  const missing = Object.entries(publicConfig).filter(([, value]) => !value).map(([name]) => name);
  if (missing.length) return Response.json({ status: 'not_ready', missing }, { status: 503 });
  try {
    const response = await fetch(`${publicConfig.NEXT_PUBLIC_API_URL!.replace(/\/$/, '')}/ready/`, { cache: 'no-store', headers: internalApiHeaders(), signal: AbortSignal.timeout(4000) });
    if (!response.ok) throw new Error('Backend unavailable');
    return Response.json({ status: 'ready', backend: 'connected' });
  } catch {
    return Response.json({ status: 'not_ready', backend: 'unavailable' }, { status: 503 });
  }
}
