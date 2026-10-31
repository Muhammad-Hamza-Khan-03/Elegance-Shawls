'use client';

export type MemoryItem = {
  id: string;
  category: 'preference' | 'session_constraint' | 'purchase_context';
  key: string;
  value: string;
  source: 'user_explicit' | 'memory_page';
  source_ref: string | null;
  reason: string | null;
  version: number;
  retention_days: number;
  expires_at: string;
  created_at: string;
  updated_at: string;
};

export type Consent = { granted: boolean; policy_version: string; changed_at: string | null };
export type MemoryApiError = Error & { status?: number; reason?: string };

const request = async <T>(path: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(`/api/customer/memory${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    cache: 'no-store',
  });
  if (!response.ok) {
    const error = new Error(response.status === 401 ? 'Sign in is required to manage memory.' : 'Memory request failed.') as MemoryApiError;
    error.status = response.status;
    error.reason = (await response.json().catch(() => null))?.reason;
    throw error;
  }
  return response.status === 204 ? (undefined as T) : response.json();
};

export const memoryApi = {
  getConsent: () => request<Consent>('/consent'),
  setConsent: (granted: boolean) => request<Consent>('/consent', { method: 'PUT', body: JSON.stringify({ granted }) }),
  list: () => request<{ items: MemoryItem[] }>(''),
  create: (item: { category: MemoryItem['category']; key: string; value: string; reason?: string }) => request<MemoryItem>('', {
    method: 'POST',
    body: JSON.stringify({ ...item, source: 'memory_page', idempotency_key: `idem_${crypto.randomUUID().replace(/-/g, '')}` }),
  }),
  get: (id: string) => request<MemoryItem>(`/${encodeURIComponent(id)}`),
  update: (id: string, value?: string, reason?: string) => request<MemoryItem>(`/${encodeURIComponent(id)}`, {
    method: 'PATCH', body: JSON.stringify({ ...(value !== undefined ? { value } : {}), ...(reason !== undefined ? { reason } : {}) }),
  }),
  remove: (id: string) => request<void>(`/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  removeAll: () => request<{ deleted: number }>('', { method: 'DELETE' }),
};
