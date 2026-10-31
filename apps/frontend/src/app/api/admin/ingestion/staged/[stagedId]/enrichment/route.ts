import { proxyAdminRequest } from '@/lib/admin-backend';
import { UUID } from '@/lib/staging';

const forward = (request: Request) => {
  const stagedId = new URL(request.url).pathname.split('/').filter(Boolean).slice(-2)[0];
  if (!UUID.test(stagedId || '')) {
    return Response.json({ detail: 'Unknown staged product.' }, { status: 404 });
  }
  return proxyAdminRequest(request, `/products/admin/ingestion/staged/${stagedId}/enrichment`);
};

// Read the latest suggestion, or request one; backend status codes (404/409/503) pass through unchanged.
export const GET = forward;
export const POST = forward;
