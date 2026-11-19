import { Metadata } from 'next';
import Link from 'next/link';
import { InfoPage } from '@/components/layout/InfoPage';

export const metadata: Metadata = { title: 'Size guide', description: 'How to check the size and fit of a shawl or stole before ordering.' };

// Deliberately no measurement table: sizes differ per product, so inventing figures here would be wrong.
export default function SizeGuidePage() {
  return <InfoPage eyebrow="Customer information" title="Size guide" intro="Shawls and stoles differ in length and width from piece to piece, so check the product you are looking at.">
    <section><h2>On the product page</h2><p>Choose the size or option shown on the product page. Each option lists its own details and price, and the message sent to WhatsApp repeats your selection.</p></section>
    <section><h2>Not sure about the fit?</h2><ul><li>Compare with a shawl or stole you already own and measure its length and width.</li><li>Ask us for the exact dimensions of a piece before you order.</li><li>Tell us how you plan to wear it (draped, wrapped or as a scarf) and we will advise.</li></ul></section>
    <section><h2>Ask us</h2><p>Message us from the <Link href="/contact" className="underline">contact page</Link>. Questions about delivery are on the <Link href="/faq" className="underline">FAQ</Link>.</p></section>
  </InfoPage>;
}
