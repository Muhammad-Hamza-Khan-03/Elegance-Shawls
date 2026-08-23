import { proxyAdminRequest } from '@/lib/admin-backend';

export async function GET(request: Request) {
  const productId = new URL(request.url).pathname.split('/').filter(Boolean).at(-1);
  return proxyAdminRequest(request, `/products/admin/${productId || ''}`);
}

export async function PUT(request: Request) {
  const productId = new URL(request.url).pathname.split('/').filter(Boolean).at(-1);
  return proxyAdminRequest(request, `/products/admin/${productId || ''}`);
}

export async function DELETE(request: Request) {
  const productId = new URL(request.url).pathname.split('/').filter(Boolean).at(-1);
  return proxyAdminRequest(request, `/products/admin/${productId || ''}`);
}
