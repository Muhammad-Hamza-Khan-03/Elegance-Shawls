import { proxyAdminRequest } from '@/lib/admin-backend';
import { UUID } from '@/lib/staging';

export async function POST(request: Request) {
  const [stagedId, , suggestionId] = new URL(request.url).pathname.split('/').filter(Boolean).slice(-4);
  if (!UUID.test(stagedId || '') || !UUID.test(suggestionId || '')) {
    return Response.json({ detail: 'Unknown suggestion.' }, { status: 404 });
  }
  return proxyAdminRequest(request, `/products/admin/ingestion/staged/${stagedId}/enrichment/${suggestionId}/cancel`);
}
