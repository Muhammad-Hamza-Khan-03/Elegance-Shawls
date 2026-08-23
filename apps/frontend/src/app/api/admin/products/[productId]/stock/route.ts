import { proxyAdminRequest } from '@/lib/admin-backend';

export async function PATCH(request: Request) {
  const productId = new URL(request.url).pathname.split('/').filter(Boolean).at(-2);
  return proxyAdminRequest(request, `/products/admin/${productId || ''}/stock`);
}
