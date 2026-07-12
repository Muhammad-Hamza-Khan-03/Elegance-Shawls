import { describe, expect, it } from 'vitest';
import { buildSingleProductMessage, buildWhatsAppUrl, validateSingleProductOrder } from './whatsapp';
import type { Product, ProductVariant } from '@/types/types';

const variant: ProductVariant = {
  id: 'burgundy-large', color: 'Burgundy', size: 'Large', stock: 3, price: 4500,
};

const product: Product = {
  id: 'product-1', name: 'Classic Pashmina', slug: 'classic-pashmina',
  description: '', price: 4000, currency: 'PKR', category: 'shawls', images: [],
  variants: [variant], stock: 3, status: 'active', itemNumber: 'ES-001',
  createdAt: '', updatedAt: '',
};

describe('WhatsApp ordering', () => {
  it('uses the selected variant, quantity, total, SKU and absolute URL', () => {
    const message = buildSingleProductMessage(product, {
      variant, quantity: 2, productUrl: 'https://elegance.example/product/classic-pashmina',
    });
    expect(message).toContain('SKU/Item: ES-001');
    expect(message).toContain('Color: Burgundy');
    expect(message).toContain('Size: Large');
    expect(message).toContain('Quantity: 2');
    expect(message).toContain('Unit price: PKR 4,500');
    expect(message).toContain('Total: PKR 9,000');
    expect(message).toContain('Product link: https://elegance.example/product/classic-pashmina');
  });

  it('rejects unavailable stock, excessive quantities and relative links', () => {
    expect(validateSingleProductOrder({ variant: { ...variant, stock: 0 }, quantity: 1, productUrl: 'https://store.test/p' })).toContain('out of stock');
    expect(validateSingleProductOrder({ variant, quantity: 4, productUrl: 'https://store.test/p' })).toContain('Only 3');
    expect(validateSingleProductOrder({ variant, quantity: 1, productUrl: '/product/test' })).toContain('not configured');
  });

  it('refuses to create an order URL without a valid configured number', () => {
    expect(() => buildWhatsAppUrl('hello', '')).toThrow('not configured');
    expect(buildWhatsAppUrl('hello world', '+92 300 1234567')).toBe('https://wa.me/923001234567?text=hello%20world');
  });
});
