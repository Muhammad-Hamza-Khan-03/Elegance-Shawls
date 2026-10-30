import { proxyAdminRequest } from '@/lib/admin-backend';

export async function GET(request: Request) {
  return proxyAdminRequest(request, '/products/admin/ingestion/jobs');
}

// The body carries only a product path; the backend joins it to the configured source host.
export async function POST(request: Request) {
  return proxyAdminRequest(request, '/products/admin/ingestion/jobs');
}
