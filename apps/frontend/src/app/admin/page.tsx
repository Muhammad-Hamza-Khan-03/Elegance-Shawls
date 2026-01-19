'use client';
import { useEffect, useState } from 'react';
import { ShoppingCart, Package, AlertTriangle } from 'lucide-react';
import { AdminLayout } from '@/components/admin/adminLayout';
import { OrdersTable } from '@/components/admin/ordersTable';
import { Skeleton } from '@/components/ui/skeleton';
import { api } from '@/lib/api';
import { Order, Product } from '@/types/types';
import {useRouter,useParams} from 'next/navigation';

// const AdminDashboardPage = () => {
//   const router = useRouter();
//   const [orders, setOrders] = useState<Order[]>([]);
//   const [products, setProducts] = useState<Product[]>([]);
//   const [loading, setLoading] = useState(true);

//   useEffect(() => {
//     const fetchData = async () => {
//       try {
//         const [ordersData, productsData] = await Promise.all([
//           api.getOrders(),
//           api.getProducts(),
//         ]);
//         setOrders(ordersData);
//         setProducts(productsData);
//       } catch (error) {
//         console.error('Failed to fetch data:', error);
//       } finally {
//         setLoading(false);
//       }
//     };
//     fetchData();
//   }, []);

//   const todayOrders = orders.filter((o) => {
//     const today = new Date().toDateString();
//     return new Date(o.createdAt).toDateString() === today;
//   });

//   const pendingOrders = orders.filter((o) => o.status === 'pending');
  
//   const lowStockProducts = products.filter((p) => p.stock < 5);

//   const kpis = [
//     {
//       label: 'Orders Today',
//       value: todayOrders.length,
//       icon: ShoppingCart,
//       color: 'bg-blue-500/10 text-blue-600',
//     },
//     {
//       label: 'Pending Orders',
//       value: pendingOrders.length,
//       icon: Package,
//       color: 'bg-gold/10 text-gold',
//     },
//     {
//       label: 'Low Stock Items',
//       value: lowStockProducts.length,
//       icon: AlertTriangle,
//       color: 'bg-destructive/10 text-destructive',
//     },
//   ];

//   return (
//     <AdminLayout>
//       <div className="space-y-8">
//         <div>
//           <h1 className="font-heading text-2xl md:text-3xl font-bold">Dashboard</h1>
//           <p className="text-muted-foreground">Welcome back to your admin panel</p>
//         </div>

//         {/* KPI Cards */}
//         {loading ? (
//           <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
//             {[...Array(3)].map((_, i) => (
//               <Skeleton key={i} className="h-28 rounded-lg" />
//             ))}
//           </div>
//         ) : (
//           <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
//             {kpis.map((kpi) => (
//               <div
//                 key={kpi.label}
//                 className="bg-card rounded-lg p-6 shadow-soft"
//               >
//                 <div className="flex items-center justify-between">
//                   <div>
//                     <p className="text-sm text-muted-foreground">{kpi.label}</p>
//                     <p className="font-heading text-3xl font-bold mt-1">{kpi.value}</p>
//                   </div>
//                   <div className={`p-3 rounded-lg ${kpi.color}`}>
//                     <kpi.icon className="h-6 w-6" />
//                   </div>
//                 </div>
//               </div>
//             ))}
//           </div>
//         )}

//         {/* Recent Orders */}
//         <div>
//           <h2 className="font-heading text-xl font-semibold mb-4">Recent Orders</h2>
//           {loading ? (
//             <Skeleton className="h-64 rounded-lg" />
//           ) : (
//             <OrdersTable 
//               orders={orders.slice(0, 5)} 
//               onRowClick={(order) => router.push(`/admin/`)}
//             />
//           )}
//         </div>
//       </div>
//     </AdminLayout>
//   );
// };
const AdminDashboardPage = () => {
}
export default AdminDashboardPage;
