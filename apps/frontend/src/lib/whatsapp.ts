import { CustomerDetails, Product } from '@/types/types';

const DEFAULT_WHATSAPP_NUMBER = process.env.NEXT_PUBLIC_WHATSAPP_NUMBER || '';

export const formatCurrency = (amount: number, currency = 'PKR') => {
  return `${currency} ${Number(amount || 0).toLocaleString()}`;
};

export const getWhatsAppNumber = () => DEFAULT_WHATSAPP_NUMBER.replace(/[^0-9]/g, '');

export const buildSingleProductMessage = (product: Product, quantity = 1) => {
  const total = product.price * quantity;

  return [
    'Assalam o Alaikum, I want to place an order from Elegance Shawls.',
    '',
    `Product: ${product.name}`,
    `SKU/Item: ${product.itemNumber || product.slug}`,
    `Quantity: ${quantity}`,
    `Price: ${formatCurrency(product.price, product.currency)}`,
    `Total: ${formatCurrency(total, product.currency)}`,
    '',
    `Product link: ${typeof window !== 'undefined' ? window.location.href : `/product/${product.slug}`}`,
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

export const buildWhatsAppUrl = (message: string) => {
  const number = getWhatsAppNumber();
  const baseUrl = number ? `https://wa.me/${number}` : 'https://wa.me/';
  return `${baseUrl}?text=${encodeURIComponent(message)}`;
};
