from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class SystemSettingsBase(BaseModel):
    default_item_threshold: int = Field(10, ge=0)
    stock_presence_confirmation_frames: int = Field(2, ge=1)
    stock_absence_confirmation_frames: int = Field(3, ge=1)
    camera_display_name: str = Field("本地演示摄像头", min_length=1, max_length=100)
    camera_location: str = Field("演示货架区域", min_length=1, max_length=100)
    camera_default_sync_inventory: bool = False

    @field_validator("camera_display_name", "camera_location")
    @classmethod
    def strip_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value cannot be empty")
        return normalized


class SystemSettingsUpdate(BaseModel):
    default_item_threshold: int | None = Field(None, ge=0)
    stock_presence_confirmation_frames: int | None = Field(None, ge=1)
    stock_absence_confirmation_frames: int | None = Field(None, ge=1)
    camera_display_name: str | None = Field(None, min_length=1, max_length=100)
    camera_location: str | None = Field(None, min_length=1, max_length=100)
    camera_default_sync_inventory: bool | None = None

    @field_validator("camera_display_name", "camera_location")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value cannot be empty")
        return normalized


class SystemSettingsResponse(SystemSettingsBase):
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
