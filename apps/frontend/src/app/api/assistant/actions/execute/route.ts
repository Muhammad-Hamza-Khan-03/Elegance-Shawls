import { proxyAssistant } from '@/lib/assistant-proxy';

export async function POST(request: Request) {
  return proxyAssistant(request, '/v1/assistant/actions/execute');
}
