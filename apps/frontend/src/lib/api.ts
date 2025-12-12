"server only"
import { API_ENDPOINTS } from '@/config/api.config';

type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

type RequestOptions = {
  method?: HttpMethod;
  body?: unknown;
  token?: string | null;
  signal?: AbortSignal;
};

const withId = (template: string, id: string) =>
  template.replace('{id}', encodeURIComponent(id));

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null;

const buildHeaders = (token?: string | null, hasBody?: boolean) => {
  const headers: Record<string, string> = {};
  if (hasBody) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
};

const http = async <T>(
  url: string,
  { method = 'GET', body, token, signal }: RequestOptions = {}
): Promise<T> => {
  const response = await fetch(url, {
    method,
    cache: 'no-store',
    headers: buildHeaders(token, body !== undefined),
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
  });

  const text = await response.text();
  let data: unknown = null;

  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!response.ok) {
    const errorData = isRecord(data) ? data : undefined;
    const message =
      (typeof errorData?.detail === 'string' ? errorData.detail : undefined) ||
      (typeof errorData?.message === 'string' ? errorData.message : undefined) ||
      `Request failed with status ${response.status}`;
    throw new Error(message);
  }

  return data as T;
};

export interface DashboardStatsResponse {
  total_orders?: number;
  total_revenue?: string;
  pending_orders?: number;
  total_products?: number;
  low_stock_products?: number;
}

export interface BackendProductVariant {
  id: number;
  product_id: number;
  color: string | null;
  size: string | null;
  price: string;
  stock: number;
  image_url: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface BackendProduct {
  id: number;
  name: string;
  description: string;
  category: string;
  price: string;
  stock: number;
  created_at: string;
  updated_at: string;
  variants: BackendProductVariant[];
}

export interface BackendOrderItem {
  id: number;
  order_id: number;
  product_variant_id: number;
  quantity: number;
  price: string;
  product_variant?: BackendProductVariant;
}

export interface BackendOrder {
  id: number;
  user_id?: number;
  email?: string;
  whatsapp?: string;
  location?: string;
  address?: string;
  status: string;
  total_amount: string;
  created_at: string;
  updated_at: string | null;
  order_items?: BackendOrderItem[];
}

export const api = {
  // Dashboard
  getDashboardStats: (options?: Omit<RequestOptions, 'method' | 'body'>) =>
    http<DashboardStatsResponse>(API_ENDPOINTS.GET_DASHBOARD_STATS, options),

  // Products
  getProducts: (options?: Omit<RequestOptions, 'method' | 'body'>) =>
    http<BackendProduct[]>(API_ENDPOINTS.GET_PRODUCTS, options),

  getProductById: (id: string, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    http<BackendProduct>(withId(API_ENDPOINTS.GET_PRODUCT_BY_ID, id), options),

  // Orders
  getOrders: (options?: Omit<RequestOptions, 'method' | 'body'>) =>
    http<BackendOrder[]>(API_ENDPOINTS.GET_ALL_ORDERS, options),

  getOrderById: (id: string, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    http<BackendOrder>(withId(API_ENDPOINTS.GET_ORDER_BY_ID, id), options),

  updateOrderStatus: (
    id: string,
    status: string,
    options?: Omit<RequestOptions, 'method'>
  ) =>
    http<BackendOrder>(withId(API_ENDPOINTS.UPDATE_ORDER_STATUS, id), {
      method: 'PATCH',
      body: { status },
      ...options,
    }),
};
