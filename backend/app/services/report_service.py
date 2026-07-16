"""
Report Service
Generates stock reports and analytics
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.item import Item
from app.models.label_mapping import LabelMapping
from app.models.stock_history import StockHistory
from app.services.report_category_service import report_category_service


class ReportService:
    STATUS_PRIORITY = {
        "out": 0,
        "low": 1,
        "normal": 2,
    }
    @staticmethod
    def get_stock_history(
        db: Session,
        item_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Dict]:
        """
        Get stock history data for time series analysis
        """
        query = db.query(
            StockHistory.timestamp,
            StockHistory.stock_level,
            StockHistory.item_id,
            Item.name.label("item_name"),
        ).join(Item, StockHistory.item_id == Item.id)

        if item_id:
            query = query.filter(StockHistory.item_id == item_id)
        if start_date:
            query = query.filter(StockHistory.timestamp >= start_date)
        if end_date:
            query = query.filter(StockHistory.timestamp <= end_date)

        results = query.order_by(StockHistory.timestamp).all()

        return [
            {
                "timestamp": r.timestamp.isoformat(),
                "stock_level": r.stock_level,
                "item_id": r.item_id,
                "item_name": r.item_name,
            }
            for r in results
        ]

    @classmethod
    def _normalize_window(
        cls,
        *,
        start_date: Optional[datetime],
        end_date: Optional[datetime],
        days: int,
    ) -> tuple[datetime, datetime]:
        resolved_end_date = end_date or datetime.utcnow()
        resolved_start_date = start_date or (resolved_end_date - timedelta(days=days))
        return resolved_start_date, resolved_end_date

    @classmethod
    def _stock_status_from_level(cls, stock_level: int, threshold: int) -> str:
        if stock_level <= 0:
            return "out"
        if stock_level < threshold:
            return "low"
        return "normal"

    @classmethod
    def _is_worsening_transition(
        cls,
        previous_status: Optional[str],
        current_status: str,
    ) -> bool:
        if current_status == "normal":
            return False
        if previous_status is None:
            return True
        return cls.STATUS_PRIORITY[current_status] < cls.STATUS_PRIORITY[previous_status]

    @classmethod
    def _get_stock_issue_events(
        cls,
        db: Session,
        *,
        start_date: datetime,
        end_date: datetime,
        include_statuses: Optional[set[str]] = None,
    ) -> List[Dict]:
        label_rows = (
            db.query(LabelMapping.item_id, LabelMapping.detection_label)
            .order_by(LabelMapping.item_id.asc(), LabelMapping.detection_label.asc())
            .all()
        )
        detection_label_by_item: Dict[str, str] = {}
        for label_row in label_rows:
            detection_label_by_item.setdefault(
                label_row.item_id,
                label_row.detection_label,
            )

        rows = (
            db.query(
                StockHistory.timestamp,
                StockHistory.item_id,
                StockHistory.stock_level,
                Item.name.label("item_name"),
                Item.category,
                Item.threshold,
            )
            .join(Item, StockHistory.item_id == Item.id)
            .filter(StockHistory.timestamp < end_date)
            .order_by(StockHistory.item_id.asc(), StockHistory.timestamp.asc())
            .all()
        )

        events: List[Dict] = []
        previous_status_by_item: Dict[str, str] = {}

        for row in rows:
            current_status = cls._stock_status_from_level(row.stock_level, row.threshold)
            previous_status = previous_status_by_item.get(row.item_id)

            if row.timestamp >= start_date and cls._is_worsening_transition(
                previous_status,
                current_status,
            ):
                if include_statuses is None or current_status in include_statuses:
                    events.append(
                        {
                            "timestamp": row.timestamp,
                            "item_id": row.item_id,
                            "item_name": row.item_name,
                            "category": row.category,
                            "detection_label": detection_label_by_item.get(row.item_id),
                            "status": current_status,
                        }
                    )

            previous_status_by_item[row.item_id] = current_status

        return events

    @classmethod
    def get_category_breakdown(
        cls,
        db: Session,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        days: int = 7,
    ) -> Dict:
        """
        Get stock incident breakdown by category over time.
        """
        resolved_start_date, resolved_end_date = cls._normalize_window(
            start_date=start_date,
            end_date=end_date,
            days=days,
        )
        events = cls._get_stock_issue_events(
            db,
            start_date=resolved_start_date,
            end_date=resolved_end_date,
        )

        rows = []
        bucket_by_day = {}

        for i in range(days):
            day_start = (resolved_start_date + timedelta(days=i)).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            data_point = {
                "name": day_start.strftime("%m/%d"),
                "date": day_start.date().isoformat(),
                "values": report_category_service.empty_values(),
            }
            rows.append(data_point)
            bucket_by_day[day_start.date()] = data_point

        for event in events:
            data_point = bucket_by_day.get(event["timestamp"].date())
            if not data_point:
                continue
            category_key = report_category_service.category_key_for_label(
                event.get("detection_label"),
            )
            data_point["values"][category_key] += 1

        return {
            "categories": report_category_service.api_categories(),
            "rows": rows,
        }

    @classmethod
    def get_trend_analysis(
        cls,
        db: Session,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        granularity: str = "day",
        days: int = 7,
    ) -> List[Dict]:
        """
        Get stock incident trend analysis over time.
        """
        del granularity
        resolved_start_date, resolved_end_date = cls._normalize_window(
            start_date=start_date,
            end_date=end_date,
            days=days,
        )
        events = cls._get_stock_issue_events(
            db,
            start_date=resolved_start_date,
            end_date=resolved_end_date,
        )

        incident_counts = {}
        for event in events:
            event_day = event["timestamp"].date()
            incident_counts[event_day] = incident_counts.get(event_day, 0) + 1

        result = []
        for i in range(days):
            day_start = (resolved_start_date + timedelta(days=i)).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            result.append(
                {
                    "name": day_start.strftime("%m/%d"),
                    "incidents": incident_counts.get(day_start.date(), 0),
                }
            )

        return result

    @classmethod
    def get_out_of_stock_trend(
        cls,
        db: Session,
        hours: int = 12,
        end_date: Optional[datetime] = None,
    ) -> List[Dict]:
        """
        Get hourly out-of-stock transition counts derived from stock history.
        """
        window_end = (end_date or datetime.utcnow()).replace(
            minute=0,
            second=0,
            microsecond=0,
        )
        window_start = window_end - timedelta(hours=hours)
        events = cls._get_stock_issue_events(
            db,
            start_date=window_start,
            end_date=window_end,
            include_statuses={"out"},
        )

        hourly_counts: Dict[datetime, int] = {}
        for event in events:
            hour_bucket = event["timestamp"].replace(
                minute=0,
                second=0,
                microsecond=0,
            )
            hourly_counts[hour_bucket] = hourly_counts.get(hour_bucket, 0) + 1

        result = []
        for i in range(hours):
            hour_start = window_start + timedelta(hours=i)
            result.append(
                {
                    "time": hour_start.strftime("%H:%M"),
                    "outOfStock": hourly_counts.get(hour_start, 0),
                }
            )

        return result

    @classmethod
    def get_recent_incident_count(
        cls,
        db: Session,
        hours: int = 1,
        end_date: Optional[datetime] = None,
    ) -> int:
        """
        Count recent stock incident transitions derived from stock history.
        """
        window_end = end_date or datetime.utcnow()
        window_start = window_end - timedelta(hours=hours)
        events = cls._get_stock_issue_events(
            db,
            start_date=window_start,
            end_date=window_end + timedelta(microseconds=1),
        )
        return len(events)

    @staticmethod
    def get_summary_stats(db: Session) -> Dict:
        """
        Get summary statistics
        """
        total_items = db.query(Item).count()
        out_of_stock = db.query(Item).filter(Item.status == "out").count()
        low_stock = db.query(Item).filter(Item.status == "low").count()
        normal_stock = db.query(Item).filter(Item.status == "normal").count()
        total_alerts = db.query(Alert).filter(Alert.status == "active").count()

        return {
            "total_items": total_items,
            "out_of_stock": out_of_stock,
            "low_stock": low_stock,
            "normal_stock": normal_stock,
            "total_alerts": total_alerts,
        }


report_service = ReportService()
