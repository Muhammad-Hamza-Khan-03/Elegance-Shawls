import { proxyAdminRequest } from '@/lib/admin-backend';

export async function GET(request: Request) {
  return proxyAdminRequest(request, '/products/admin/');
}

export async function POST(request: Request) {
  return proxyAdminRequest(request, '/products/admin/');
}
