'use client';

import Link from 'next/link';
import { Menu, X } from 'lucide-react';
import { useState } from 'react';
import { Button } from '@/components/ui/button';

const navLinks = [
  { href: '/', label: 'Home' },
  { href: '/products', label: 'All products' },
  { href: '/products?category=shawls', label: 'Shawls' },
  { href: '/products?category=stoles', label: 'Stoles' },
];

export const Navbar = () => {
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 w-full border-b border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
        <Link href="/" className="flex items-baseline gap-2" aria-label="Elegance Shawls home">
          <span className="font-heading text-2xl font-bold text-primary">Elegance</span>
          <span className="font-heading text-lg text-muted-foreground">Shawls</span>
        </Link>

        <nav aria-label="Main navigation" className="hidden items-center gap-8 md:flex">
          {navLinks.map((link) => (
            <Link key={link.href} href={link.href} className="text-sm font-medium text-muted-foreground transition-colors hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
              {link.label}
            </Link>
          ))}
        </nav>

        <Button variant="ghost" size="icon" className="md:hidden" onClick={() => setIsMenuOpen((open) => !open)} aria-label={isMenuOpen ? 'Close navigation menu' : 'Open navigation menu'} aria-expanded={isMenuOpen} aria-controls="mobile-navigation">
          {isMenuOpen ? <X aria-hidden="true" className="h-5 w-5" /> : <Menu aria-hidden="true" className="h-5 w-5" />}
        </Button>
      </div>

      {isMenuOpen && <div id="mobile-navigation" className="border-t border-border/40 md:hidden">
        <nav aria-label="Mobile navigation" className="mx-auto max-w-6xl space-y-1 px-6 py-3">
          {navLinks.map((link) => (
            <Link key={link.href} href={link.href} className="block rounded-lg px-2 py-3 text-sm font-medium text-muted-foreground hover:bg-secondary hover:text-primary" onClick={() => setIsMenuOpen(false)}>
              {link.label}
            </Link>
          ))}
        </nav>
      </div>}
    </header>
  );
};
