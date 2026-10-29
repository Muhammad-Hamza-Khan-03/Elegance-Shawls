export const STAGED_ACTIONS = ['approve', 'reject', 'publish', 'unpublish', 'archive'] as const;
export type StagedAction = (typeof STAGED_ACTIONS)[number];

export const STAGED_STATUSES = ['pending_review', 'approved', 'rejected', 'published', 'unpublished', 'archived'] as const;
export type StagedStatus = (typeof STAGED_STATUSES)[number];

export type StagedProduct = {
  _id: string;
  source_name: string;
  source_url: string;
  source_product_id?: string | null;
  source_price?: number | null;
  source_currency?: string | null;
  status: StagedStatus;
  rejection_reason?: string | null;
  missing_fields: string[];
  stock_known: boolean;
  latest_source_hash?: string | null;
  product_id?: string | null;
  product: {
    name: string;
    cover_image_url: string;
    images: string[];
    main_description?: string | null;
    category: string;
    material?: string | null;
    sizing?: string | null;
    weight?: string | null;
    variants: { name: string; stock: number }[];
  };
  source_attributes?: Record<string, unknown>;
  created_at: string;
};

// Mirrors the backend transition table; the backend remains the authority and rejects anything else.
const ACTIONS_BY_STATUS: Record<StagedStatus, StagedAction[]> = {
  pending_review: ['approve', 'reject'],
  approved: ['publish', 'archive'],
  published: ['unpublish', 'archive'],
  unpublished: ['publish', 'archive'],
  rejected: ['archive'],
  archived: [],
};

export const availableActions = (status: StagedStatus): StagedAction[] => ACTIONS_BY_STATUS[status] ?? [];

export const formatSourcePrice = (price?: number | null, currency?: string | null) => {
  if (price == null) return 'Not provided';
  return currency ? `${price.toFixed(2)} ${currency}` : `${price.toFixed(2)} (currency unknown)`;
};

export const describeMissing = (field: string) =>
  ({
    price: 'Retail price (PKR) — set on approval',
    stock: 'Stock — set on approval',
    source_price: 'Source price',
    source_currency: 'Source currency',
    material: 'Material',
    sizing: 'Sizing',
    weight: 'Weight',
  })[field] ?? field;

export class StagingApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

const errorMessage = async (response: Response) => {
  const body = await response.json().catch(() => null);
  const detail = body?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
  return `Request failed (${response.status})`;
};

const request = async <T,>(input: string, init?: RequestInit): Promise<T> => {
  let response: Response;
  try {
    response = await fetch(input, { ...init, cache: 'no-store' });
  } catch {
    throw new StagingApiError('Could not reach the server.', 0);
  }
  if (!response.ok) throw new StagingApiError(await errorMessage(response), response.status);
  return response.json() as Promise<T>;
};

export const listStaged = (status?: StagedStatus | 'all') =>
  request<{ items: StagedProduct[]; next_cursor?: string | null }>(
    `/api/admin/ingestion/staged${status && status !== 'all' ? `?status=${status}` : ''}`
  );

export type ActionBody = { price?: number; stock?: number; reason?: string };

export const runStagedAction = (id: string, action: StagedAction, body?: ActionBody) =>
  request<StagedProduct>(`/api/admin/ingestion/staged/${id}/${action}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  });

export type PkrSuggestion = {
  source_price: number;
  source_currency: string;
  rate: number;
  rate_date: string;
  suggested_pkr: number;
  note: string;
};

export const fetchPkrSuggestion = (id: string) =>
  request<PkrSuggestion>(`/api/admin/ingestion/staged/${id}/pkr-suggestion`);

export const formatSuggestion = (s: PkrSuggestion) =>
  `≈ PKR ${s.suggested_pkr.toLocaleString('en-US')} (1 ${s.source_currency} = ${s.rate.toFixed(2)} PKR, rate of ${s.rate_date})`;

export const queueProductPath = (path: string) =>
  request<{ _id: string; status: string }>('/api/admin/ingestion/jobs', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ path }),
  });
