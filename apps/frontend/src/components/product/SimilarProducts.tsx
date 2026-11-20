import Image from 'next/image';
import Link from 'next/link';
import { formatCurrency } from '@/lib/whatsapp';
import { Product } from '@/types/types';

export function SimilarProducts({ products }: { products: Product[] }) {
  if (!products.length) return null;
  return <section aria-labelledby="similar-heading" className="bg-[#fbf7f0] px-6 pb-16 text-[#2f241f]">
    <div className="mx-auto max-w-6xl">
      <h2 id="similar-heading" className="font-heading text-2xl font-semibold">More like this</h2>
      <ul className="mt-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {products.map((product) => <li key={product.id || product.slug}>
          <Link href={`/product/${product.slug}`} className="group block overflow-hidden rounded-2xl border border-[#e7dac8] bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2f241f]">
            <div className="relative aspect-[3/4] bg-[#efe5d5]">{product.images[0] && <Image src={product.images[0]} alt={product.name} fill sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 25vw" className="object-cover" />}</div>
            <div className="p-4"><p className="line-clamp-2 font-semibold">{product.name}</p><p className="mt-1 text-sm text-[#6f625a]">{formatCurrency(product.price, product.currency)}</p></div>
          </Link>
        </li>)}
      </ul>
    </div>
  </section>;
}
