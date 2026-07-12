import { CustomerDetails, Product, ProductVariant } from '@/types/types';

const DEFAULT_WHATSAPP_NUMBER = process.env.NEXT_PUBLIC_WHATSAPP_NUMBER || '';

export const formatCurrency = (amount: number, currency = 'PKR') => {
  return `${currency} ${Number(amount || 0).toLocaleString()}`;
};

export const getWhatsAppNumber = (value = DEFAULT_WHATSAPP_NUMBER) =>
  value.replace(/[^0-9]/g, '');

export interface SingleProductOrder {
  variant: ProductVariant;
  quantity: number;
  productUrl: string;
}

export const validateSingleProductOrder = ({ variant, quantity, productUrl }: SingleProductOrder) => {
  if (!Number.isInteger(quantity) || quantity < 1) return 'Quantity must be at least 1.';
  if (variant.stock < 1) return 'This option is currently out of stock.';
  if (quantity > variant.stock) return `Only ${variant.stock} item${variant.stock === 1 ? '' : 's'} available.`;
  if (!/^https?:\/\//.test(productUrl)) return 'Storefront URL is not configured.';
  return null;
};

export const buildSingleProductMessage = (product: Product, order: SingleProductOrder) => {
  const error = validateSingleProductOrder(order);
  if (error) throw new Error(error);
  const { variant, quantity, productUrl } = order;
  const total = variant.price * quantity;

  return [
    'Assalam o Alaikum, I want to place an order from Elegance Shawls.',
    '',
    `Product: ${product.name}`,
    `SKU/Item: ${product.itemNumber || product.slug}`,
    `Color: ${variant.color}`,
    `Size: ${variant.size}`,
    `Quantity: ${quantity}`,
    `Unit price: ${formatCurrency(variant.price, product.currency)}`,
    `Total: ${formatCurrency(total, product.currency)}`,
    '',
    `Product link: ${productUrl}`,
    '',
    'Please confirm availability and delivery details.',
  ].join('\n');
};

export const buildCartMessage = (
  items: Array<{ product: Product; quantity: number; selectedColor?: string; selectedSize?: string }>,
  customer?: Partial<CustomerDetails>,
) => {
  const total = items.reduce((sum, item) => sum + item.product.price * item.quantity, 0);
  const currency = items[0]?.product.currency || 'PKR';

  const lines = items.map((item, index) => {
    const variant = [item.selectedColor, item.selectedSize].filter(Boolean).join(' / ');
    return `${index + 1}. ${item.product.name}${variant ? ` (${variant})` : ''} x ${item.quantity} = ${formatCurrency(item.product.price * item.quantity, item.product.currency)}`;
  });

  return [
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
};

export const buildWhatsAppUrl = (message: string, configuredNumber = DEFAULT_WHATSAPP_NUMBER) => {
  const number = getWhatsAppNumber(configuredNumber);
  if (!/^\d{10,15}$/.test(number)) {
    throw new Error('WhatsApp ordering is not configured.');
  }
  return `https://wa.me/${number}?text=${encodeURIComponent(message)}`;
};
