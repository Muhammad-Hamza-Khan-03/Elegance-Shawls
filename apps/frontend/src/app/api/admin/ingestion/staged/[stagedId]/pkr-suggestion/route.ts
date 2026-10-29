import { proxyAdminRequest } from '@/lib/admin-backend';
import { UUID } from '@/lib/staging';

const OBJECT_ID = /^[a-f0-9]{24}$/i; // legacy ids; Postgres staged ids are UUIDs

// Read-only reference conversion; the id is validated before it reaches the backend path.
export async function GET(request: Request) {
  const stagedId = new URL(request.url).pathname.split('/').filter(Boolean).slice(-2)[0];
  if (!OBJECT_ID.test(stagedId || '') && !UUID.test(stagedId || '')) {
    return Response.json({ detail: 'Unknown staged product.' }, { status: 404 });
  }
  return proxyAdminRequest(request, `/products/admin/ingestion/staged/${stagedId}/pkr-suggestion`);
}
