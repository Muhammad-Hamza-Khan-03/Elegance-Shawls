import { proxyAdminRequest } from '@/lib/admin-backend';

export async function POST(request: Request) {
  return proxyAdminRequest(request, '/v1/search/hybrid');
}
