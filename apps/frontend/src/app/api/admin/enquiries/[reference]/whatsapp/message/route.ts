import { proxyAdminRequest } from '@/lib/admin-backend';

export async function POST(request: Request) {
  const reference = new URL(request.url).pathname.split('/').filter(Boolean).at(-3);
  return proxyAdminRequest(request, `/v1/admin/enquiries/${encodeURIComponent(reference || '')}/whatsapp/message`);
}
