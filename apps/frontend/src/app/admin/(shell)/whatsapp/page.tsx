import type { Metadata } from 'next';
import { WhatsAppAdmin } from '@/components/admin/WhatsAppAdmin';

export const metadata: Metadata = {
  title: 'WhatsApp',
  description: 'WhatsApp bridge status, pairing and unlinked chats.',
};

export default function AdminWhatsAppPage() {
  return <WhatsAppAdmin />;
}
