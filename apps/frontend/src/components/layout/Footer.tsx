'use client';
import Link from 'next/link';

export const Footer = () => {
  return (
    <footer className="border-t border-border bg-secondary/30">
      <div className="container py-12 md:py-16">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
          {/* Brand */}
          <div className="md:col-span-2">
            <Link href="/" className="flex items-center space-x-2 mb-4">
              <span className="font-heading text-2xl font-bold text-primary">Elegance</span>
              <span className="font-heading text-lg text-muted-foreground">Shawls</span>
            </Link>
            <p className="text-muted-foreground max-w-md">
              Discover the finest handcrafted shawls and stoles from artisans across India. 
              Each piece tells a story of tradition, craftsmanship, and timeless elegance.
            </p>
          </div>

          {/* Quick Links */}
          <div>
            <h4 className="font-heading text-lg font-semibold mb-4">Shop</h4>
            <ul className="space-y-2">
              <li>
                <Link href="/products/shawls" className="text-muted-foreground hover:text-primary transition-colors">
                  Shawls
                </Link>
              </li>
              <li>
                <Link href="/products/stoles" className="text-muted-foreground hover:text-primary transition-colors">
                  Stoles
                </Link>
              </li>
              <li>
                <Link href="/cart" className="text-muted-foreground hover:text-primary transition-colors">
                  Cart
                </Link>
              </li>
            </ul>
          </div>

          {/* Contact */}
          <div>
            <h4 className="font-heading text-lg font-semibold mb-4">Contact</h4>
            <ul className="space-y-2 text-muted-foreground">
              <li>support@eleganceshawls.com</li>
              <li>+91 98765 43210</li>
              <li>Mon - Sat, 10am - 7pm</li>
            </ul>
          </div>
        </div>

        <div className="mt-12 pt-8 border-t border-border flex flex-col md:flex-row justify-between items-center gap-4">
          <p className="text-sm text-muted-foreground">
            © 2024 Elegance Shawls. All rights reserved.
          </p>
          <div className="flex gap-6">
            <Link href="/admin" className="text-sm text-muted-foreground hover:text-primary transition-colors">
              Admin
            </Link>
          </div>
        </div>
      </div>
    </footer>
  );
};
