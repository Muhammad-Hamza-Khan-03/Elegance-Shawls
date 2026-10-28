'use client';

import { MouseEvent, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { useRouter } from 'next/navigation';
import { Minus, Plus, ShoppingBag } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Product } from '@/types/types';
import { useCart } from '@/components/cart/CartProvider';
import { api } from '@/lib/api';
import { CART_VERIFICATION_TTL_MS } from '@/lib/cart';
import { toast } from 'sonner';
import {
  buildSingleProductMessage,
  buildWhatsAppUrl,
  formatCurrency,
  validateSingleProductOrder,
} from '@/lib/whatsapp';

interface ProductExperienceProps {
  product: Product;
  siteUrl: string;
  whatsappNumber: string;
}

export const getInitialVariant = (product: Product) =>
  product.variants.find((variant) => variant.stock > 0) || product.variants[0];

export const clampQuantity = (value: number, stock: number) =>
  Math.max(1, Math.min(stock || 1, Number(value) || 1));

export function ProductExperience({ product, siteUrl, whatsappNumber }: ProductExperienceProps) {
  const { items, addItem, setItemQuantity } = useCart();
  const firstAvailable = getInitialVariant(product);
  const [selectedId, setSelectedId] = useState(firstAvailable?.id || product.variants[0]?.id || '');
  const [quantity, setQuantity] = useState(1);
  const [activeImage, setActiveImage] = useState(firstAvailable?.image_url || product.images[0] || '');

  const selected = product.variants.find((variant) => variant.id === selectedId);
  const cartLine = items.find((item) => item.productId === product.id && item.variantId === selected?.id);

  const selectVariant = (variantId: string) => {
    const variant = product.variants.find((item) => item.id === variantId);
    setSelectedId(variantId);
    setQuantity(1);
    setActiveImage(variant?.image_url || product.images[0] || '');
  };

  const productUrl = siteUrl ? `${siteUrl.replace(/\/$/, '')}/product/${product.slug}` : '';
  const configurationError = !siteUrl
    ? 'Online ordering is temporarily unavailable because the storefront URL is not configured.'
    : !/^\d{10,15}$/.test(whatsappNumber.replace(/\D/g, ''))
      ? 'Online ordering is temporarily unavailable because WhatsApp is not configured.'
      : null;
  const orderError = selected
    ? validateSingleProductOrder({ variant: selected, quantity, productUrl })
    : 'No product option is available.';

  // The page may have been open for a while: re-check the published product
  // before handing off, and re-render from the server if anything changed.
  const router = useRouter();
  const verifiedAtRef = useRef(0);
  useEffect(() => {
    verifiedAtRef.current = Date.now();
  }, [product]);

  const handleOrderClick = async (event: MouseEvent<HTMLAnchorElement>) => {
    if (Date.now() - verifiedAtRef.current <= CART_VERIFICATION_TTL_MS) return;
    event.preventDefault();
    try {
      const current = await api.getPublishedProduct(product.slug);
      const variant = current?.variants.find((entry) => entry.id === selected?.id);
      if (!current || !selected || !variant || current.id !== product.id || current.currency !== product.currency
        || variant.price !== selected.price || variant.stock < quantity) {
        toast.error('This product has changed. Review the updated details before ordering.');
        router.refresh();
        return;
      }
      verifiedAtRef.current = Date.now();
      toast.success('Availability confirmed. Tap "Order on WhatsApp" again to continue.');
    } catch {
      toast.error('We could not confirm current availability. Please try again.');
    }
  };

  const handleAddToCart = () => {
    if (!selected) return;
    if (cartLine) {
      setItemQuantity(cartLine.lineId, quantity);
      toast.success(`${product.name} updated in cart.`);
      return;
    }

    addItem(product, selected, quantity);
    toast.success(`${product.name} added to cart.`);
  };

  const whatsappUrl = useMemo(() => {
    if (!selected || configurationError || orderError) return null;
    try {
      return buildWhatsAppUrl(
        buildSingleProductMessage(product, { variant: selected, quantity, productUrl }),
        whatsappNumber,
      );
    } catch {
      return null;
    }
  }, [configurationError, orderError, product, productUrl, quantity, selected, whatsappNumber]);

  const gallery = Array.from(new Set([
    activeImage,
    ...product.images,
    ...product.variants.map((variant) => variant.image_url).filter(Boolean),
  ].filter(Boolean))) as string[];

  return (
    <main id="main-content" className="min-h-screen bg-[#fbf7f0] px-6 pb-28 pt-12 text-[#2f241f] md:pb-12">
      <section className="mx-auto grid max-w-6xl gap-10 lg:grid-cols-[1.05fr_0.95fr]">
        <div className="space-y-4">
          <Link href="/products" className="text-sm font-medium text-[#9a6b3f] hover:underline">
            ← Back to collection
          </Link>
          <div className="relative aspect-[3/4] overflow-hidden rounded-3xl border border-[#e7dac8] bg-[#efe5d5] shadow-sm">
            <Image src={activeImage} alt={`${product.name}${selected ? ` in ${selected.color}` : ''}`} fill priority sizes="(max-width: 1024px) 100vw, 55vw" className="object-cover" />
          </div>
          {gallery.length > 1 && (
            <div className="grid grid-cols-4 gap-3" aria-label="Product images">
              {gallery.slice(0, 8).map((image, index) => (
                <button key={image} type="button" onClick={() => setActiveImage(image)} aria-label={`View product image ${index + 1}`} aria-pressed={activeImage === image} className={`relative aspect-square overflow-hidden rounded-2xl border bg-[#efe5d5] ${activeImage === image ? 'border-[#2f241f] ring-2 ring-[#2f241f]/20' : 'border-[#e7dac8]'}`}>
                  <Image src={image} alt="" fill sizes="(max-width: 1024px) 25vw, 12vw" className="object-cover" />
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-7 rounded-3xl border border-[#e7dac8] bg-white/80 p-8 shadow-sm lg:sticky lg:top-8 lg:self-start">
          <div className="space-y-4">
            <p className="text-xs font-semibold uppercase tracking-[0.3em] text-[#9a6b3f]">{product.category}</p>
            <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">{product.name}</h1>
            <p className="text-2xl font-semibold">{formatCurrency(selected?.price ?? product.price, product.currency)}</p>
            <p className={`text-sm font-medium ${selected?.stock ? 'text-emerald-700' : 'text-red-700'}`} aria-live="polite">
              {selected?.stock ? `${selected.stock} available` : 'Out of stock'}
            </p>
          </div>

          {product.description && <p className="leading-8 text-[#6f625a]">{product.description}</p>}

          <div className="grid gap-3 rounded-2xl bg-[#fbf7f0] p-5 text-sm text-[#6f625a]">
            {product.material && <p><span className="font-semibold text-[#2f241f]">Material:</span> {product.material}</p>}
            {product.sizing && <p><span className="font-semibold text-[#2f241f]">Sizing:</span> {product.sizing}</p>}
            {product.weight && <p><span className="font-semibold text-[#2f241f]">Weight:</span> {product.weight}</p>}
            {product.itemNumber && <p><span className="font-semibold text-[#2f241f]">Item:</span> {product.itemNumber}</p>}
          </div>

          <fieldset className="space-y-3">
            <legend className="font-semibold">Choose color and size</legend>
            <div role="radiogroup" aria-label="Available product options" className="grid gap-2 sm:grid-cols-2">
              {product.variants.map((variant) => (
                <button key={variant.id} type="button" role="radio" aria-checked={selectedId === variant.id} disabled={variant.stock < 1} onClick={() => selectVariant(variant.id)} className={`rounded-2xl border px-4 py-3 text-left text-sm transition ${selectedId === variant.id ? 'border-[#2f241f] bg-[#2f241f] text-white' : 'border-[#e7dac8] bg-[#fbf7f0]'} disabled:cursor-not-allowed disabled:opacity-45`}>
                  <span className="block font-semibold">{variant.color}</span>
                  <span className="block text-xs opacity-75">{variant.size} · {variant.stock > 0 ? `${variant.stock} available` : 'Out of stock'}</span>
                </button>
              ))}
            </div>
          </fieldset>

          <div className="space-y-3">
            <label htmlFor="quantity" className="font-semibold">Quantity</label>
            <div className="flex w-fit items-center overflow-hidden rounded-full border border-[#e7dac8] bg-[#fbf7f0]">
              <button type="button" aria-label="Decrease quantity" onClick={() => setQuantity((value) => Math.max(1, value - 1))} disabled={quantity <= 1} className="p-3 disabled:opacity-35"><Minus className="h-4 w-4" /></button>
              <input id="quantity" type="number" min={1} max={selected?.stock || 1} value={quantity} onChange={(event) => setQuantity(clampQuantity(Number(event.target.value), selected?.stock || 0))} inputMode="numeric" className="w-14 bg-transparent text-center font-semibold outline-none" />
              <button type="button" aria-label="Increase quantity" onClick={() => setQuantity((value) => Math.min(selected?.stock || 1, value + 1))} disabled={!selected || quantity >= selected.stock} className="p-3 disabled:opacity-35"><Plus className="h-4 w-4" /></button>
            </div>
          </div>

          <div className="rounded-2xl bg-[#fbf7f0] p-4 text-sm">
            <div className="flex justify-between gap-4"><span>Order total</span><strong>{formatCurrency((selected?.price || product.price) * quantity, product.currency)}</strong></div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <Button type="button" onClick={handleAddToCart} className="rounded-full bg-[#d9c1a2] px-8 py-4 text-sm font-semibold text-[#2f241f] transition hover:bg-[#cbb08c]">
              <ShoppingBag className="h-4 w-4" aria-hidden="true" />
              {cartLine ? 'Update cart item' : 'Add to cart'}
            </Button>
            {whatsappUrl ? (
              <a href={whatsappUrl} target="_blank" rel="noopener noreferrer" onClick={handleOrderClick} className="rounded-full bg-[#2f241f] px-8 py-4 text-center text-sm font-semibold text-white transition hover:bg-[#4a382f]">
                Order on WhatsApp
              </a>
            ) : (
              <button type="button" disabled className="rounded-full bg-[#8b817c] px-8 py-4 text-center text-sm font-semibold text-white">Order unavailable</button>
            )}
          </div>

          {(configurationError || orderError) && <p role="alert" className="text-center text-sm text-red-700">{configurationError || orderError}</p>}
          {cartLine && <p className="text-center text-sm text-[#6f625a]">This variant is already in your cart. Use the cart page to adjust quantity across products.</p>}
          <p className="text-center text-xs leading-6 text-[#6f625a]">WhatsApp will open with your selected product details. Availability and delivery are confirmed manually.</p>
        </div>
      </section>
      {whatsappUrl && (
        <a href={whatsappUrl} target="_blank" rel="noopener noreferrer" onClick={handleOrderClick} className="fixed inset-x-4 bottom-4 z-40 rounded-full bg-[#2f241f] px-8 py-4 text-center text-sm font-semibold text-white shadow-xl md:hidden">
          Order on WhatsApp
        </a>
      )}
    </main>
  );
}
