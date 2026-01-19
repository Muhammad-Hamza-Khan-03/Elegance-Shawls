import { Product, Order } from '@/types/types';

const API_URL = process.env.NEXT_PUBLIC_API_URL;

// Helper to handle API responses
const handleResponse = async (response: Response) => {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'An error occurred' }));
    throw new Error(error.detail || `API Error: ${response.statusText}`);
  }
  return response.json();
};

// Mapper: Backend Product -> Frontend Product
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const mapBackendProduct = (bp: any): Product => {
  const variants = bp.variants?.map((v: any) => ({
    id: v._id || v.id || 'unknown',
    color: v.name, // Mapping variant name to color
    size: 'Free Size',
    stock: v.stock_status === 'In stock' ? 10 : 0
  })) || [];

  const price = variants.length > 0 ? variants[0].price : 0;

  // Collect all images: cover + variant images
  const images = [bp.cover_image_url];
  variants.forEach((v: any) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const vImg = (bp.variants || []).find((bv: any) => (bv._id || bv.id) === v.id)?.image_url;
    if (vImg && !images.includes(vImg)) {
      images.push(vImg);
    }
  });

  return {
    id: bp._id || bp.id,
    name: bp.name,
    slug: bp.slug,
    description: bp.main_description || '',
    price: price,
    category: 'shawls', // Default category
    images: images,
    variants: variants,
    stock: variants.reduce((acc: number, v: any) => acc + v.stock, 0),
    status: bp.is_active ? 'active' : 'draft',
    createdAt: bp.created_at,
    updatedAt: bp.updated_at
  };
};

export const api = {
  // GET /products
  getProducts: async (): Promise<Product[]> => {
    try {
      const data = await handleResponse(await fetch(`${API_URL}/products/`));
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return data.map((p: any) => mapBackendProduct(p));
    } catch (error) {
      console.error('Failed to fetch products:', error);
      return [];
    }
  },

  // GET /products/:id
  getProductById: async (id: string): Promise<Product | undefined> => {
    try {
      // Since backend strictly uses slug for details, we try to fetch all and find by ID locally.
      // This is a temporary fallback until backend supports GET /products/{id}
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
      const data = await handleResponse(await fetch(`${API_URL}/products/slug/${slug}`));
      return mapBackendProduct(data);
    } catch (e) {
      console.error(`Failed to fetch product by slug ${slug}:`, e);
      return undefined;
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

  // POST /products
  createProduct: async (product: Omit<Product, 'id' | 'createdAt' | 'updatedAt'>): Promise<Product> => {
    const payload = {
      name: product.name,
      slug: product.slug,
      cover_image_url: product.images[0] || 'https://placehold.co/600x400',
      main_description: product.description,
      variants: product.variants.map((v: any) => ({
        name: v.color,
        image_url: v.image_url || product.images[0] || '',
        price: product.price,
        currency: "PKR",
        stock_status: v.stock > 0 ? "In stock" : "Out of stock",
        description: ""
      }))
    };

    const data = await handleResponse(await fetch(`${API_URL}/products/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }));

    return mapBackendProduct(data);
  },

  // PUT /products/:id
  updateProduct: async (id: string, product: Partial<Product>): Promise<Product> => {
    throw new Error("Update product endpoint not implemented in backend.");
  },

  // DELETE /products/:id
  deleteProduct: async (id: string): Promise<void> => {
    throw new Error("Delete product endpoint not implemented in backend.");
  },

  // Orders API (Mocked placeholder)
  getOrders: async (): Promise<Order[]> => {
    return [];
  },

  getOrderById: async (id: string): Promise<Order | undefined> => {
    return undefined;
  },

  createOrder: async (order: Omit<Order, 'id' | 'createdAt' | 'updatedAt'>): Promise<Order> => {
    throw new Error("Order creation not connected to backend.");
  },

  updateOrder: async (id: string, updates: Partial<Order>): Promise<Order> => {
    throw new Error("Order update not connected to backend.");
  },
};