import { Metadata } from 'next';
import Link from 'next/link';
import { InfoPage } from '@/components/layout/InfoPage';

export const metadata: Metadata = { title: 'Frequently asked questions', description: 'How ordering, availability, delivery and returns work at Elegance Shawls.' };

// Answers only restate what the Delivery, Returns and Contact pages already say; no new policy is introduced here.
export default function FaqPage() {
  return <InfoPage eyebrow="Customer information" title="Frequently asked questions" intro="Short answers about ordering with us. Details are on the linked pages.">
    <section><h2>How do I order?</h2><p>There is no online checkout. Add items to your cart or open a product and choose Order on WhatsApp. You get an enquiry reference and a WhatsApp message with your selection, and the order is finalised in that conversation.</p></section>
    <section><h2>Are the prices and stock final?</h2><p>Prices and availability are checked again when you start the enquiry, and availability is confirmed manually before your order is finalised.</p></section>
    <section><h2>How does delivery work?</h2><p>Availability, charge and timing are confirmed with you before you proceed. See <Link href="/delivery" className="underline">Delivery</Link>.</p></section>
    <section><h2>Can I return an item?</h2><p>Please contact us in your WhatsApp order conversation first; eligibility is confirmed before anything is sent back. See <Link href="/returns" className="underline">Returns</Link>.</p></section>
    <section><h2>How do I choose a size?</h2><p>See the <Link href="/size-guide" className="underline">size guide</Link>.</p></section>
    <section><h2>Something else?</h2><p>Message us from the <Link href="/contact" className="underline">contact page</Link>.</p></section>
  </InfoPage>;
}
