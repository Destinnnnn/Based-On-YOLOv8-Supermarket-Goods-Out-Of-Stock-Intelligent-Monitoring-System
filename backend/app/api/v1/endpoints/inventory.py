from datetime import datetime
from typing import Any, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.v1.endpoints.auth import get_current_active_admin, get_current_user
from app.models.alert import Alert
from app.models.detection import Detection
from app.models.detection_box import DetectionBox
from app.models.label_mapping import LabelMapping
from app.models.stock_history import StockHistory
from app.schemas.item import Item, ItemCreate, ItemUpdate
from app.models.item import Item as DBItem
from app.models.user import User
from app.db.database import get_db
from app.services.alert_service import alert_service
from app.services.stock_service import stock_service

router = APIRouter(dependencies=[Depends(get_current_user)])

InventoryOrderBy = Literal[
    "id",
    "name",
    "category",
    "aisle",
    "current_stock",
    "threshold",
    "status",
    "last_updated",
]
InventoryOrderDir = Literal["asc", "desc"]

ORDER_BY_COLUMNS = {
    "id": DBItem.id,
    "name": DBItem.name,
    "category": DBItem.category,
    "aisle": DBItem.aisle,
    "current_stock": DBItem.current_stock,
    "threshold": DBItem.threshold,
    "status": DBItem.status,
    "last_updated": DBItem.last_updated,
}


def build_status_change(item: DBItem, old_status: str, new_status: str) -> dict:
    return {
        "item_id": item.id,
        "item_name": item.name,
        "old_status": old_status,
        "new_status": new_status,
        "current_stock": item.current_stock,
        "threshold": item.threshold,
    }

@router.get("/", response_model=List[Item])
def read_items(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    status: Optional[str] = Query(None, pattern="^(normal|low|out)$"),
    category: Optional[str] = None,
    order_by: InventoryOrderBy = Query("id"),
    order_dir: InventoryOrderDir = Query("asc"),
    db: Session = Depends(get_db)
) -> Any:
    """
    Retrieve inventory items with filtering

    Args:
        skip: Number of records to skip
        limit: Maximum number of records to return
        status: Filter by status (normal/low/out)
        category: Filter by category
        order_by: Sort field
        order_dir: Sort direction
    """
    query = db.query(DBItem)

    if status:
        query = query.filter(DBItem.status == status)
    if category:
        query = query.filter(DBItem.category == category)

    sort_column = ORDER_BY_COLUMNS[order_by]
    if order_dir == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    items = query.offset(skip).limit(limit).all()
    return items

@router.post("/", response_model=Item)
def create_item(
    *,
    item_in: ItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
) -> Any:
    """
    Create new inventory item
    """
    # Check if item already exists
    existing = db.query(DBItem).filter(DBItem.id == item_in.id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Item with this ID already exists")

    item_data = item_in.model_dump()
    current_stock = item_data.pop("current_stock", None) or 0
    threshold = item_data.pop("threshold", None) or 10
    calculated_status = stock_service.determine_stock_status(current_stock, threshold)

    item = DBItem(
        **item_data,
        current_stock=current_stock,
        threshold=threshold,
        status=calculated_status,
    )
    db.add(item)
    db.add(
        StockHistory(
            item_id=item.id,
            stock_level=current_stock,
        )
    )
    db.commit()
    db.refresh(item)

    if item.status != "normal":
        alert_service.sync_alerts_for_status_change(
            db,
            build_status_change(item, "normal", item.status),
        )

    return item

@router.post("/reset-state")
def reset_inventory_state(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
) -> Any:
    """
    Reset runtime inventory state while preserving product catalog and mappings.
    """
    detection_boxes_deleted = db.query(DetectionBox).delete(synchronize_session=False)
    detections_deleted = db.query(Detection).delete(synchronize_session=False)
    stock_history_deleted = db.query(StockHistory).delete(synchronize_session=False)
    alerts_deleted = db.query(Alert).delete(synchronize_session=False)
    items_reset = db.query(DBItem).update(
        {
            DBItem.current_stock: 0,
            DBItem.status: "out",
            DBItem.last_updated: datetime.utcnow(),
        },
        synchronize_session=False,
    )

    db.commit()
    stock_service.reset_runtime_state()

    return {
        "message": "Inventory state reset successfully",
        "items_reset": items_reset,
        "detections_deleted": detections_deleted,
        "detection_boxes_deleted": detection_boxes_deleted,
        "stock_history_deleted": stock_history_deleted,
        "alerts_deleted": alerts_deleted,
    }

@router.get("/{item_id}", response_model=Item)
def read_item(
    item_id: str,
    db: Session = Depends(get_db)
) -> Any:
    """
    Get item by ID
    """
    item = db.query(DBItem).filter(DBItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item

@router.patch("/{item_id}", response_model=Item)
def update_item(
    item_id: str,
    item_in: ItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
) -> Any:
    """
    Update inventory item
    """
    item = db.query(DBItem).filter(DBItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    update_data = item_in.model_dump(exclude_unset=True)
    old_status = item.status
    old_stock = item.current_stock
    old_threshold = item.threshold

    for field, value in update_data.items():
        setattr(item, field, value)

    threshold_changed = item.threshold != old_threshold
    stock_changed = item.current_stock != old_stock

    if stock_changed or threshold_changed:
        item.status = stock_service.determine_stock_status(
            item.current_stock,
            item.threshold,
        )

    if stock_changed:
        db.add(
            StockHistory(
                item_id=item.id,
                stock_level=item.current_stock,
            )
        )

    db.commit()
    db.refresh(item)

    if old_status != item.status:
        alert_service.sync_alerts_for_status_change(
            db,
            build_status_change(item, old_status, item.status),
        )

    return item

@router.delete("/{item_id}")
def delete_item(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
) -> Any:
    """
    Delete inventory item
    """
    item = db.query(DBItem).filter(DBItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    db.query(LabelMapping).filter(LabelMapping.item_id == item_id).delete()
    db.delete(item)
    db.commit()
    return {"message": "Item deleted", "item_id": item_id}
