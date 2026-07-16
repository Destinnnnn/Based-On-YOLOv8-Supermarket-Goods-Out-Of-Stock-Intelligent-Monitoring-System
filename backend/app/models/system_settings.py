from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.db.base_class import Base


class SystemSettings(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, default=1)
    default_item_threshold = Column(Integer, nullable=False, default=10)
    stock_presence_confirmation_frames = Column(Integer, nullable=False, default=2)
    stock_absence_confirmation_frames = Column(Integer, nullable=False, default=3)
    camera_display_name = Column(String, nullable=False, default="本地演示摄像头")
    camera_location = Column(String, nullable=False, default="演示货架区域")
    camera_default_sync_inventory = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
