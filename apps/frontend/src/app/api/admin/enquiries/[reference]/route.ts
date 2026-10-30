import { proxyAdminRequest } from '@/lib/admin-backend';

export async function GET(request: Request) {
  const reference = new URL(request.url).pathname.split('/').filter(Boolean).at(-1);
  return proxyAdminRequest(request, `/v1/admin/enquiries/${encodeURIComponent(reference || '')}`);
}
