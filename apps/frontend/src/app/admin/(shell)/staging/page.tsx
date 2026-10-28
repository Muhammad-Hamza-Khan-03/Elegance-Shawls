import type { Metadata } from 'next';
import { StagedProductReview } from '@/components/admin/StagedProductReview';

export const metadata: Metadata = {
  title: 'Staged products',
  description: 'Review, approve and publish ingested products.',
};

export default function AdminStagingPage() {
  return <StagedProductReview />;
}
