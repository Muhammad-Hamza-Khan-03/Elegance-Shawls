import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Dashboard',
  description: 'Admin dashboard overview for Elegance Shawls.',
};

const quickStats = [
  { label: 'Products', value: 'Ready', detail: 'Product CRUD pages can attach here next.' },
  { label: 'Orders', value: 'Ready', detail: 'Order follow-up pages can use this shell.' },
  { label: 'Access', value: 'Protected', detail: 'Session cookie gate blocks unauthenticated access.' },
];

export default function AdminDashboardPage() {
  return (
    <main id="main-content" className="space-y-8">
      <section className="rounded-[2rem] border border-[#e7dac8] bg-white p-8 shadow-sm">
        <p className="text-xs font-bold uppercase tracking-[0.3em] text-[#9a6b3f]">Dashboard</p>
        <h1 className="font-heading mt-3 text-4xl font-semibold tracking-tight">Admin shell overview</h1>
        <p className="mt-4 max-w-3xl leading-7 text-[#6f625a]">
          This shell is intentionally lightweight: it provides a secure workspace, shared navigation, and a structure that product-management pages can plug into without rebuilding the shell later.
        </p>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        {quickStats.map((stat) => (
          <article key={stat.label} className="rounded-[1.5rem] border border-[#e7dac8] bg-[#fbf7f0] p-6">
            <p className="text-xs font-bold uppercase tracking-[0.28em] text-[#9a6b3f]">{stat.label}</p>
            <h2 className="mt-3 text-2xl font-semibold text-[#2f241f]">{stat.value}</h2>
            <p className="mt-2 text-sm leading-6 text-[#6f625a]">{stat.detail}</p>
          </article>
        ))}
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <article className="rounded-[2rem] border border-[#e7dac8] bg-white p-8 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-[0.28em] text-[#9a6b3f]">Next up</p>
          <h2 className="font-heading mt-3 text-2xl font-semibold">Product management pages</h2>
          <p className="mt-3 leading-7 text-[#6f625a]">
            Attach list, create, edit and status workflows to the products route without changing the shell or auth gate.
          </p>
        </article>
        <article className="rounded-[2rem] border border-[#e7dac8] bg-white p-8 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-[0.28em] text-[#9a6b3f]">Navigation</p>
          <h2 className="font-heading mt-3 text-2xl font-semibold">Consistent admin flow</h2>
          <p className="mt-3 leading-7 text-[#6f625a]">
            Use the left rail to move between dashboard, products and orders while keeping the storefront isolated.
          </p>
        </article>
      </section>
    </main>
  );
}
