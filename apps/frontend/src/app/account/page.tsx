import type { Metadata } from 'next';
import { AccountSignIn } from '@/components/account/AccountSignIn';

export const metadata: Metadata = { title: 'Your account', description: 'Sign in to manage what the shopping assistant remembers about you.' };

export default function AccountPage() {
  return (
    <main id="main-content" className="mx-auto max-w-xl space-y-4 px-6 py-12">
      <h1 className="font-heading text-3xl font-bold">Your account</h1>
      <p className="text-muted-foreground">Signing in is optional. It lets the assistant remember only what you ask it to, and you can view or delete it any time.</p>
      <AccountSignIn />
    </main>
  );
}
