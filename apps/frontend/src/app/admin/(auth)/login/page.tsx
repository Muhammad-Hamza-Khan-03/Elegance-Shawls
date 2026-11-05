import type { Metadata } from 'next';
import { redirect } from 'next/navigation';
import { AdminLoginForm } from '@/components/admin/AdminLoginForm';
import { fetchAdminIdentity } from '@/lib/admin-backend';
import { ADMIN_SESSION_COOKIE } from '@/lib/admin-session';
import { cookies } from 'next/headers';

export const metadata: Metadata = {
  title: 'Admin login',
  robots: { index: false, follow: false },
  description: 'Sign in to manage Elegance Shawls.',
};

export default async function AdminLoginPage() {
  if (await fetchAdminIdentity((await cookies()).get(ADMIN_SESSION_COOKIE)?.value)) {
    redirect('/admin/dashboard');
  }

  return (
    <main id="main-content" className="min-h-screen bg-[#fbf7f0] px-6 py-16 text-[#2f241f]">
      <div className="mx-auto grid min-h-[calc(100vh-8rem)] max-w-6xl items-center gap-10 lg:grid-cols-[1.1fr_0.9fr]">
        <section className="max-w-2xl">
          <p className="text-xs font-bold uppercase tracking-[0.35em] text-[#9a6b3f]">Elegance Admin</p>
          <h1 className="font-heading mt-4 text-5xl font-semibold tracking-tight sm:text-6xl">Store admin</h1>
          <p className="mt-6 max-w-xl text-lg leading-8 text-[#6f625a]">
            Sign in with your individual admin account to manage the catalogue, review imported products and keep stock up to date.
          </p>
        </section>

        <section className="rounded-[2rem] border border-[#e7dac8] bg-white p-8 shadow-sm sm:p-10">
          <p className="text-xs font-bold uppercase tracking-[0.3em] text-[#9a6b3f]">Sign in</p>
          <h2 className="font-heading mt-3 text-3xl font-semibold">Welcome back</h2>
          <p className="mt-3 text-sm leading-6 text-[#6f625a]">Use the email and password of your admin account. Ask an owner if you need one.</p>
          <div className="mt-8">
            <AdminLoginForm />
          </div>
        </section>
      </div>
    </main>
  );
}
