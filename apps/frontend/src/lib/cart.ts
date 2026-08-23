import { Product, ProductVariant } from '@/types/types';
import { buildWhatsAppUrl, formatCurrency } from '@/lib/whatsapp';

export type CartProductSnapshot = Pick<
  Product,
  'id' | 'name' | 'slug' | 'description' | 'price' | 'currency' | 'category' | 'images' | 'itemNumber' | 'material' | 'sizing' | 'weight'
>;

export type CartVariantSnapshot = Pick<ProductVariant, 'id' | 'color' | 'size' | 'stock' | 'price' | 'image_url'>;

export interface CartItem {
  lineId: string;
  productId: string;
  variantId: string;
  quantity: number;
  product: CartProductSnapshot;
  variant: CartVariantSnapshot;
}

export const CART_STORAGE_KEY = 'elegance-shawls.cart.v1';

export const getCartLineId = (productId: string, variantId: string) => `${productId}:${variantId}`;

export const clampCartQuantity = (quantity: number, stock: number) => {
  const max = Math.max(0, Math.floor(Number(stock) || 0));
  const normalized = Math.floor(Number(quantity) || 0);

  if (max < 1) return 0;
  if (normalized < 1) return 1;
  return Math.min(normalized, max);
};

export const createCartItem = (
  product: Product,
  variant: ProductVariant,
  quantity = 1,
): CartItem | null => {
  const requestedQuantity = Math.floor(Number(quantity) || 0);
  if (variant.stock < 1 || requestedQuantity < 1) return null;
  const nextQuantity = clampCartQuantity(requestedQuantity, variant.stock);
  if (nextQuantity < 1) return null;

  return {
    lineId: getCartLineId(product.id, variant.id),
    productId: product.id,
    variantId: variant.id,
    quantity: nextQuantity,
    product: {
      id: product.id,
      name: product.name,
      slug: product.slug,
      description: product.description,
      price: product.price,
      currency: product.currency,
      category: product.category,
      images: product.images,
      itemNumber: product.itemNumber,
      material: product.material,
      sizing: product.sizing,
      weight: product.weight,
    },
    variant: {
      id: variant.id,
      color: variant.color,
      size: variant.size,
      stock: variant.stock,
      price: variant.price,
      image_url: variant.image_url,
    },
  };
};

const normalizeItem = (item: CartItem | null | undefined) => {
  if (!item) return null;
  const requestedQuantity = Math.floor(Number(item.quantity) || 0);
  if (requestedQuantity < 1 || !item.productId || !item.variantId) return null;
  const quantity = clampCartQuantity(requestedQuantity, item.variant?.stock ?? 0);
  if (quantity < 1) return null;

  return {
    ...item,
    lineId: item.lineId || getCartLineId(item.productId, item.variantId),
    quantity,
    product: item.product,
    variant: item.variant,
  } satisfies CartItem;
};

export const normalizeCartItems = (items: CartItem[]) =>
  items
    .map((item) => normalizeItem(item))
    .filter((item): item is CartItem => Boolean(item));

export const addCartItem = (items: CartItem[], product: Product, variant: ProductVariant, quantity = 1) => {
  const nextItem = createCartItem(product, variant, quantity);
  if (!nextItem) return items;

  const index = items.findIndex((item) => item.lineId === nextItem.lineId);
  if (index === -1) return normalizeCartItems([...items, nextItem]);

  const existing = items[index];
  const mergedQuantity = clampCartQuantity(existing.quantity + nextItem.quantity, variant.stock);
  const updated = { ...existing, quantity: mergedQuantity, product: nextItem.product, variant: nextItem.variant };
  return normalizeCartItems([...items.slice(0, index), updated, ...items.slice(index + 1)]);
};

export const setCartItemQuantity = (items: CartItem[], lineId: string, quantity: number) => {
  const index = items.findIndex((item) => item.lineId === lineId);
  if (index === -1) return items;

  const current = items[index];
  const requestedQuantity = Math.floor(Number(quantity) || 0);
  if (requestedQuantity < 1) {
    return items.filter((item) => item.lineId !== lineId);
  }

  const nextQuantity = clampCartQuantity(requestedQuantity, current.variant.stock);
  if (nextQuantity < 1) {
    return items.filter((item) => item.lineId !== lineId);
  }

  const updated = { ...current, quantity: nextQuantity };
  return normalizeCartItems([...items.slice(0, index), updated, ...items.slice(index + 1)]);
};

export const incrementCartItem = (items: CartItem[], lineId: string) => {
  const item = items.find((entry) => entry.lineId === lineId);
  if (!item) return items;
  return setCartItemQuantity(items, lineId, item.quantity + 1);
};

export const decrementCartItem = (items: CartItem[], lineId: string) => {
  const item = items.find((entry) => entry.lineId === lineId);
  if (!item) return items;
  return setCartItemQuantity(items, lineId, item.quantity - 1);
};

export const removeCartItem = (items: CartItem[], lineId: string) => items.filter((item) => item.lineId !== lineId);

export const clearCartItems = () => [] as CartItem[];

export const getCartSummary = (items: CartItem[]) => {
  const itemCount = items.reduce((total, item) => total + item.quantity, 0);
  const subtotal = items.reduce((total, item) => total + item.variant.price * item.quantity, 0);
  const currency = items[0]?.product.currency || 'PKR';
  return { itemCount, subtotal, currency };
};

export const buildCartCheckoutUrl = (items: CartItem[], whatsappNumber: string, customer?: { name?: string; phone?: string; city?: string; address?: string; notes?: string }) => {
  const currency = items[0]?.product.currency || 'PKR';
  const total = items.reduce((sum, item) => sum + item.variant.price * item.quantity, 0);
  const lines = items.map((item, index) => {
    const variant = [item.variant.color, item.variant.size].filter(Boolean).join(' / ');
    return `${index + 1}. ${item.product.name}${variant ? ` (${variant})` : ''} x ${item.quantity} = ${formatCurrency(item.variant.price * item.quantity, currency)}`;
  });

  const message = [
    'Assalam o Alaikum, I want to place an order from Elegance Shawls.',
    '',
    customer?.name ? `Name: ${customer.name}` : 'Name:',
    customer?.phone ? `Phone: ${customer.phone}` : 'Phone:',
    customer?.city ? `City: ${customer.city}` : 'City:',
    customer?.address ? `Address: ${customer.address}` : 'Address:',
    customer?.notes ? `Notes: ${customer.notes}` : '',
    '',
    'Items:',
    ...lines,
    '',
    `Total: ${formatCurrency(total, currency)}`,
    '',
    'Please confirm availability and delivery details.',
  ].filter(Boolean).join('\n');

  return buildWhatsAppUrl(message, whatsappNumber);
};
