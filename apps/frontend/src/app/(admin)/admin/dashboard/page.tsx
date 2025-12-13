'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { ShoppingCart, Package, AlertTriangle } from 'lucide-react';
import { AdminLayout } from '@/components/admin/adminLayout';
import { OrdersTable } from '@/components/admin/ordersTable';
import { Skeleton } from '@/components/ui/skeleton';
import { api, BackendOrder, DashboardStatsResponse } from '@/lib/api';
import { Order } from '@/types/index';
import { useRouter } from 'next/navigation';
import { useAdminStore } from '@/store/adminStore';
import { OrdersTableSkeleton } from '@/components/admin/LoadingTable';

const AdminDashboardPage = () => {
  const router = useRouter();
  const { token, isAuthenticated } = useAdminStore();
  const [orders, setOrders] = useState<Order[]>([]);
  const [kpiCounts, setKpiCounts] = useState({
    ordersToday: 0,
    pendingOrders: 0,
    lowStock: 0,
  });
  const [loadingOrders, setLoadingOrders] = useState(true);
  const [loadingStats, setLoadingStats] = useState(true);

  const [error, setError] = useState<string | null>(null);

  const normalizeStatus = (status: string): Order['status'] => {
    const normalized = status?.toLowerCase();
    if (normalized === 'confirmed') return 'confirmed';
    if (normalized === 'shipped') return 'shipped';
    if (normalized === 'delivered') return 'delivered';
    if (normalized === 'cancelled') return 'cancelled';
    return 'pending';
  };

  const mapBackendOrder = (order: BackendOrder): Order => ({
    id: String(order.id),
    customerName: order.email ?? 'Customer',
    email: order.email ?? '',
    whatsappNumber: order.whatsapp ?? '',
    city: order.location ?? '',
    address: order.address ?? '',
    items:
      order.order_items?.map((item) => ({
        productId: String(item.product_variant_id),
        productName: item.product_variant?.color ?? 'Item',
        quantity: item.quantity,
        price: Number(item.price ?? 0),
        color: item.product_variant?.color ?? '',
        size: item.product_variant?.size ?? '',
      })) ?? [],
    total: Number(order.total_amount ?? 0),
    status: normalizeStatus(order.status),
    createdAt: order.created_at,
    updatedAt: order.updated_at ?? order.created_at,
  });

 

  const deriveKpis = (
    stats: DashboardStatsResponse | null,
    ordersData: Order[],
  ) => {
    const todayStr = new Date().toDateString();
    const ordersToday = stats?.total_orders ?? ordersData.filter((o) => new Date(o.createdAt).toDateString() === todayStr).length;
    const pendingOrders = stats?.pending_orders ?? 0;
    const lowStock = stats?.low_stock_products ?? 0;

    return { ordersToday, pendingOrders, lowStock };
  };

  const fetchDashboardData = useCallback(async (signal?: AbortSignal) => {
    if (!token) {
      setLoadingOrders(false);
      setLoadingStats(false);
      return;
    }

    setError(null);

    try {
      setLoadingStats(true);
      setLoadingOrders(true);

      const [dashboardStats, backendOrders] = await Promise.all([
        api.getDashboardStats({ token, signal }).catch(() => null),
        api.getOrders({ token, signal }).finally(() => setLoadingOrders(false))
      ]);

      setLoadingStats(false);

      const ordersData = backendOrders.map(mapBackendOrder);
      const derived = deriveKpis(dashboardStats, ordersData);

      setOrders(ordersData);
      setKpiCounts(derived);
    } catch (err) {
      if ((err as any)?.name === 'AbortError') return;
      console.error('Failed to fetch dashboard data', err);
      setError('Unable to load dashboard data. Please try again.');

      setLoadingOrders(false);
      setLoadingStats(false);
    }
  }, [token]);

  useEffect(() => {
    if (!isAuthenticated || !token) {
      router.replace('/login');
      return;
    }

    const controller = new AbortController();
    fetchDashboardData(controller.signal);

    return () => controller.abort();
  }, [fetchDashboardData, isAuthenticated, router, token]);

  const sortedOrders = useMemo(() => {
    const weight = (status: Order['status']) =>
      status === 'pending' ? 0 : 1;

    return orders
      .slice()
      .sort((a, b) => {
        const weightDiff = weight(a.status) - weight(b.status);
        if (weightDiff !== 0) return weightDiff;
        return a.createdAt < b.createdAt ? 1 : -1;
      });
  }, [orders]);

  const kpis = [
    {
      label: 'Orders Today',
      value: kpiCounts.ordersToday,
      icon: ShoppingCart,
      color: 'bg-blue-500/10 text-blue-600',
    },
    {
      label: 'Pending Orders',
      value: kpiCounts.pendingOrders,
      icon: Package,
      color: 'bg-gold/10 text-gold',
    },
    {
      label: 'Low Stock Items',
      value: kpiCounts.lowStock,
      icon: AlertTriangle,
      color: 'bg-destructive/10 text-destructive',
    },
  ];

  return (
    <AdminLayout>
      <div className="space-y-8">
        <div>
          <h1 className="font-heading text-2xl md:text-3xl font-bold">Dashboard</h1>
          <p className="text-muted-foreground">Welcome back to your admin panel</p>
        </div>

        {error && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {/* KPI Cards */}
        {loadingStats ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {kpis.map((_, i) => (
              <Skeleton key={i} className="h-28 rounded-lg" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {kpis.map((kpi) => (
              <div key={kpi.label} className="bg-card rounded-lg p-6 shadow-soft">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-muted-foreground">{kpi.label}</p>
                    <p className="font-heading text-3xl font-bold mt-1">
                      {kpi.value}
                    </p>
                  </div>
                  <div className={`p-3 rounded-lg ${kpi.color}`}>
                    <kpi.icon className="h-6 w-6" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Recent Orders */}
        <div>
          <h2 className="font-heading text-xl font-semibold mb-4">Recent Orders</h2>
          {loadingOrders ? (
            <OrdersTableSkeleton />

          ) : (
            <OrdersTable
              orders={sortedOrders}
              onRowClick={(order: any) => router.push(`/admin/orders/${order.id}`)}
            />
          )}
        </div>
      </div>
    </AdminLayout>
  );
};

export default AdminDashboardPage;
