'use client';

import Link from 'next/link';
import { ChevronDown, Menu, ShoppingBag, X } from 'lucide-react';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { useCart } from '@/components/cart/CartProvider';
import { CATEGORY_LABELS, PRODUCT_CATEGORIES } from '@/lib/categories';

const navLinks = [
  { href: '/', label: 'Home' },
];

const categoryLinks = PRODUCT_CATEGORIES.map((key) => ({ href: `/products?category=${key}`, label: CATEGORY_LABELS[key] }));
const linkClass = 'text-sm font-medium text-muted-foreground transition-colors hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary';

// "All products" links to the full shop; the chevron (or hover) reveals the product types.
function ProductsMenu() {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}
      onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}
      onKeyDown={(event) => { if (event.key === 'Escape') setOpen(false); }}>
      <div className="flex items-center gap-1">
        <Link href="/products" className={linkClass} onClick={() => setOpen(false)}>All products</Link>
        <button type="button" aria-label="Show product types" aria-expanded={open} aria-controls="products-menu" onClick={() => setOpen((value) => !value)} className="rounded-full p-1 text-muted-foreground hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
          <ChevronDown aria-hidden="true" className={`h-4 w-4 transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>
      </div>
      {open && <ul id="products-menu" className="absolute left-0 top-full z-50 min-w-44 pt-2">
        <li className="list-none overflow-hidden rounded-2xl border border-border bg-background p-1.5 shadow-lg">
          <ul>{categoryLinks.map((link) => <li key={link.href}><Link href={link.href} onClick={() => setOpen(false)} className="block rounded-xl px-4 py-2.5 text-sm font-medium text-foreground hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">{link.label}</Link></li>)}</ul>
        </li>
      </ul>}
    </div>
  );
}

export const Navbar = () => {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const { itemCount } = useCart();

  return (
    <header className="sticky top-0 z-50 w-full border-b border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
        <Link href="/" className="flex items-baseline gap-2" aria-label="Elegance Shawls home">
          <span className="font-heading text-2xl font-bold text-primary">Elegance</span>
          <span className="font-heading text-lg text-muted-foreground">Shawls</span>
        </Link>

        <nav aria-label="Main navigation" className="hidden items-center gap-8 md:flex">
          {navLinks.map((link) => <Link key={link.href} href={link.href} className={linkClass}>{link.label}</Link>)}
          <ProductsMenu />
          <Link href="/cart" className="inline-flex items-center gap-2 rounded-full border border-border px-4 py-2 text-sm font-semibold text-primary transition hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
            <ShoppingBag className="h-4 w-4" aria-hidden="true" />
            Cart
            <span className="rounded-full bg-primary px-2 py-0.5 text-xs text-primary-foreground">{itemCount}</span>
          </Link>
        </nav>

        <div className="flex items-center gap-2 md:hidden">
          <Link href="/cart" className="inline-flex items-center gap-2 rounded-full border border-border px-3 py-2 text-sm font-semibold text-primary" aria-label={`Cart with ${itemCount} items`}>
            <ShoppingBag className="h-4 w-4" aria-hidden="true" />
            <span className="rounded-full bg-primary px-2 py-0.5 text-xs text-primary-foreground">{itemCount}</span>
          </Link>
          <Button variant="ghost" size="icon" className="md:hidden" onClick={() => setIsMenuOpen((open) => !open)} aria-label={isMenuOpen ? 'Close navigation menu' : 'Open navigation menu'} aria-expanded={isMenuOpen} aria-controls="mobile-navigation">
            {isMenuOpen ? <X aria-hidden="true" className="h-5 w-5" /> : <Menu aria-hidden="true" className="h-5 w-5" />}
          </Button>
        </div>
      </div>

      {isMenuOpen && <div id="mobile-navigation" className="border-t border-border/40 md:hidden">
        <nav aria-label="Mobile navigation" className="mx-auto max-w-6xl space-y-1 px-6 py-3">
          {[...navLinks, { href: '/products', label: 'All products' }].map((link) => (
            <Link key={link.href} href={link.href} className="block rounded-lg px-2 py-3 text-sm font-medium text-muted-foreground hover:bg-secondary hover:text-primary" onClick={() => setIsMenuOpen(false)}>
              {link.label}
            </Link>
          ))}
          {categoryLinks.map((link) => (
            <Link key={link.href} href={link.href} className="block rounded-lg py-2.5 pl-6 pr-2 text-sm text-muted-foreground hover:bg-secondary hover:text-primary" onClick={() => setIsMenuOpen(false)}>
              {link.label}
            </Link>
          ))}
        </nav>
      </div>}
    </header>
  );
};
