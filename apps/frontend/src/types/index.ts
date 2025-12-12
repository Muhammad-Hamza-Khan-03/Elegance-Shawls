export interface Product {
    id: string;
    name: string;
    slug: string;
    description: string;
    price: number;
    category: 'shawls' | 'stoles';
    images: string[];
    variants: ProductVariant[];
    stock: number;
    status: 'active' | 'draft' | 'out_of_stock';
    createdAt: string;
    updatedAt: string;
  }
  
  export interface ProductVariant {
    id: string;
    color: string;
    size: string;
    stock: number;
  }
  
  export interface CartItem {
    productId: string;
    product: Product;
    quantity: number;
    selectedColor: string;
    selectedSize: string;
  }
  
  export interface Order {
    id: string;
    customerName: string;
    email: string;
    whatsappNumber: string;
    city: string;
    address: string;
    items: OrderItem[];
    total: number;
    status: 'pending' | 'confirmed' | 'shipped' | 'delivered' | 'cancelled';
    createdAt: string;
    updatedAt: string;
  }
  
  export interface OrderItem {
    productId: string;
    productName: string;
    quantity: number;
    price: number;
    color: string;
    size: string;
  }
  
  export interface FilterState {
    colors: string[];
    sizes: string[];
    sortBy: 'price_asc' | 'price_desc' | 'newest' | 'name';
  }
  