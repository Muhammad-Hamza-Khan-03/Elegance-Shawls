import { Order } from '@/types';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { cn } from '@/lib/utils';

interface OrdersTableProps {
  orders: Order[];
  onRowClick?: (order: Order) => void;
}

const statusColors: Record<Order['status'], string> = {
  pending: 'bg-blue-100 text-blue-700 border-blue-200',
  confirmed: 'bg-purple-100 text-purple-700 border-purple-200',
  shipped: 'bg-purple-100 text-purple-700 border-purple-200',
  delivered: 'bg-purple-100 text-purple-700 border-purple-200',
  cancelled: 'bg-destructive/20 text-destructive border-destructive/30',
};

export const OrdersTable = ({ orders, onRowClick }: OrdersTableProps) => {
  const formatPrice = (price: number) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'PKR',
      maximumFractionDigits: 0,
    }).format(price);
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-IN', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    });
  };

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Order ID</TableHead>
            <TableHead>Customer</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Total</TableHead>
            <TableHead>Date</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {orders.map((order) => (
            <TableRow
              key={order.id}
              className={cn(
                "transition-colors",
                onRowClick && "cursor-pointer hover:bg-muted/50"
              )}
              onClick={() => onRowClick?.(order)}
            >
              <TableCell className="font-medium">{order.id}</TableCell>
              <TableCell>
                <div>
                  <p className="font-medium">{order.customerName}</p>
                  <p className="text-sm text-muted-foreground">{order.city}</p>
                </div>
              </TableCell>
              <TableCell>
                <Badge
                  variant="outline"
                  className={cn("capitalize", statusColors[order.status])}
                >
                  {order.status}
                </Badge>
              </TableCell>
              <TableCell className="text-right font-medium">
                {formatPrice(order.total)}
              </TableCell>
              <TableCell className="text-muted-foreground">
                {formatDate(order.createdAt)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
};
