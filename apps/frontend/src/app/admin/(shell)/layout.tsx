import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { AdminShell } from '@/components/admin/AdminShell';
import { fetchAdminIdentity } from '@/lib/admin-backend';
import { ADMIN_SESSION_COOKIE } from '@/lib/admin-session';

export const metadata: Metadata = {
  title: {
    default: 'Admin dashboard',
    template: '%s | Elegance Shawls admin',
  },
  robots: { index: false, follow: false },
};

export default async function AdminShellLayout({ children }: { children: ReactNode }) {
  const identity = await fetchAdminIdentity((await cookies()).get(ADMIN_SESSION_COOKIE)?.value);

  if (!identity) {
    redirect('/admin/login');
  }

  return <AdminShell account={identity}>{children}</AdminShell>;
}
