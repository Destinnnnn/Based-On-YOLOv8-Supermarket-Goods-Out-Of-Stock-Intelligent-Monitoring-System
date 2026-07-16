from datetime import datetime

from pydantic import BaseModel


class LabelMappingBase(BaseModel):
    detection_label: str
    item_id: str


class LabelMappingCreate(LabelMappingBase):
    pass


class LabelMappingUpdate(BaseModel):
    detection_label: str | None = None
    item_id: str | None = None


class LabelMappingResponse(LabelMappingBase):
    id: int
    item_name: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
