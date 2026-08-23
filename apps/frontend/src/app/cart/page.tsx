import { Metadata } from 'next';
import { absoluteUrl } from '@/lib/site';
import { CartPage } from '@/components/cart/CartPage';

export const metadata: Metadata = {
  title: 'Cart',
  description: 'Review your shared cart and adjust quantities before placing an order.',
  alternates: absoluteUrl('/cart') ? { canonical: absoluteUrl('/cart')! } : undefined,
};

export default function CartRoute() {
  return <CartPage />;
}
