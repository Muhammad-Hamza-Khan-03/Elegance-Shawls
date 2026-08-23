import type { Metadata } from 'next';
import { AdminProductManager } from '@/components/admin/ProductManagement';

export const metadata: Metadata = {
  title: 'Products',
  description: 'Product management structure for the admin shell.',
};

export default function AdminProductsPage() {
  return <AdminProductManager />;
}
