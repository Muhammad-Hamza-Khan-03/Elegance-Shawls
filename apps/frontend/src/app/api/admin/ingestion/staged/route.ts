import { proxyAdminRequest } from '@/lib/admin-backend';

export async function GET(request: Request) {
  return proxyAdminRequest(request, '/products/admin/ingestion/staged');
}
