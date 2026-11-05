'use client';

import { ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import { Navbar } from './Navbar';
import { Footer } from './Footer';
import dynamic from 'next/dynamic';
import { ASSISTANT_ENABLED } from '@/lib/assistant';
import { CartProvider } from '@/components/cart/CartProvider';

const AssistantPanel = ASSISTANT_ENABLED
  ? dynamic(() => import('@/components/assistant/AssistantPanel').then((m) => m.AssistantPanel), { ssr: false })
  : null;

interface MainLayoutProps {
  children: ReactNode;
}

export const MainLayout = ({ children }: MainLayoutProps) => {
  const pathname = usePathname();

  if (pathname.startsWith('/admin')) {
    return <>{children}</>;
  }

  return (
    <CartProvider>
      <div className="min-h-screen flex flex-col">
        <Navbar />
        <div className="flex-1">{children}</div>
        <Footer />
        {AssistantPanel && <AssistantPanel />}
      </div>
    </CartProvider>
  );
};
