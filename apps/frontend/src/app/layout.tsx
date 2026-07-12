import type { Metadata } from "next";
import "./globals.css";
import { Toaster } from "sonner";
import { MainLayout } from "@/components/layout/mainLayout";

export const metadata: Metadata = {
  title: "Elegance Shawls | Premium Shawls & Stoles",
  description:
    "Shop elegant shawls and stoles designed for comfort, modest styling, and graceful gifting.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        <MainLayout>{children}</MainLayout>
        <Toaster position="top-right" richColors />
      </body>
    </html>
  );
}
