import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { AdminShell } from '@/components/admin/AdminShell';
import { verifyAdminSession } from '@/lib/admin-session';

export const metadata: Metadata = {
  title: {
    default: 'Admin dashboard',
    template: '%s | Elegance Shawls admin',
  },
  robots: { index: false, follow: false },
};

export default async function AdminShellLayout({ children }: { children: ReactNode }) {
  const session = (await cookies()).get('es_admin_session')?.value;

  if (!verifyAdminSession(session)) {
    redirect('/admin/login');
  }

  return <AdminShell>{children}</AdminShell>;
}
