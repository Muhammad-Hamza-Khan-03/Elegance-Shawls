import { proxyAdminRequest } from '@/lib/admin-backend';
import { STAGED_ACTIONS, UUID, type StagedAction } from '@/lib/staging';

const OBJECT_ID = /^[a-f0-9]{24}$/i; // legacy ids; Postgres staged ids are UUIDs

// Only known review actions are forwarded; the path segments never reach the backend unchecked.
export async function POST(request: Request) {
  const [stagedId, action] = new URL(request.url).pathname.split('/').filter(Boolean).slice(-2);
  if ((!OBJECT_ID.test(stagedId || '') && !UUID.test(stagedId || '')) ||!STAGED_ACTIONS.includes(action as StagedAction)) {
    return Response.json({ detail: 'Unknown staged product action.' }, { status: 404 });
  }
  return proxyAdminRequest(request, `/products/admin/ingestion/staged/${stagedId}/${action}`);
}
