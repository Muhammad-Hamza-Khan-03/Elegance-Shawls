import { Product } from '@/types/types';

const API_URL = process.env.NEXT_PUBLIC_API_URL;

type BackendVariant = {
  _id?: string;
  id?: string;
  color?: string;
  name?: string;
  size?: string;
  stock?: number;
  stock_status?: string;
  price?: number | { amount?: number };
  image_url?: string;
  imageUrl?: string;
};

type BackendProduct = {
  _id?: string;
  id?: string;
  name?: string;
  slug?: string;
  description?: string;
  main_description?: string;
  price?: number | { amount?: number; currency?: string };
  currency?: string;
  category?: string | { name?: string };
  type?: string;
  cover_image_url?: string;
  image_url?: string;
  imageUrl?: string;
  images?: string[];
  variations?: BackendVariant[];
  variants?: BackendVariant[];
  status?: Product['status'];
  is_active?: boolean;
  material?: string;
  sizing?: string;
  weight?: string;
  item_number?: string | number;
  created_at?: string;
  createdAt?: string;
  updated_at?: string;
  updatedAt?: string;
};

const amountFrom = (price: number | { amount?: number } | undefined, fallback = 0) =>
  typeof price === 'number' ? price : Number(price?.amount ?? fallback);

const currencyFrom = (
  price: number | { currency?: string } | undefined,
  fallback = 'PKR',
) => (typeof price === 'object' ? price.currency || fallback : fallback);

const getApiUrl = () => {
  if (!API_URL) {
    throw new Error('NEXT_PUBLIC_API_URL is not configured.');
  }

  return API_URL.replace(/\/$/, '');
};

// Helper to handle API responses
const handleResponse = async (response: Response) => {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'An error occurred' }));
    throw new Error(error.detail || `API Error: ${response.statusText}`);
  }
  return response.json();
};

const normalizeCategory = (category: unknown): 'shawls' | 'stoles' => {
  const raw =
    typeof category === 'object' && category !== null && 'name' in category
      ? String((category as { name?: string }).name || '')
      : String(category || '');

  return raw.toLowerCase().includes('stole') ? 'stoles' : 'shawls';
};

// Mapper: Backend/Quill Product -> Storefront Product
const mapBackendProduct = (bp: BackendProduct): Product => {
  const rawVariations = bp.variations || bp.variants || [];
  const productPrice = amountFrom(bp.price);
  const currency = currencyFrom(bp.price, bp.currency || 'PKR');

  const variants = rawVariations.map((v: BackendVariant, index: number) => ({
    id: v._id || v.id || `${bp._id || bp.id || bp.slug}-variant-${index}`,
    color: v.color || v.name || 'Default',
    size: v.size || bp.sizing || 'Free Size',
    stock: v.stock ?? (v.stock_status === 'Out of stock' ? 0 : 10),
    price: amountFrom(v.price, productPrice),
    image_url: v.image_url || v.imageUrl || undefined,
  }));

  const images = [...(bp.images || []), bp.cover_image_url, bp.image_url, bp.imageUrl]
    .filter(Boolean) as string[];

  variants.forEach((variant) => {
    if (variant.image_url && !images.includes(variant.image_url)) {
      images.push(variant.image_url);
    }
  });

  if (images.length === 0) {
    images.push('https://placehold.co/600x800/fbf7f0/2f241f?text=Elegance+Shawls');
  }

  const status = bp.status || (bp.is_active === false ? 'draft' : 'active');

  return {
    id: bp._id || bp.id || bp.slug || '',
    name: bp.name || 'Untitled product',
    slug: bp.slug || '',
    description: bp.description || bp.main_description || '',
    price: variants[0]?.price || productPrice,
    currency,
    category: normalizeCategory(bp.category || bp.type),
    images,
    variants,
    stock: variants.reduce((acc: number, v) => acc + Number(v.stock || 0), 0),
    status,
    material: bp.material,
    sizing: bp.sizing,
    weight: bp.weight,
    itemNumber: bp.item_number,
    type: bp.type,
    createdAt: bp.created_at || bp.createdAt || '',
    updatedAt: bp.updated_at || bp.updatedAt || '',
  };
};

const extractItems = (data: unknown): BackendProduct[] => {
  if (Array.isArray(data)) return data;
  if (typeof data === 'object' && data !== null) {
    const payload = data as { items?: unknown; products?: unknown };
    if (Array.isArray(payload.items)) return payload.items;
    if (Array.isArray(payload.products)) return payload.products;
  }
  return [];
};

export const api = {
  // GET /products
  getProducts: async (): Promise<Product[]> => {
    const data = await handleResponse(await fetch(`${getApiUrl()}/products/?limit=100`));
    return extractItems(data)
      .map((p) => mapBackendProduct(p))
      .filter((p: Product) => p.status === 'active');
  },

  // GET /products/slug/:slug
  getProductBySlug: async (slug: string): Promise<Product | undefined> => {
    try {
      const data = await handleResponse(await fetch(`${getApiUrl()}/products/slug/${slug}`));
      return mapBackendProduct(data);
    } catch (e) {
      console.error(`Failed to fetch product by slug ${slug}:`, e);
      try {
        const products = await api.getProducts();
        return products.find(p => p.slug === slug);
      } catch {
        return undefined;
      }
    }
  },

  // GET /products/featured
  getFeaturedProducts: async (): Promise<Product[]> => {
    const products = await api.getProducts();
    return products.slice(0, 4);
  },

};
