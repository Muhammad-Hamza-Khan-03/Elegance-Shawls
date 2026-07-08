import Link from 'next/link';
import { notFound } from 'next/navigation';
import { api } from '@/lib/api';
import { buildSingleProductMessage, buildWhatsAppUrl, formatCurrency } from '@/lib/whatsapp';

export const dynamic = 'force-dynamic';

export default async function ProductDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const product = await api.getProductBySlug(slug);

  if (!product || product.status !== 'active') {
    notFound();
  }

  const whatsappMessage = buildSingleProductMessage(product, 1);
  const whatsappUrl = buildWhatsAppUrl(whatsappMessage);

  return (
    <main className="min-h-screen bg-[#fbf7f0] px-6 py-12 text-[#2f241f]">
      <section className="mx-auto grid max-w-6xl gap-10 lg:grid-cols-[1.05fr_0.95fr]">
        <div className="space-y-4">
          <Link href="/products" className="text-sm font-medium text-[#9a6b3f] hover:underline">
            ← Back to collection
          </Link>
          <div className="overflow-hidden rounded-3xl border border-[#e7dac8] bg-[#efe5d5] shadow-sm">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={product.images[0]}
              alt={product.name}
              className="h-full max-h-[760px] w-full object-cover"
            />
          </div>
          {product.images.length > 1 && (
            <div className="grid grid-cols-4 gap-3">
              {product.images.slice(1, 5).map((image) => (
                <div key={image} className="aspect-square overflow-hidden rounded-2xl border border-[#e7dac8] bg-[#efe5d5]">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={image} alt={product.name} className="h-full w-full object-cover" />
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-8 rounded-3xl border border-[#e7dac8] bg-white/80 p-8 shadow-sm lg:sticky lg:top-8 lg:self-start">
          <div className="space-y-4">
            <p className="text-xs font-semibold uppercase tracking-[0.3em] text-[#9a6b3f]">
              {product.category}
            </p>
            <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">{product.name}</h1>
            <p className="text-2xl font-semibold">{formatCurrency(product.price, product.currency)}</p>
          </div>

          {product.description && (
            <p className="leading-8 text-[#6f625a]">{product.description}</p>
          )}

          <div className="grid gap-3 rounded-2xl bg-[#fbf7f0] p-5 text-sm text-[#6f625a]">
            {product.material && <p><span className="font-semibold text-[#2f241f]">Material:</span> {product.material}</p>}
            {product.sizing && <p><span className="font-semibold text-[#2f241f]">Sizing:</span> {product.sizing}</p>}
            {product.weight && <p><span className="font-semibold text-[#2f241f]">Weight:</span> {product.weight}</p>}
            {product.itemNumber && <p><span className="font-semibold text-[#2f241f]">Item:</span> {product.itemNumber}</p>}
          </div>

          {product.variants.length > 0 && (
            <div className="space-y-3">
              <h2 className="font-semibold">Available options</h2>
              <div className="flex flex-wrap gap-2">
                {product.variants.map((variant) => (
                  <span
                    key={variant.id}
                    className="rounded-full border border-[#e7dac8] bg-[#fbf7f0] px-4 py-2 text-sm"
                  >
                    {variant.color}
                  </span>
                ))}
              </div>
            </div>
          )}

          <a
            href={whatsappUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="block rounded-full bg-[#2f241f] px-8 py-4 text-center text-sm font-semibold text-white transition hover:bg-[#4a382f]"
          >
            Order on WhatsApp
          </a>

          <p className="text-center text-xs leading-6 text-[#6f625a]">
            You will be redirected to WhatsApp with product details. Availability and delivery will be confirmed manually.
          </p>
        </div>
      </section>
    </main>
  );
}
