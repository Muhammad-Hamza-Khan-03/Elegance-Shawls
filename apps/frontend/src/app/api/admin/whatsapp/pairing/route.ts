import { proxyAdminRequest } from '@/lib/admin-backend';

const forward = (request: Request) => proxyAdminRequest(request, '/v1/admin/whatsapp/pairing');

export const GET = forward;
export const POST = forward;
export const DELETE = forward;
