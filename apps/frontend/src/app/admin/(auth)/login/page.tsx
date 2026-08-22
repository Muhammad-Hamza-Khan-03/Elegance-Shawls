import type { Metadata } from 'next';
import { redirect } from 'next/navigation';
import { AdminLoginForm } from '@/components/admin/AdminLoginForm';
import { verifyAdminSession } from '@/lib/admin-session';
import { cookies } from 'next/headers';

export const metadata: Metadata = {
  title: 'Admin login',
  description: 'Sign in to the Elegance Shawls admin shell.',
};

export default async function AdminLoginPage() {
  const session = (await cookies()).get('es_admin_session')?.value;

  if (verifyAdminSession(session)) {
    redirect('/admin/dashboard');
  }

  return (
    <main id="main-content" className="min-h-screen bg-[#fbf7f0] px-6 py-16 text-[#2f241f]">
      <div className="mx-auto grid min-h-[calc(100vh-8rem)] max-w-6xl items-center gap-10 lg:grid-cols-[1.1fr_0.9fr]">
        <section className="max-w-2xl">
          <p className="text-xs font-bold uppercase tracking-[0.35em] text-[#9a6b3f]">Quill Panel</p>
          <h1 className="font-heading mt-4 text-5xl font-semibold tracking-tight sm:text-6xl">Authenticated admin access</h1>
          <p className="mt-6 max-w-xl text-lg leading-8 text-[#6f625a]">
            Sign in with the shared admin key to reach the dashboard shell and navigate to product and order management.
          </p>
          <ul className="mt-8 space-y-3 text-sm leading-6 text-[#5f4f44]">
            <li>• Unauthorized visitors are redirected before they can view admin screens.</li>
            <li>• Authenticated admins get a dedicated dashboard shell with navigation.</li>
            <li>• Product and order pages are scaffolded for the next implementation slices.</li>
          </ul>
        </section>

        <section className="rounded-[2rem] border border-[#e7dac8] bg-white p-8 shadow-sm sm:p-10">
          <p className="text-xs font-bold uppercase tracking-[0.3em] text-[#9a6b3f]">Sign in</p>
          <h2 className="font-heading mt-3 text-3xl font-semibold">Welcome back</h2>
          <p className="mt-3 text-sm leading-6 text-[#6f625a]">Use the admin key configured on the server.</p>
          <div className="mt-8">
            <AdminLoginForm />
          </div>
        </section>
      </div>
    </main>
  );
}
