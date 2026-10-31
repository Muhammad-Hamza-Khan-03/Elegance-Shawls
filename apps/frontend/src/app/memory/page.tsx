import type { Metadata } from 'next';
import { MemoryManagement } from '@/components/memory/MemoryManagement';

export const metadata: Metadata = { title: 'Manage memory', description: 'Review and manage your explicitly saved memory.' };

export default function MemoryPage() { return <MemoryManagement />; }
