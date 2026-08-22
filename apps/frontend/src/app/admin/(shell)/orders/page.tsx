import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Orders',
  description: 'Order management scaffold for the admin shell.',
};

export default function AdminOrdersPage() {
  return (
    <main id="main-content" className="space-y-8">
      <section className="rounded-[2rem] border border-[#e7dac8] bg-white p-8 shadow-sm">
        <p className="text-xs font-bold uppercase tracking-[0.3em] text-[#9a6b3f]">Orders</p>
        <h1 className="font-heading mt-3 text-4xl font-semibold tracking-tight">Order operations scaffold</h1>
        <p className="mt-4 max-w-3xl leading-7 text-[#6f625a]">
          Order review and follow-up screens can live here without altering the authenticated shell or the guard.
        </p>
      </section>

      <section className="grid gap-4 md:grid-cols-2">
        <article className="rounded-[1.75rem] border border-[#e7dac8] bg-[#fbf7f0] p-6">
          <h2 className="text-xl font-semibold text-[#2f241f]">Order queue</h2>
          <p className="mt-3 text-sm leading-6 text-[#6f625a]">List incoming enquiries, WhatsApp follow-ups, and fulfilment status.</p>
        </article>
        <article className="rounded-[1.75rem] border border-[#e7dac8] bg-[#fbf7f0] p-6">
          <h2 className="text-xl font-semibold text-[#2f241f]">Customer handoff</h2>
          <p className="mt-3 text-sm leading-6 text-[#6f625a]">Reserve this space for notes, contact details, and order confirmation steps.</p>
        </article>
      </section>
    </main>
  );
}
