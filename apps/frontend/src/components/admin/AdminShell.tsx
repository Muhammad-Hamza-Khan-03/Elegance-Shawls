'use client';

import type { ReactNode } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { LogOut, Package, LayoutDashboard, ShoppingBag } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

const navItems = [
  { href: '/admin/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/admin/products', label: 'Products', icon: Package },
  { href: '/admin/orders', label: 'Orders', icon: ShoppingBag },
];

export const AdminShell = ({ children }: { children: ReactNode }) => {
  const pathname = usePathname();
  const router = useRouter();

  const signOut = async () => {
    await fetch('/api/admin/session', { method: 'DELETE' }).catch(() => null);
    router.replace('/admin/login');
    router.refresh();
  };

  return (
    <div className="min-h-screen bg-[#fbf7f0] text-[#2f241f]">
      <div className="mx-auto grid min-h-screen max-w-[96rem] lg:grid-cols-[18rem_minmax(0,1fr)]">
        <aside className="border-b border-[#e7dac8] bg-white/85 px-6 py-6 backdrop-blur lg:border-b-0 lg:border-r">
          <div className="flex items-start justify-between gap-4 lg:flex-col lg:items-stretch">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.32em] text-[#9a6b3f]">Quill Panel</p>
              <h1 className="font-heading mt-2 text-3xl font-semibold">Admin shell</h1>
              <p className="mt-3 max-w-sm text-sm leading-6 text-[#6f625a]">
                Manage the product catalogue and order operations from one authenticated workspace.
              </p>
            </div>
            <Button variant="outline" className="rounded-full border-[#d8c8b4] bg-transparent px-4" onClick={signOut}>
              <LogOut className="h-4 w-4" />
              Sign out
            </Button>
          </div>

          <nav aria-label="Admin navigation" className="mt-8 space-y-2">
            {navItems.map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              const Icon = item.icon;

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    'flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-medium transition',
                    active
                      ? 'bg-[#2f241f] text-white shadow-sm'
                      : 'text-[#5f4f44] hover:bg-[#f4ebe0] hover:text-[#2f241f]'
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="mt-8 rounded-3xl border border-[#e7dac8] bg-[#fbf7f0] p-4 text-sm text-[#6f625a]">
            <p className="font-semibold text-[#2f241f]">Ready for product management</p>
            <p className="mt-2 leading-6">
              This shell is wired for product creation, editing, publishing and order follow-up pages.
            </p>
          </div>
        </aside>

        <main className="flex min-w-0 flex-col">
          <header className="border-b border-[#e7dac8] bg-white/70 px-6 py-5 backdrop-blur">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.3em] text-[#9a6b3f]">Authenticated workspace</p>
                <p className="mt-2 text-sm text-[#6f625a]">Protected by the shared admin key session.</p>
              </div>
              <Link href="/" className="text-sm font-semibold text-[#765033] hover:underline">
                View storefront →
              </Link>
            </div>
          </header>

          <div className="flex-1 px-6 py-8 lg:px-8">
            <div className="mx-auto max-w-6xl">{children}</div>
          </div>
        </main>
      </div>
    </div>
  );
};
