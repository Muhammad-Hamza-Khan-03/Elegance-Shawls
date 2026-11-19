import { Metadata } from 'next';
import { SavedProducts } from '@/components/product/SavedProducts';

export const metadata: Metadata = { title: 'Saved products', description: 'Products you saved for later on this device.', robots: { index: false } };

export default function WishlistRoute() {
  return <SavedProducts />;
}
