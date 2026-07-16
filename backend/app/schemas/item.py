from typing import Optional
from pydantic import BaseModel
from datetime import datetime

# Shared mutable properties for create/update
class ItemMutable(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    aisle: Optional[str] = None
    current_stock: Optional[int] = 0
    threshold: Optional[int] = 10

# Properties to receive on item creation
class ItemCreate(ItemMutable):
    id: str
    name: str

# Properties to receive on item update
class ItemUpdate(ItemMutable):
    pass

# Properties shared by models stored in DB
class ItemInDBBase(ItemMutable):
    id: str
    status: str = "normal"
    last_updated: Optional[datetime] = None

    class Config:
        from_attributes = True

# Properties to return to client
class Item(ItemInDBBase):
    pass

# Alert schemas
class AlertResponse(BaseModel):
    id: int
    item_id: str
    alert_type: str
    message: str
    status: str
    created_at: datetime
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True
