"""
Reports API Endpoints
Provides stock analytics and reporting
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional

from app.api.v1.endpoints.auth import get_current_user
from app.db.database import get_db
from app.services.report_service import report_service
from app.models.alert import Alert
from app.models.item import Item

router = APIRouter(dependencies=[Depends(get_current_user)])

@router.get("/stock-history")
def get_stock_history(
    item_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get stock history data for time series charts

    Args:
        item_id: Optional item ID filter
        start_date: Start date (ISO format)
        end_date: End date (ISO format)
    """
    # Parse dates
    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None

    data = report_service.get_stock_history(
        db=db,
        item_id=item_id,
        start_date=start_dt,
        end_date=end_dt
    )

    return {"data": data}

@router.get("/category-breakdown")
def get_category_breakdown(
    days: int = Query(7, ge=1, le=90),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get stock incident breakdown by product category

    Args:
        days: Number of days to analyze
        start_date: Start date (ISO format)
        end_date: End date (ISO format)
    """
    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None

    data = report_service.get_category_breakdown(
        db=db,
        start_date=start_dt,
        end_date=end_dt,
        days=days
    )

    return data

@router.get("/trend-analysis")
def get_trend_analysis(
    days: int = Query(7, ge=1, le=90),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    granularity: str = Query('day', pattern='^(day|week|month)$'),
    db: Session = Depends(get_db)
):
    """
    Get stock incident trend analysis over time

    Args:
        days: Number of days to analyze
        start_date: Start date (ISO format)
        end_date: End date (ISO format)
        granularity: Time granularity (day/week/month)
    """
    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None

    data = report_service.get_trend_analysis(
        db=db,
        start_date=start_dt,
        end_date=end_dt,
        granularity=granularity,
        days=days
    )

    return data

@router.get("/summary")
def get_summary_stats(db: Session = Depends(get_db)):
    """
    Get summary statistics for dashboard
    """
    stats = report_service.get_summary_stats(db)
    return stats

@router.get("/dashboard-stats")
def get_dashboard_stats(db: Session = Depends(get_db)):
    """
    Get dashboard statistics including recent alerts
    """
    stats = report_service.get_summary_stats(db)
    recent_alerts = db.query(Alert).filter(Alert.status == 'active').count()
    recent_incidents = report_service.get_recent_incident_count(db=db, hours=1)

    return {
        "total_items": stats['total_items'],
        "low_stock_count": stats['low_stock'],
        "out_of_stock_count": stats['out_of_stock'],
        "recent_alerts_count": recent_alerts,
        "recent_incidents_count": recent_incidents,
    }

@router.get("/recent-alerts")
def get_recent_alerts(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """
    Get recent alerts for dashboard
    """
    alerts = db.query(Alert).filter(
        Alert.status == 'active'
    ).order_by(Alert.created_at.desc()).limit(limit).all()

    # Join with items to get item names
    result = []
    for alert in alerts:
        item = db.query(Item).filter(Item.id == alert.item_id).first()
        result.append({
            "id": alert.id,
            "type": alert.alert_type,
            "message": alert.message,
            "time": alert.created_at.isoformat(),
            "item_name": item.name if item else "Unknown"
        })

    return result

@router.get("/stock-trend-today")
def get_stock_trend_today(
    hours: int = Query(12, ge=1, le=24),
    db: Session = Depends(get_db)
):
    """
    Get out-of-stock transition trend for recent hours.
    """
    return report_service.get_out_of_stock_trend(db=db, hours=hours)
