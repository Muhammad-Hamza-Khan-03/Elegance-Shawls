import type { Metadata } from 'next';
import { EnquiryLookup } from '@/components/admin/EnquiryLookup';

export const metadata: Metadata = {
  title: 'Enquiries',
  description: 'Look up WhatsApp enquiry references.',
};

export default function AdminEnquiriesPage() {
  return <EnquiryLookup />;
}
