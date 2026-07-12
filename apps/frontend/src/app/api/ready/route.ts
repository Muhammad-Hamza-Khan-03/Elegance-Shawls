const required = ['NEXT_PUBLIC_API_URL', 'NEXT_PUBLIC_SITE_URL', 'NEXT_PUBLIC_WHATSAPP_NUMBER'] as const;

export async function GET() {
  const missing = required.filter((name) => !process.env[name]);
  if (missing.length) return Response.json({ status: 'not_ready', missing }, { status: 503 });
  try {
    const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL!.replace(/\/$/, '')}/ready/`, { cache: 'no-store', signal: AbortSignal.timeout(4000) });
    if (!response.ok) throw new Error('Backend unavailable');
    return Response.json({ status: 'ready', backend: 'connected' });
  } catch {
    return Response.json({ status: 'not_ready', backend: 'unavailable' }, { status: 503 });
  }
}
