import type { Metadata } from "next";
import "./globals.css";
import { Toaster } from "sonner";
import { MainLayout } from "@/components/layout/mainLayout";
import { getSiteUrl } from "@/lib/site";

const siteUrl = getSiteUrl();

export const metadata: Metadata = {
  metadataBase: siteUrl ? new URL(siteUrl) : undefined,
  title: { default: "Elegance Shawls | Shawls & Stoles in Pakistan", template: "%s | Elegance Shawls" },
  description:
    "Browse shawls and stoles in Pakistan and send your selected product, variant and quantity through WhatsApp.",
  openGraph: {
    type: "website",
    siteName: "Elegance Shawls",
    title: "Elegance Shawls | Shawls & Stoles in Pakistan",
    description: "Browse available shawls and stoles and order through WhatsApp.",
    url: siteUrl || undefined,
  },
  twitter: { card: "summary_large_image", title: "Elegance Shawls", description: "Browse available shawls and stoles in Pakistan." },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        <a href="#main-content" className="skip-link">Skip to main content</a>
        <MainLayout>{children}</MainLayout>
        <Toaster position="top-right" richColors />
      </body>
    </html>
  );
}
