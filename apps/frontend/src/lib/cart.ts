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

export interface CartIssue {
  lineId: string;
  message: string;
}

export const CART_VERIFICATION_TTL_MS = 60_000;

const describeLine = (item: CartItem) => {
  const variant = [item.variant.color, item.variant.size].filter(Boolean).join(' / ');
  return `${item.product.name}${variant ? ` (${variant})` : ''}`;
};

// Rebuild cart lines from the current published catalogue. `current` maps each
// cart slug to its published product, or null when it is no longer published.
// Backend price, currency and stock always replace the browser snapshot.
export const reconcileCartItems = (items: CartItem[], current: Map<string, Product | null>) => {
  const next: CartItem[] = [];
  const issues: CartIssue[] = [];

  for (const item of items) {
    const label = describeLine(item);
    const product = current.get(item.product.slug);
    if (!product || product.status !== 'active' || product.id !== item.productId) {
      issues.push({ lineId: item.lineId, message: `${label} is no longer available and was removed from your cart.` });
      continue;
    }
    const variant = product.variants.find((entry) => entry.id === item.variantId);
    if (!variant) {
      issues.push({ lineId: item.lineId, message: `${label} is no longer offered in this option and was removed from your cart.` });
      continue;
    }
    if (variant.stock < 1) {
      issues.push({ lineId: item.lineId, message: `${label} is sold out and was removed from your cart.` });
      continue;
    }

    const quantity = Math.min(item.quantity, variant.stock);
    if (quantity < item.quantity) {
      issues.push({ lineId: item.lineId, message: `Only ${variant.stock} of ${label} available; quantity reduced from ${item.quantity} to ${quantity}.` });
    }
    if (variant.price !== item.variant.price || product.currency !== item.product.currency) {
      issues.push({
        lineId: item.lineId,
        message: `${label} price changed from ${formatCurrency(item.variant.price, item.product.currency)} to ${formatCurrency(variant.price, product.currency)}.`,
      });
    }
    const refreshed = createCartItem(product, variant, quantity);
    if (refreshed) next.push(refreshed);
  }

  return { items: next, issues };
};

export interface CartCheckoutOptions {
  siteUrl?: string;
  reference?: string;
  customer?: { name?: string; phone?: string; city?: string; address?: string; notes?: string };
}

export const buildCartCheckoutUrl = (items: CartItem[], whatsappNumber: string, { siteUrl = '', customer, reference }: CartCheckoutOptions = {}) => {
  const currency = items[0]?.product.currency || 'PKR';
  const total = items.reduce((sum, item) => sum + item.variant.price * item.quantity, 0);
  const baseUrl = siteUrl.replace(/\/$/, '');
  const lines = items.flatMap((item, index) => [
    `${index + 1}. ${item.product.name}`,
    `   SKU/Item: ${item.product.itemNumber || item.product.slug}`,
    `   Color / Size: ${[item.variant.color, item.variant.size].filter(Boolean).join(' / ')}`,
    `   Quantity: ${item.quantity} x ${formatCurrency(item.variant.price, item.product.currency)} = ${formatCurrency(item.variant.price * item.quantity, item.product.currency)}`,
    ...(baseUrl ? [`   Link: ${baseUrl}/product/${item.product.slug}`] : []),
  ]);

  const message = [
    'Assalam o Alaikum, I want to place an order from Elegance Shawls.',
    ...(reference ? [`Enquiry reference: ${reference}`] : []),
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
