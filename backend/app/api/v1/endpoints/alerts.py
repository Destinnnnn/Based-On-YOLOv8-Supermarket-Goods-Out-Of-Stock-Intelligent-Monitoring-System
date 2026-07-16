"""
Alert API Endpoints
Handles alert management and WebSocket notifications
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.api.v1.endpoints.auth import authenticate_websocket, get_current_active_admin, get_current_user
from app.db.database import get_db
from app.models.alert import Alert
from app.models.user import User
from app.services.alert_service import AlertService
from app.schemas.item import AlertResponse

router = APIRouter()

@router.websocket("/stream")
async def alert_stream(websocket: WebSocket):
    """
    WebSocket endpoint for real-time alert notifications
    """
    from app.db.database import SessionLocal

    db = SessionLocal()

    try:
        authenticate_websocket(websocket, db)
        await websocket.accept()
        AlertService.register_connection(websocket)

        # Keep connection alive
        while True:
            # Wait for messages (heartbeat)
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        AlertService.unregister_connection(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        AlertService.unregister_connection(websocket)
    finally:
        db.close()

@router.get("/", response_model=List[AlertResponse])
def get_alerts(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = Query(None, pattern="^(active|resolved)$"),
    alert_type: Optional[str] = Query(None, pattern="^(warning|critical)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get alerts with filtering and pagination

    Args:
        skip: Number of records to skip
        limit: Maximum number of records to return
        status: Filter by status (active/resolved)
        alert_type: Filter by type (warning/critical)
    """
    query = db.query(Alert).order_by(Alert.created_at.desc())

    if status:
        query = query.filter(Alert.status == status)
    if alert_type:
        query = query.filter(Alert.alert_type == alert_type)

    alerts = query.offset(skip).limit(limit).all()
    return alerts

@router.get("/{alert_id}", response_model=AlertResponse)
def get_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single alert by ID"""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert

@router.patch("/{alert_id}/resolve")
def resolve_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    """Mark an alert as resolved"""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.status = "resolved"
    alert.resolved_at = datetime.utcnow()
    db.commit()

    return {"message": "Alert resolved", "alert_id": alert_id}

@router.delete("/{alert_id}")
def delete_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    """Delete an alert"""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Alert not found")

    db.delete(alert)
    db.commit()

    return {"message": "Alert deleted", "alert_id": alert_id}
