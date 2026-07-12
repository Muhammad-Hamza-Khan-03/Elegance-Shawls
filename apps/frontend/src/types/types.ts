export interface Product {
  id: string;
  name: string;
  slug: string;
  description: string;
  price: number;
  currency: string;
  category: 'shawls' | 'stoles';
  images: string[];
  variants: ProductVariant[];
  stock: number;
  status: 'active' | 'draft' | 'out_of_stock' | 'archived';
  material?: string;
  sizing?: string;
  weight?: string;
  itemNumber?: string | number;
  type?: string;
  createdAt: string;
  updatedAt: string;
}

export interface ProductVariant {
  id: string;
  color: string;
  size: string;
  stock: number;
  price: number;
  image_url?: string;
}

export interface CustomerDetails {
  name: string;
  phone: string;
  city: string;
  address: string;
  notes?: string;
}
