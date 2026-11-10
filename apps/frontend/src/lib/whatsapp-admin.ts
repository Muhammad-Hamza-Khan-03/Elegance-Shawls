// Shared by the admin WhatsApp screens. The backend answers 503 {detail: {code: 'whatsapp_disabled'}} while automation is off.
export type ApiResult<T> = { ok: true; data: T } | { ok: false; disabled: boolean; status: number; message: string };

export async function adminFetch<T>(url: string, init?: RequestInit): Promise<ApiResult<T>> {
  try {
    const response = await fetch(url, { cache: 'no-store', ...init, headers: init?.body ? { 'content-type': 'application/json' } : undefined });
    const body = await response.json().catch(() => null);
    if (response.ok) return { ok: true, data: body as T };
    const detail = body?.detail;
    return {
      ok: false, status: response.status, disabled: detail?.code === 'whatsapp_disabled',
      message: response.status === 401 ? 'Your session has expired. Sign in again.' : response.status === 403 ? 'Your role does not permit this action.' : typeof detail === 'string' ? detail : 'Request failed.',
    };
  } catch {
    return { ok: false, status: 0, disabled: false, message: 'Could not reach the server.' };
  }
}

export const DISABLED_NOTICE = 'WhatsApp automation is off. The shop is in link mode: customers order through the wa.me link and staff reply by hand.';

export type BridgeStatus = { state: 'connected' | 'connecting' | 'pairing' | 'needs_pairing' | 'misconfigured' | 'unreachable'; number?: string | null; last_event_at?: string | null; stream_lag?: number | null; dead_letters?: number | null; detail?: string;
  alerts?: string[]; ingested_last_hour?: number; linked_by_reference?: number; linked_by_staff?: number; median_contact_seconds?: number | null };
export type PairingView = { state: string; number?: string | null; pairing: { qr: string | null; code: string | null; expires_at: string } | null };
export type UnlinkedChat = { id: string; phone: string | null; display_name: string | null; last_seen_at: string };
export type TimelineMessage = { id: string; sent_by: 'customer' | 'staff' | 'bot'; type: string; text: string | null; sent_at: string };
