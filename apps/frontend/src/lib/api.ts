import { Product, Order } from '@/types/types';

const API_URL = process.env.NEXT_PUBLIC_API_URL;

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
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const mapBackendProduct = (bp: any): Product => {
  const rawVariations = bp.variations || bp.variants || [];
  const productPrice = Number(bp.price?.amount ?? bp.price ?? 0);
  const currency = bp.price?.currency || bp.currency || 'PKR';

  const variants = rawVariations.map((v: any, index: number) => ({
    id: v._id || v.id || `${bp._id || bp.id || bp.slug}-variant-${index}`,
    color: v.color || v.name || 'Default',
    size: v.size || bp.sizing || 'Free Size',
    stock: v.stock ?? (v.stock_status === 'Out of stock' ? 0 : 10),
    price: Number(v.price?.amount ?? v.price ?? productPrice),
    image_url: v.image_url || v.imageUrl || undefined,
  }));

  const images = [bp.cover_image_url, bp.image_url, bp.imageUrl]
    .filter(Boolean) as string[];

  variants.forEach((variant: any) => {
    if (variant.image_url && !images.includes(variant.image_url)) {
      images.push(variant.image_url);
    }
  });

  if (images.length === 0) {
    images.push('https://placehold.co/600x800/fbf7f0/2f241f?text=Elegance+Shawls');
  }

  const status = bp.status || (bp.is_active === false ? 'draft' : 'active');

  return {
    id: bp._id || bp.id,
    name: bp.name,
    slug: bp.slug,
    description: bp.description || bp.main_description || '',
    price: variants[0]?.price || productPrice,
    currency,
    category: normalizeCategory(bp.category || bp.type),
    images,
    variants,
    stock: variants.reduce((acc: number, v: any) => acc + Number(v.stock || 0), 0),
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

const extractItems = (data: any) => {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.items)) return data.items;
  if (Array.isArray(data?.products)) return data.products;
  return [];
};

export const api = {
  // GET /products
  getProducts: async (): Promise<Product[]> => {
    try {
      const data = await handleResponse(await fetch(`${getApiUrl()}/products/`));
      return extractItems(data)
        .map((p: any) => mapBackendProduct(p))
        .filter((p: Product) => p.status === 'active');
    } catch (error) {
      console.error('Failed to fetch products:', error);
      return [];
    }
  },

  // GET /products/:id
  getProductById: async (id: string): Promise<Product | undefined> => {
    try {
      const products = await api.getProducts();
      return products.find(p => p.id === id);
    } catch (error) {
      console.error(`Failed to fetch product by id ${id}:`, error);
      return undefined;
    }
  },

  // GET /products/slug/:slug
  getProductBySlug: async (slug: string): Promise<Product | undefined> => {
    try {
      const data = await handleResponse(await fetch(`${getApiUrl()}/products/slug/${slug}`));
      return mapBackendProduct(data);
    } catch (e) {
      console.error(`Failed to fetch product by slug ${slug}:`, e);
      const products = await api.getProducts();
      return products.find(p => p.slug === slug);
    }
  },

  // GET /products/category/:category
  getProductsByCategory: async (category: 'shawls' | 'stoles'): Promise<Product[]> => {
    const products = await api.getProducts();
    return products.filter(p => p.category === category);
  },

  // GET /products/featured
  getFeaturedProducts: async (): Promise<Product[]> => {
    const products = await api.getProducts();
    return products.slice(0, 4);
  },

  // Product writes are owned by Quill Panel, not the storefront.
  createProduct: async (): Promise<Product> => {
    throw new Error('Product creation is handled in Quill Panel.');
  },

  updateProduct: async (): Promise<Product> => {
    throw new Error('Product updates are handled in Quill Panel.');
  },

  deleteProduct: async (): Promise<void> => {
    throw new Error('Product deletion is handled in Quill Panel.');
  },

  // Orders are intentionally handled through WhatsApp for launch.
  getOrders: async (): Promise<Order[]> => {
    return [];
  },

  getOrderById: async (): Promise<Order | undefined> => {
    return undefined;
  },

  createOrder: async (): Promise<Order> => {
    throw new Error('Orders are submitted through WhatsApp checkout.');
  },

  updateOrder: async (): Promise<Order> => {
    throw new Error('Orders are managed manually through WhatsApp.');
  },
};
