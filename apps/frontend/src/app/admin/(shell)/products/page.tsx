import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Products',
  description: 'Product management structure for the admin shell.',
};

const sections = [
  {
    title: 'Catalogue list',
    text: 'This route is reserved for product tables, filters, bulk actions, and status chips.',
  },
  {
    title: 'Create and edit',
    text: 'Use this area for product forms, variant management, and image handling.',
  },
  {
    title: 'Publish flow',
    text: 'Connect draft, active, out-of-stock, and archived transitions here.',
  },
];

export default function AdminProductsPage() {
  return (
    <main id="main-content" className="space-y-8">
      <section className="rounded-[2rem] border border-[#e7dac8] bg-white p-8 shadow-sm">
        <p className="text-xs font-bold uppercase tracking-[0.3em] text-[#9a6b3f]">Products</p>
        <h1 className="font-heading mt-3 text-4xl font-semibold tracking-tight">Product workspace ready</h1>
        <p className="mt-4 max-w-3xl leading-7 text-[#6f625a]">
          The shell already provides the authenticated navigation and layout that product-management screens need.
        </p>
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        {sections.map((section) => (
          <article key={section.title} className="rounded-[1.75rem] border border-[#e7dac8] bg-[#fbf7f0] p-6">
            <h2 className="text-xl font-semibold text-[#2f241f]">{section.title}</h2>
            <p className="mt-3 text-sm leading-6 text-[#6f625a]">{section.text}</p>
          </article>
        ))}
      </section>
    </main>
  );
}
