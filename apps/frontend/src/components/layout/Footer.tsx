import Link from 'next/link';

export const Footer = () => (
  <footer className="border-t border-border bg-secondary/30">
    <div className="mx-auto max-w-6xl px-6 py-12 md:py-16">
      <div className="grid gap-10 md:grid-cols-[2fr_1fr_1fr_1fr]">
        <div>
          <Link href="/" className="mb-4 flex items-baseline gap-2" aria-label="Elegance Shawls home">
            <span className="font-heading text-2xl font-bold text-primary">Elegance</span>
            <span className="font-heading text-lg text-muted-foreground">Shawls</span>
          </Link>
          <p className="max-w-md leading-7 text-muted-foreground">
            Shawls and stoles for customers in Pakistan, with product selection and order enquiries handled through WhatsApp.
          </p>
        </div>
        <div>
          <h2 className="mb-4 font-heading text-lg font-semibold">Help</h2>
          <ul className="space-y-3 text-muted-foreground">
            <li><Link href="/delivery" className="hover:text-primary">Delivery</Link></li>
            <li><Link href="/returns" className="hover:text-primary">Returns</Link></li>
            <li><Link href="/contact" className="hover:text-primary">Contact</Link></li>
            <li><Link href="/privacy" className="hover:text-primary">Privacy</Link></li>
            <li><Link href="/terms" className="hover:text-primary">Terms</Link></li>
          </ul>
        </div>
        <div>
          <h2 className="mb-4 font-heading text-lg font-semibold">Shop</h2>
          <ul className="space-y-3 text-muted-foreground">
            <li><Link href="/products" className="hover:text-primary">All products</Link></li>
            <li><Link href="/products?category=shawls" className="hover:text-primary">Shawls</Link></li>
            <li><Link href="/products?category=stoles" className="hover:text-primary">Stoles</Link></li>
          </ul>
        </div>
        <div>
          <h2 className="mb-4 font-heading text-lg font-semibold">Ordering</h2>
          <p className="leading-7 text-muted-foreground">Availability, delivery and payment details are confirmed with you before an order is finalised.</p>
        </div>
      </div>
      <p className="mt-12 border-t border-border pt-8 text-sm text-muted-foreground">© {new Date().getFullYear()} Elegance Shawls. All rights reserved.</p>
    </div>
  </footer>
);
