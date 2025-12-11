from pydantic import BaseModel
from decimal import Decimal

class DashboardStats(BaseModel):
    total_orders: int
    total_revenue: Decimal
    pending_orders: int
    total_products: int
    low_stock_products: int

class SalesReport(BaseModel):
    date: str
    total_sales: Decimal
    order_count: int