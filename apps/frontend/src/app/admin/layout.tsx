import { AdminLayout } from "@/components/admin/adminLayout";
import { ReactNode } from "react";

export default function AdminRootLayout({ children }: { children: ReactNode }) {
  return <AdminLayout>{children}</AdminLayout>;
}