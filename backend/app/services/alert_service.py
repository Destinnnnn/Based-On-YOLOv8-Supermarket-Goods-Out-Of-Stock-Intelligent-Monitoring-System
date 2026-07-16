"""
Alert Service
Handles alert creation and management
"""
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Dict
import logging

from app.models.alert import Alert
from app.models.item import Item

logger = logging.getLogger(__name__)

class AlertService:
    # Store WebSocket connections for broadcasting
    active_connections: List = []

    @classmethod
    def register_connection(cls, websocket):
        """Register a new WebSocket connection"""
        cls.active_connections.append(websocket)
        logger.info(f"New alert connection registered. Total: {len(cls.active_connections)}")

    @classmethod
    def unregister_connection(cls, websocket):
        """Unregister a WebSocket connection"""
        if websocket in cls.active_connections:
            cls.active_connections.remove(websocket)
        logger.info(f"Alert connection unregistered. Total: {len(cls.active_connections)}")

    @classmethod
    async def broadcast_alert(cls, alert_data: dict):
        """Broadcast alert to all connected clients"""
        disconnected = []
        for connection in cls.active_connections:
            try:
                await connection.send_json({
                    'type': 'alert',
                    'data': alert_data
                })
            except Exception as e:
                logger.error(f"Error broadcasting to connection: {e}")
                disconnected.append(connection)

        # Remove disconnected clients
        for conn in disconnected:
            cls.unregister_connection(conn)

    @staticmethod
    def create_alert_from_status_change(db: Session, status_change: Dict) -> Alert:
        """
        Create an alert based on status change

        Args:
            db: Database session
            status_change: Dict with item_id, old_status, new_status, current_stock, threshold

        Returns:
            Created Alert object
        """
        item_id = status_change['item_id']
        item_name = status_change['item_name']
        new_status = status_change['new_status']
        current_stock = status_change['current_stock']
        threshold = status_change['threshold']

        # Determine alert type and message
        if new_status == 'out':
            alert_type = 'critical'
            message = f"商品 [{item_name}] 已缺货！当前数量: {current_stock}"
        elif new_status == 'low':
            alert_type = 'warning'
            message = f"商品 [{item_name}] 库存不足，当前数量: {current_stock}，阈值: {threshold}"
        else:
            # Status improved, no alert needed
            return None

        # Create alert
        alert = Alert(
            item_id=item_id,
            alert_type=alert_type,
            message=message,
            status='active'
        )

        db.add(alert)
        db.commit()
        db.refresh(alert)

        logger.info(f"Created {alert_type} alert for {item_name}")

        return alert

    @staticmethod
    def resolve_active_alerts_for_item(db: Session, item_id: str) -> int:
        alerts = (
            db.query(Alert)
            .filter(Alert.item_id == item_id, Alert.status == "active")
            .all()
        )
        for alert in alerts:
            alert.status = "resolved"
            alert.resolved_at = datetime.utcnow()

        if alerts:
            db.commit()
            logger.info("Resolved %s active alert(s) for item %s", len(alerts), item_id)

        return len(alerts)

    @staticmethod
    def sync_alerts_for_status_change(db: Session, status_change: Dict) -> Alert | None:
        old_status = status_change["old_status"]
        new_status = status_change["new_status"]
        item_id = status_change["item_id"]

        status_priority = {"normal": 2, "low": 1, "out": 0}

        if status_priority[new_status] < status_priority[old_status]:
            return AlertService.create_alert_from_status_change(db, status_change)

        if new_status != old_status:
            AlertService.resolve_active_alerts_for_item(db, item_id)

        return None

    @staticmethod
    async def process_status_changes(db: Session, status_changes: List[Dict]):
        """
        Process status changes and create alerts

        Args:
            db: Database session
            status_changes: List of status change dicts
        """
        for change in status_changes:
            # Only create alerts for worsening conditions
            old_status = change['old_status']
            new_status = change['new_status']

            # Status priority: normal > low > out
            status_priority = {'normal': 2, 'low': 1, 'out': 0}

            if status_priority[new_status] < status_priority[old_status]:
                # Status worsened, create alert
                alert = AlertService.create_alert_from_status_change(db, change)

                if alert:
                    # Broadcast to connected clients
                    alert_data = {
                        'id': alert.id,
                        'item_id': alert.item_id,
                        'alert_type': alert.alert_type,
                        'message': alert.message,
                        'status': alert.status,
                        'created_at': alert.created_at.isoformat()
                    }
                    await AlertService.broadcast_alert(alert_data)

alert_service = AlertService()
