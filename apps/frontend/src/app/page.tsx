import Image from 'next/image';
import Link from 'next/link';
import { api } from '@/lib/api';
import { formatCurrency } from '@/lib/whatsapp';
import { Metadata } from 'next';
import { absoluteUrl } from '@/lib/site';

export const dynamic = 'force-dynamic';
export const metadata: Metadata = { alternates: absoluteUrl('/') ? { canonical: absoluteUrl('/')! } : undefined };

export default async function Home() {
  const featured = await api.getFeaturedProducts().catch(() => []);

  return <main id="main-content" className="overflow-hidden bg-[#fbf7f0] text-[#2f241f]">
    <section className="relative border-b border-[#e7dac8]">
      <div aria-hidden="true" className="absolute -right-24 -top-32 h-96 w-96 rounded-full bg-[#c99a67]/20 blur-3xl" />
      <div className="relative mx-auto grid min-h-[calc(100vh-4rem)] max-w-6xl items-center gap-12 px-6 py-16 lg:grid-cols-[1.05fr_0.95fr] lg:py-24">
        <div className="max-w-2xl">
          <p className="mb-6 text-xs font-bold uppercase tracking-[0.36em] text-[#9a6b3f]">Elegance, made personal</p>
          <h1 className="font-heading text-5xl font-semibold leading-[1.02] tracking-[-0.04em] sm:text-6xl lg:text-7xl">The finishing layer for every occasion.</h1>
          <p className="mt-7 max-w-xl text-lg leading-8 text-[#6f625a]">Explore shawls and stoles in considered colours and styles, then choose your preferred option and order directly through WhatsApp.</p>
          <div className="mt-9 flex flex-wrap gap-3">
            <Link href="/products" className="rounded-full bg-[#2f241f] px-7 py-4 text-sm font-semibold text-white transition hover:bg-[#4a382f] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2f241f] focus-visible:ring-offset-4">Explore the collection</Link>
            <Link href="/products?category=stoles" className="rounded-full border border-[#bda98f] bg-white/60 px-7 py-4 text-sm font-semibold transition hover:bg-white">Browse stoles</Link>
          </div>
        </div>

        <div className="relative mx-auto aspect-[4/5] w-full max-w-md" aria-hidden="true">
          <div className="absolute inset-0 rotate-3 rounded-[3rem] bg-[#dac5aa]" />
          <div className="absolute inset-4 -rotate-2 overflow-hidden rounded-[2.6rem] bg-[#49362d] shadow-2xl">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_25%_20%,#c89b6a_0,transparent_35%),linear-gradient(145deg,#765341_0%,#2f241f_68%)]" />
            <div className="absolute inset-x-10 top-16 h-[56%] rounded-[45%_55%_42%_58%] border border-white/20 bg-white/8 shadow-inner" />
            <div className="absolute bottom-12 left-10 right-10 border-t border-white/25 pt-5 text-center text-xs font-semibold uppercase tracking-[0.32em] text-white/80">Shawls · Stoles · Pakistan</div>
          </div>
        </div>
      </div>
    </section>

    <section className="mx-auto max-w-6xl px-6 py-20 sm:py-24">
      <div className="mb-10 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div><p className="text-xs font-bold uppercase tracking-[0.3em] text-[#9a6b3f]">Shop by style</p><h2 className="font-heading mt-3 text-4xl font-semibold tracking-tight sm:text-5xl">Find your layer</h2></div>
        <Link href="/products" className="w-fit text-sm font-semibold text-[#765033] hover:underline">View all products →</Link>
      </div>
      <div className="grid gap-6 md:grid-cols-2">
        <Link href="/products?category=shawls" className="group relative min-h-72 overflow-hidden rounded-[2rem] bg-[#3d3029] p-8 text-white shadow-sm">
          <div aria-hidden="true" className="absolute -right-16 -top-16 h-64 w-64 rounded-full border-[3rem] border-[#c99a67]/25 transition duration-500 group-hover:scale-110" />
          <div className="relative flex h-full flex-col justify-end"><p className="text-xs font-bold uppercase tracking-[0.28em] text-[#e2c7aa]">Collection</p><h3 className="font-heading mt-2 text-4xl font-semibold">Shawls</h3><p className="mt-3 max-w-sm text-white/70">Generous layers for warmth, styling and gifting.</p></div>
        </Link>
        <Link href="/products?category=stoles" className="group relative min-h-72 overflow-hidden rounded-[2rem] bg-[#d9c1a2] p-8 text-[#2f241f] shadow-sm">
          <div aria-hidden="true" className="absolute -bottom-24 -right-8 h-72 w-72 rotate-12 rounded-[40%] bg-[#fbf7f0]/35 transition duration-500 group-hover:rotate-6" />
          <div className="relative flex h-full flex-col justify-end"><p className="text-xs font-bold uppercase tracking-[0.28em] text-[#765033]">Collection</p><h3 className="font-heading mt-2 text-4xl font-semibold">Stoles</h3><p className="mt-3 max-w-sm text-[#5e4d43]">Lighter silhouettes for versatile everyday wear.</p></div>
        </Link>
      </div>
    </section>

    {featured.length > 0 && <section className="border-y border-[#e7dac8] bg-white/55">
      <div className="mx-auto max-w-6xl px-6 py-20 sm:py-24">
        <div className="mb-10"><p className="text-xs font-bold uppercase tracking-[0.3em] text-[#9a6b3f]">Available now</p><h2 className="font-heading mt-3 text-4xl font-semibold tracking-tight sm:text-5xl">Featured pieces</h2></div>
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">{featured.map((product, index) => <Link key={product.id || product.slug} href={`/product/${product.slug}`} className="group"><div className="relative aspect-[3/4] overflow-hidden rounded-[1.6rem] bg-[#efe5d5] shadow-sm"><Image src={product.images[0]} alt={product.name} fill priority={index < 2} sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 25vw" className="object-cover transition duration-500 group-hover:scale-105" /></div><p className="mt-4 text-xs font-bold uppercase tracking-[0.22em] text-[#9a6b3f]">{product.category}</p><h3 className="mt-1 font-heading text-xl font-semibold">{product.name}</h3><p className="mt-1 text-sm font-semibold">{formatCurrency(product.price, product.currency)}</p></Link>)}</div>
      </div>
    </section>}

    <section className="mx-auto grid max-w-6xl gap-6 px-6 py-20 sm:py-24 md:grid-cols-3">
      {[['Choose with confidence', 'See available variants, prices and stock before sending your enquiry.'], ['Order directly', 'Your chosen product, option and quantity are prepared in a WhatsApp message.'], ['Clear confirmation', 'Availability, delivery and payment details are confirmed before the order is finalised.']].map(([title, text], index) => <div key={title} className="border-t border-[#bda98f] pt-6"><span className="text-xs font-bold text-[#9a6b3f]">0{index + 1}</span><h2 className="font-heading mt-5 text-2xl font-semibold">{title}</h2><p className="mt-3 leading-7 text-[#6f625a]">{text}</p></div>)}
    </section>

    <section className="bg-[#2f241f] px-6 py-20 text-center text-white sm:py-24"><div className="mx-auto max-w-3xl"><p className="text-xs font-bold uppercase tracking-[0.32em] text-[#d8b994]">Elegance Shawls</p><h2 className="font-heading mt-5 text-4xl font-semibold sm:text-5xl">Ready to find your next favourite?</h2><p className="mx-auto mt-5 max-w-xl leading-7 text-white/65">Browse the live collection and select the colour, size and quantity that suits you.</p><Link href="/products" className="mt-8 inline-block rounded-full bg-[#fbf7f0] px-7 py-4 text-sm font-semibold text-[#2f241f]">Shop the collection</Link></div></section>
  </main>;
}
