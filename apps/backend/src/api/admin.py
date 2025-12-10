from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List
from ..core.database import get_db
from ..core.security import get_current_admin
from ..schemas import DashboardStats, SalesReport
from ..services.order_service import OrderService

router = APIRouter(prefix="/admin", tags=["Admin"])

@router.get("/dashboard", response_model=DashboardStats)
def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_admin = Depends(get_current_admin)
):
    """Get dashboard statistics (admin only)"""
    stats = OrderService.get_dashboard_stats(db)
    return stats

@router.get("/sales-report", response_model=List[SalesReport])
def get_sales_report(
    days: int = Query(30, ge=1, le=365, description="Number of days to include in report"),
    db: Session = Depends(get_db),
    current_admin = Depends(get_current_admin)
):
    """Get sales report for last N days (admin only)"""
    report = OrderService.get_sales_report(db, days=days)
    return report