import { proxyAdminRequest } from '@/lib/admin-backend';

export async function GET(request: Request) {
  return proxyAdminRequest(request, '/v1/admin/enquiries');
}
